import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text

from .storage_schema import IdempotencyConflict, leads
from .store_base import StoreBase


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


class LogisticsStoreMixin(StoreBase):
    """PostgreSQL repository for the separately migrated logistics tables."""

    def create_or_get_public_inquiry(
        self,
        *,
        idempotency_key: str,
        source: str,
        raw_payload: dict[str, Any],
        normalized_payload: dict[str, Any],
        actor: str,
        source_message_id: str | None = None,
        queue_state: str = "held",
        hold_reason: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Return an existing lead/inquiry or atomically create a held inquiry."""
        payload_digest = _digest(normalized_payload)
        now = datetime.now(UTC)
        inquiry_id = str(uuid4())
        with self.engine.begin() as db:
            lead = (
                db.execute(
                    select(leads.c.id, leads.c.payload).where(
                        leads.c.idempotency_key == idempotency_key
                    )
                )
                .mappings()
                .first()
            )
            if lead:
                return {"record_type": "lead", "id": str(lead["id"])}, False
            inserted = (
                db.execute(
                    text(
                        """
                        INSERT INTO logistics_inquiry_holding_queue (
                            id, idempotency_key, source, source_message_id,
                            payload_digest, raw_payload, normalized_payload,
                            queue_state, hold_reason, available_at,
                            created_at, created_by, updated_at, updated_by
                        ) VALUES (
                            :id, :idempotency_key, :source, :source_message_id,
                            :payload_digest, CAST(:raw_payload AS jsonb),
                            CAST(:normalized_payload AS jsonb), :queue_state,
                            :hold_reason, :now, :now, :actor, :now, :actor
                        )
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING *
                        """
                    ),
                    {
                        "id": inquiry_id,
                        "idempotency_key": idempotency_key,
                        "source": source,
                        "source_message_id": source_message_id,
                        "payload_digest": payload_digest,
                        "raw_payload": _canonical_json(raw_payload),
                        "normalized_payload": _canonical_json(normalized_payload),
                        "queue_state": queue_state,
                        "hold_reason": hold_reason,
                        "now": now,
                        "actor": actor,
                    },
                )
                .mappings()
                .first()
            )
            if inserted:
                self._audit(
                    db,
                    event="logistics.inquiry_held",
                    actor=actor,
                    subject_type="public_inquiry",
                    subject_id=inquiry_id,
                    payload={"source": source, "payload_digest": payload_digest},
                )
                return {"record_type": "inquiry", **dict(inserted)}, True
            existing = (
                db.execute(
                    text(
                        """
                        SELECT * FROM logistics_inquiry_holding_queue
                        WHERE idempotency_key = :idempotency_key
                        """
                    ),
                    {"idempotency_key": idempotency_key},
                )
                .mappings()
                .one()
            )
            if existing["payload_digest"] != payload_digest:
                raise IdempotencyConflict("Inquiry idempotency key payload mismatch")
            return {"record_type": "inquiry", **dict(existing)}, False

    def link_photo_asset_to_work_order(
        self,
        *,
        work_order_id: str,
        storage_key: str,
        original_name: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        actor: str,
        asset_role: str = "intake",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, bool]:
        asset_id = str(uuid4())
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            inserted = db.execute(
                text(
                    """
                    INSERT INTO logistics_work_order_photo_assets (
                        id, work_order_id, asset_role, storage_key, original_name,
                        content_type, size_bytes, sha256, metadata, status,
                        created_at, created_by, updated_at, updated_by
                    ) VALUES (
                        :id, :work_order_id, :asset_role, :storage_key,
                        :original_name, :content_type, :size_bytes, :sha256,
                        CAST(:metadata AS jsonb), 'active', :now, :actor, :now, :actor
                    )
                    ON CONFLICT (work_order_id, sha256) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "id": asset_id,
                    "work_order_id": work_order_id,
                    "asset_role": asset_role,
                    "storage_key": storage_key,
                    "original_name": original_name,
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                    "metadata": _canonical_json(metadata or {}),
                    "now": now,
                    "actor": actor,
                },
            ).scalar_one_or_none()
            if inserted:
                self._audit(
                    db,
                    event="logistics.photo_asset_linked",
                    actor=actor,
                    subject_type="work_order",
                    subject_id=work_order_id,
                    payload={"asset_id": asset_id, "sha256": sha256},
                )
                return str(inserted), True
            existing = db.execute(
                text(
                    """
                    SELECT id FROM logistics_work_order_photo_assets
                    WHERE work_order_id = :work_order_id AND sha256 = :sha256
                    """
                ),
                {"work_order_id": work_order_id, "sha256": sha256},
            ).scalar_one()
            return str(existing), False

    def enqueue_inbound_message_media(
        self,
        *,
        provider: str,
        provider_message_id: str,
        provider_media_key: str,
        sender_phone_hash: str,
        media_url: str,
        content_type: str,
        actor: str,
        inquiry_id: str | None = None,
        accepted_lead_id: str | None = None,
        sender_phone_encrypted_ref: str | None = None,
        media_ordinal: int = 0,
    ) -> tuple[str, bool]:
        media_id = str(uuid4())
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            inserted = db.execute(
                text(
                    """
                    INSERT INTO logistics_inbound_message_media (
                        id, provider, provider_message_id, provider_media_key,
                        inquiry_id, accepted_lead_id, sender_phone_hash,
                        sender_phone_encrypted_ref, media_url, content_type,
                        media_ordinal, status, available_at,
                        created_at, created_by, updated_at, updated_by
                    ) VALUES (
                        :id, :provider, :provider_message_id, :provider_media_key,
                        :inquiry_id, :accepted_lead_id, :sender_phone_hash,
                        :sender_phone_encrypted_ref, :media_url, :content_type,
                        :media_ordinal, 'queued', :now, :now, :actor, :now, :actor
                    )
                    ON CONFLICT (provider, provider_media_key) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "id": media_id,
                    "provider": provider,
                    "provider_message_id": provider_message_id,
                    "provider_media_key": provider_media_key,
                    "inquiry_id": inquiry_id,
                    "accepted_lead_id": accepted_lead_id,
                    "sender_phone_hash": sender_phone_hash,
                    "sender_phone_encrypted_ref": sender_phone_encrypted_ref,
                    "media_url": media_url,
                    "content_type": content_type,
                    "media_ordinal": media_ordinal,
                    "now": now,
                    "actor": actor,
                },
            ).scalar_one_or_none()
            if inserted:
                self._audit(
                    db,
                    event="logistics.inbound_media_queued",
                    actor=actor,
                    subject_type="inbound_message",
                    subject_id=provider_message_id,
                    payload={"media_id": media_id, "provider": provider},
                )
                return str(inserted), True
            existing = db.execute(
                text(
                    """
                    SELECT id FROM logistics_inbound_message_media
                    WHERE provider = :provider
                      AND provider_media_key = :provider_media_key
                    """
                ),
                {"provider": provider, "provider_media_key": provider_media_key},
            ).scalar_one()
            return str(existing), False

    def record_logistics_integration_event(
        self,
        *,
        event: str,
        actor: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        with self.engine.begin() as db:
            self._audit(
                db,
                event=event,
                actor=actor,
                subject_type=subject_type,
                subject_id=subject_id,
                payload=payload,
            )
