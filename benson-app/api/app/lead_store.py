import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update

from .domain import LeadSummary, LeadUpdate
from .store_base import StoreBase
from .storage_schema import (
    LEAD_TRANSITIONS,
    InvalidLeadTransition,
    attachments,
    audit_events,
    lead_notes,
    leads,
    upload_sessions,
)


class LeadStoreMixin(StoreBase):
    def get_upload_session(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(upload_sessions).where(upload_sessions.c.id == session_id)
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            return None
        return dict(row)

    def add_attachment(
        self,
        *,
        lead_id: str,
        original_name: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
    ) -> str:
        return self.add_attachments(
            lead_id=lead_id,
            items=[
                {
                    "original_name": original_name,
                    "storage_key": storage_key,
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                }
            ],
        )[0]

    def add_attachments(
        self, *, lead_id: str, items: list[dict[str, Any]]
    ) -> list[str]:
        attachment_ids = [str(uuid4()) for _ in items]
        with self.engine.begin() as db:
            for attachment_id, item in zip(attachment_ids, items, strict=True):
                db.execute(
                    attachments.insert().values(
                        id=attachment_id,
                        lead_id=lead_id,
                        created_at=datetime.now(UTC),
                        **item,
                    )
                )
                self._audit(
                    db,
                    event="lead.attachment_added",
                    actor="customer-upload",
                    subject_type="lead",
                    subject_id=lead_id,
                    payload={
                        "attachment_id": attachment_id,
                        "content_type": item["content_type"],
                        "size": item["size_bytes"],
                    },
                )
        return attachment_ids

    def reserve_upload_capacity(
        self,
        session_id: str,
        *,
        file_count: int,
        size_bytes: int,
        max_files: int,
        max_bytes: int,
    ) -> bool:
        with self.engine.begin() as db:
            result = db.execute(
                update(upload_sessions)
                .where(
                    upload_sessions.c.id == session_id,
                    upload_sessions.c.expires_at >= datetime.now(UTC),
                    upload_sessions.c.uploaded_files + file_count <= max_files,
                    upload_sessions.c.uploaded_bytes + size_bytes <= max_bytes,
                )
                .values(
                    uploaded_files=upload_sessions.c.uploaded_files + file_count,
                    uploaded_bytes=upload_sessions.c.uploaded_bytes + size_bytes,
                )
            )
        return bool(result.rowcount)

    def release_upload_capacity(
        self, session_id: str, *, file_count: int, size_bytes: int
    ) -> None:
        with self.engine.begin() as db:
            db.execute(
                update(upload_sessions)
                .where(upload_sessions.c.id == session_id)
                .values(
                    uploaded_files=upload_sessions.c.uploaded_files - file_count,
                    uploaded_bytes=upload_sessions.c.uploaded_bytes - size_bytes,
                )
            )

    def lead_count(self) -> int:
        with self.engine.connect() as db:
            return int(
                db.execute(
                    select(func.count())
                    .select_from(leads)
                    .where(leads.c.deleted_at.is_(None), leads.c.is_spam == 0)
                ).scalar_one()
            )

    def list_leads(
        self,
        limit: int = 100,
        *,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
        query: str | None = None,
        source: str | None = None,
        spam: str = "active",
    ) -> list[LeadSummary]:
        statement = select(leads).where(leads.c.deleted_at.is_(None))
        if spam == "active":
            statement = statement.where(leads.c.is_spam == 0)
        elif spam == "spam":
            statement = statement.where(leads.c.is_spam == 1)
        if source:
            statement = statement.where(leads.c.source == source)
        if status:
            statement = statement.where(leads.c.status == status)
        if priority:
            statement = statement.where(leads.c.priority == priority)
        if assigned_to:
            statement = statement.where(leads.c.assigned_to == assigned_to)
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                leads.c.name.ilike(pattern)
                | leads.c.email.ilike(pattern)
                | leads.c.phone.ilike(pattern)
                | leads.c.city.ilike(pattern)
                | leads.c.service_type.ilike(pattern)
                | leads.c.source.ilike(pattern)
            )
        with self.engine.connect() as db:
            rows = (
                db.execute(statement.order_by(leads.c.created_at.desc()).limit(limit))
                .mappings()
                .all()
            )
        return [
            LeadSummary(
                id=row["id"],
                status=row["status"],
                priority=row["priority"],
                name=row["name"],
                phone=row["phone"],
                email=row["email"],
                service_type=row["service_type"],
                city=row["city"],
                created_at=row["created_at"],
                assigned_to=row["assigned_to"],
                source=row["source"],
                is_spam=bool(row["is_spam"]),
                spam_reason=row["spam_reason"],
            )
            for row in rows
        ]

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            lead = (
                db.execute(
                    select(leads).where(
                        leads.c.id == lead_id, leads.c.deleted_at.is_(None)
                    )
                )
                .mappings()
                .first()
            )
            if not lead:
                return None
            lead_attachments = (
                db.execute(
                    select(attachments)
                    .where(attachments.c.lead_id == lead_id)
                    .order_by(attachments.c.created_at)
                )
                .mappings()
                .all()
            )
            notes = (
                db.execute(
                    select(lead_notes)
                    .where(lead_notes.c.lead_id == lead_id)
                    .order_by(lead_notes.c.created_at.desc())
                )
                .mappings()
                .all()
            )
            events = (
                db.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.subject_type == "lead",
                        audit_events.c.subject_id == lead_id,
                    )
                    .order_by(audit_events.c.occurred_at.desc())
                )
                .mappings()
                .all()
            )
        result = dict(lead)
        result["payload"] = json.loads(result["payload"])
        result["attachments"] = [
            {key: value for key, value in dict(item).items() if key != "storage_key"}
            for item in lead_attachments
        ]
        result["notes"] = [dict(item) for item in notes]
        result["audit_events"] = [
            {**dict(item), "payload": json.loads(item["payload"])} for item in events
        ]
        return result

    def get_attachment(self, attachment_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(select(attachments).where(attachments.c.id == attachment_id))
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def update_lead(
        self, lead_id: str, change: LeadUpdate, *, actor: str
    ) -> dict[str, Any] | None:
        values = change.model_dump(exclude_none=True, exclude={"note"})
        if "assigned_to" in values:
            values["assigned_to"] = str(values["assigned_to"]).lower()
        if "email" in values:
            values["email"] = str(values["email"]).lower()
        if "is_spam" in values:
            values["is_spam"] = int(values["is_spam"])
            values["spam_reason"] = (
                None if not values["is_spam"] else "Marked as spam by staff"
            )
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            existing = (
                db.execute(
                    select(leads).where(
                        leads.c.id == lead_id, leads.c.deleted_at.is_(None)
                    )
                )
                .mappings()
                .first()
            )
            if not existing:
                return None
            payload_fields = {"name", "phone", "email", "service_type", "city"}
            payload_changes = payload_fields.intersection(values)
            if payload_changes:
                payload = json.loads(existing["payload"])
                for field in payload_changes:
                    payload[field] = values[field]
                values["payload"] = json.dumps(payload, sort_keys=True)
            requested_status = values.get("status")
            current_status = str(existing["status"])
            if (
                requested_status
                and requested_status != current_status
                and requested_status not in LEAD_TRANSITIONS.get(current_status, set())
            ):
                raise InvalidLeadTransition(
                    f"Lead cannot move from {current_status} to {requested_status}"
                )
            if values:
                values["updated_at"] = now
                db.execute(update(leads).where(leads.c.id == lead_id).values(**values))
                self._audit(
                    db,
                    event="lead.updated",
                    actor=actor,
                    subject_type="lead",
                    subject_id=lead_id,
                    payload={
                        key: {"from": existing[key], "to": value}
                        for key, value in values.items()
                        if key not in {"updated_at", "payload"}
                        and existing[key] != value
                    },
                )
            if change.note:
                note_id = str(uuid4())
                db.execute(
                    lead_notes.insert().values(
                        id=note_id,
                        lead_id=lead_id,
                        author=actor,
                        body=change.note,
                        created_at=now,
                    )
                )
                self._audit(
                    db,
                    event="lead.note_added",
                    actor=actor,
                    subject_type="lead",
                    subject_id=lead_id,
                    payload={"note_id": note_id},
                )
        return self.get_lead(lead_id)

    def delete_lead(self, lead_id: str, *, actor: str) -> bool:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            existing = (
                db.execute(
                    select(leads).where(
                        leads.c.id == lead_id, leads.c.deleted_at.is_(None)
                    )
                )
                .mappings()
                .first()
            )
            if not existing:
                return False
            db.execute(
                update(leads)
                .where(leads.c.id == lead_id)
                .values(deleted_at=now, updated_at=now)
            )
            self._audit(
                db,
                event="lead.archived",
                actor=actor,
                subject_type="lead",
                subject_id=lead_id,
                payload={"name": existing["name"]},
            )
        return True
