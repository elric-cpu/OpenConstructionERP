# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Compliance documents service — CRUD + status derivation."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date as _date, datetime
from typing import Any

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compliance_docs.models import ComplianceDoc
from app.modules.compliance_docs.repository import ComplianceDocRepository
from app.modules.compliance_docs.schemas import (
    ComplianceDocCreate,
    ComplianceDocUpdate,
)

logger = logging.getLogger(__name__)

# ── Status set (kept in sync with schemas.STATUSES) ────────────────────

_TERMINAL_STATUSES: frozenset[str] = frozenset({"cancelled", "void"})


def recompute_status(
    today: _date,
    expires_at: _date,
    notify_days_before: int,
    *,
    current_status: str | None = None,
) -> str:
    """Derive ``status`` from the date window.

    Pure function so unit tests can drive it without a session.

    Rules:
        - If the caller has explicitly marked the document ``cancelled``
          or ``void``, preserve that — those are terminal manual states
          and must never auto-flip back to ``active``.
        - ``today > expires_at``  → ``expired``.
        - ``today + notify_days_before >= expires_at`` → ``expiring_soon``.
        - Otherwise → ``active``.

    Args:
        today: The reference date (usually :func:`datetime.now().date()`).
        expires_at: When the document loses validity.
        notify_days_before: How many days before expiry counts as
            "expiring soon".
        current_status: Existing stored status; ``cancelled``/``void``
            are preserved.
    """
    if current_status in _TERMINAL_STATUSES:
        return current_status  # type: ignore[return-value]

    if today > expires_at:
        return "expired"

    # Inclusive on both sides — exactly ``notify_days_before`` days out
    # already counts as "expiring soon" so reminders aren't silently
    # skipped on the boundary day.
    delta = (expires_at - today).days
    if delta <= max(0, notify_days_before):
        return "expiring_soon"

    return "active"


class ComplianceDocService:
    """Business logic for the compliance docs tracker."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ComplianceDocRepository(session)

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _today() -> _date:
        return datetime.now(UTC).date()

    async def _check_attachment(
        self,
        project_id: uuid.UUID,
        attachment_document_id: uuid.UUID | None,
    ) -> None:
        """Reject an attachment from a different project.

        FK is enough to prevent dangling references, but cross-project
        smuggling needs an extra service-level guard.
        """
        if attachment_document_id is None:
            return
        # Lazy import — keeps the module loadable when the documents
        # module is disabled.
        try:
            from app.modules.documents.models import Document
        except ImportError:  # pragma: no cover — documents always present
            return

        stmt = select(Document.project_id).where(
            Document.id == attachment_document_id
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Attachment document not found.",
            )
        if str(row[0]) != str(project_id):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Attachment document belongs to a different project."
                ),
            )

    # ── CRUD ────────────────────────────────────────────────────────

    async def create_doc(
        self,
        data: ComplianceDocCreate,
        *,
        user_id: str | None = None,
    ) -> ComplianceDoc:
        if data.expires_at < data.effective_date:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    "expires_at must be on or after effective_date."
                ),
            )

        await self._check_attachment(
            data.project_id, data.attachment_document_id,
        )

        derived_status = data.status or recompute_status(
            today=self._today(),
            expires_at=data.expires_at,
            notify_days_before=data.notify_days_before,
        )

        doc = ComplianceDoc(
            project_id=data.project_id,
            doc_type=data.doc_type,
            name=data.name,
            issuer=data.issuer,
            policy_number=data.policy_number,
            coverage_amount=data.coverage_amount,
            currency=data.currency,
            effective_date=data.effective_date,
            expires_at=data.expires_at,
            notify_days_before=data.notify_days_before,
            status=derived_status,
            attachment_document_id=data.attachment_document_id,
            notes=data.notes,
            metadata_=data.metadata,
            created_by=user_id,
        )
        doc = await self.repo.create(doc)
        logger.info(
            "Compliance doc created: %s (%s) for project %s",
            doc.id, doc.doc_type, doc.project_id,
        )
        return doc

    async def get_doc(self, doc_id: uuid.UUID) -> ComplianceDoc:
        doc = await self.repo.get_by_id(doc_id)
        if doc is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Compliance document not found.",
            )
        return doc

    async def list_docs(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None = None,
        doc_type: str | None = None,
    ) -> list[ComplianceDoc]:
        return await self.repo.list_for_project(
            project_id, status=status, doc_type=doc_type,
        )

    async def list_expiring_soon(
        self,
        project_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[ComplianceDoc]:
        return await self.repo.list_expiring_soon(project_id, limit=limit)

    async def update_doc(
        self,
        doc_id: uuid.UUID,
        data: ComplianceDocUpdate,
    ) -> ComplianceDoc:
        doc = await self.get_doc(doc_id)

        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        # Same-project guard if attachment is being changed.
        if "attachment_document_id" in fields:
            await self._check_attachment(
                doc.project_id, fields["attachment_document_id"],
            )

        # Validate date ordering if either side moved.
        new_effective = fields.get("effective_date", doc.effective_date)
        new_expires = fields.get("expires_at", doc.expires_at)
        if new_expires < new_effective:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    "expires_at must be on or after effective_date."
                ),
            )

        # If status not explicitly set in the patch, recompute it from
        # the (possibly updated) date window.
        explicit_status = fields.get("status")
        if explicit_status is None:
            fields["status"] = recompute_status(
                today=self._today(),
                expires_at=new_expires,
                notify_days_before=fields.get(
                    "notify_days_before", doc.notify_days_before,
                ),
                current_status=doc.status,
            )

        if not fields:
            return doc

        await self.repo.update_fields(doc_id, **fields)
        fresh = await self.repo.get_by_id(doc_id)
        return fresh or doc

    async def delete_doc(self, doc_id: uuid.UUID) -> None:
        await self.get_doc(doc_id)
        await self.repo.delete(doc_id)
        logger.info("Compliance doc deleted: %s", doc_id)


__all__ = ["ComplianceDocService", "recompute_status"]
