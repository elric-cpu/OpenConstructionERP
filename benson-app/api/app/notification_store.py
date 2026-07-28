import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Table, func, or_, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from .domain import LeadCreate, LeadReceipt
from .lead_rules import classify_spam, lead_source
from .store_base import StoreBase
from .storage_schema import (
    IdempotencyConflict,
    employee_notification_outbox,
    leads,
    notification_outbox,
    operations_settings,
    upload_sessions,
)
from .onboarding_schema import identity_provisioning_commands


class NotificationStoreMixin(StoreBase):
    @staticmethod
    def _receipt(
        lead_row: RowMapping,
        session_row: RowMapping,
        upload_base_url: str,
        *,
        duplicate: bool,
    ) -> LeadReceipt:
        return LeadReceipt(
            lead_id=lead_row["id"],
            upload_session_id=session_row["id"],
            upload_url=f"{upload_base_url.rstrip('/')}/uploads/{session_row['id']}",
            accepted_at=lead_row["created_at"],
            duplicate=duplicate,
        )

    def create_or_get_lead(
        self,
        *,
        idempotency_key: str,
        lead: LeadCreate,
        upload_base_url: str,
        upload_session_hours: int,
        notification_email_to: str,
        emergency_sms_to: str,
        client_sms_to: str,
        notification_max_attempts: int,
    ) -> LeadReceipt:
        now = datetime.now(UTC)
        lead_id = str(uuid4())
        upload_session_id = str(uuid4())
        payload = lead.model_dump(mode="json")
        is_spam, spam_reason = classify_spam(payload)
        values = {
            "id": lead_id,
            "idempotency_key": idempotency_key,
            "status": "new",
            "priority": "urgent" if lead.urgency == "emergency" else "normal",
            "name": lead.name,
            "phone": lead.phone,
            "email": str(lead.email) if lead.email else None,
            "service_type": lead.service_type,
            "city": lead.city,
            "source": lead_source(payload),
            "is_spam": int(is_spam),
            "spam_reason": spam_reason,
            "payload": lead.model_dump_json(),
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self.engine.begin() as db:
                db.execute(leads.insert().values(**values))
                db.execute(
                    upload_sessions.insert().values(
                        id=upload_session_id,
                        lead_id=lead_id,
                        expires_at=now + timedelta(hours=upload_session_hours),
                        uploaded_files=0,
                        uploaded_bytes=0,
                        created_at=now,
                    )
                )
                notification_payload = json.dumps(
                    {
                        "name": lead.name,
                        "phone": lead.phone,
                        "email": str(lead.email) if lead.email else None,
                        "service_type": lead.service_type,
                        "customer_type": lead.customer_type,
                        "urgency": lead.urgency,
                        "city": lead.city,
                        "message": lead.message,
                    },
                    sort_keys=True,
                )
                destinations: list[tuple[str, str, str]] = (
                    []
                    if is_spam
                    else [("email", notification_email_to, "internal_lead_alert")]
                )
                if not is_spam and lead.urgency == "emergency" and emergency_sms_to:
                    destinations.append(
                        ("sms", emergency_sms_to, "internal_emergency_alert")
                    )
                if not is_spam and client_sms_to:
                    destinations.append(
                        ("sms", client_sms_to, "client_lead_acknowledgement")
                    )
                for channel, destination, kind in destinations:
                    item_payload = json.loads(notification_payload)
                    item_payload["kind"] = kind
                    db.execute(
                        notification_outbox.insert().values(
                            id=str(uuid4()),
                            lead_id=lead_id,
                            channel=channel,
                            destination=destination,
                            payload=json.dumps(item_payload, sort_keys=True),
                            status="pending",
                            attempts=0,
                            max_attempts=notification_max_attempts,
                            available_at=now,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                self._audit(
                    db,
                    event="lead.accepted",
                    actor="benson-website",
                    subject_type="lead",
                    subject_id=lead_id,
                    payload={
                        "idempotency_key": idempotency_key,
                        "priority": values["priority"],
                        "source": values["source"],
                        "is_spam": is_spam,
                        "spam_reason": spam_reason,
                    },
                )
        except IntegrityError:
            with self.engine.connect() as db:
                existing = (
                    db.execute(
                        select(leads).where(leads.c.idempotency_key == idempotency_key)
                    )
                    .mappings()
                    .one()
                )
                session = (
                    db.execute(
                        select(upload_sessions).where(
                            upload_sessions.c.lead_id == existing["id"]
                        )
                    )
                    .mappings()
                    .one()
                )
            if existing["payload"] != lead.model_dump_json():
                raise IdempotencyConflict(
                    "Idempotency-Key was already used for a different lead payload"
                )
            return self._receipt(existing, session, upload_base_url, duplicate=True)
        return LeadReceipt(
            lead_id=lead_id,
            upload_session_id=upload_session_id,
            upload_url=f"{upload_base_url.rstrip('/')}/uploads/{upload_session_id}",
            accepted_at=now,
            duplicate=False,
        )

    def claim_notifications(
        self, *, limit: int, lock_timeout_minutes: int = 10
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        stale_before = now - timedelta(minutes=lock_timeout_minutes)
        with self.engine.begin() as db:
            rows = (
                db.execute(
                    select(notification_outbox)
                    .where(
                        notification_outbox.c.attempts
                        < notification_outbox.c.max_attempts,
                        notification_outbox.c.available_at <= now,
                        or_(
                            notification_outbox.c.status == "pending",
                            (
                                (notification_outbox.c.status == "processing")
                                & (notification_outbox.c.locked_at <= stale_before)
                            ),
                        ),
                    )
                    .order_by(
                        notification_outbox.c.available_at,
                        notification_outbox.c.created_at,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            claimed: list[dict[str, Any]] = []
            for row in rows:
                result = db.execute(
                    update(notification_outbox)
                    .where(
                        notification_outbox.c.id == row["id"],
                        or_(
                            notification_outbox.c.status == "pending",
                            notification_outbox.c.locked_at <= stale_before,
                        ),
                    )
                    .values(status="processing", locked_at=now, updated_at=now)
                )
                if result.rowcount == 1:
                    item = dict(row)
                    item["payload"] = json.loads(item["payload"])
                    item["outbox_type"] = "lead"
                    claimed.append(item)
        return claimed

    def claim_employee_notifications(
        self, *, limit: int, lock_timeout_minutes: int = 10
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        stale_before = now - timedelta(minutes=lock_timeout_minutes)
        with self.engine.begin() as db:
            rows = (
                db.execute(
                    select(employee_notification_outbox)
                    .where(
                        employee_notification_outbox.c.attempts
                        < employee_notification_outbox.c.max_attempts,
                        employee_notification_outbox.c.available_at <= now,
                        or_(
                            employee_notification_outbox.c.status == "pending",
                            (
                                (employee_notification_outbox.c.status == "processing")
                                & (
                                    employee_notification_outbox.c.locked_at
                                    <= stale_before
                                )
                            ),
                        ),
                    )
                    .order_by(employee_notification_outbox.c.available_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            claimed: list[dict[str, Any]] = []
            for row in rows:
                result = db.execute(
                    update(employee_notification_outbox)
                    .where(
                        employee_notification_outbox.c.id == row["id"],
                        or_(
                            employee_notification_outbox.c.status == "pending",
                            employee_notification_outbox.c.locked_at <= stale_before,
                        ),
                    )
                    .values(status="processing", locked_at=now, updated_at=now)
                )
                if result.rowcount == 1:
                    item = dict(row)
                    item["channel"] = "email"
                    item["payload"] = json.loads(item["payload"])
                    item["outbox_type"] = "employee"
                    claimed.append(item)
        return claimed

    @staticmethod
    def _outbox(outbox_type: str) -> Table:
        return (
            employee_notification_outbox
            if outbox_type == "employee"
            else notification_outbox
        )

    def mark_notification_sent(
        self,
        notification_id: str,
        provider_message_id: str,
        *,
        outbox_type: str = "lead",
    ) -> None:
        now = datetime.now(UTC)
        outbox = self._outbox(outbox_type)
        with self.engine.begin() as db:
            row = (
                db.execute(select(outbox).where(outbox.c.id == notification_id))
                .mappings()
                .first()
            )
            payload = (
                json.loads(row["payload"])
                if row and outbox_type == "employee"
                else None
            )
            if payload and payload.pop("bootstrap_credential", None):
                command_id = payload.get("identity_command_id")
                if command_id:
                    db.execute(
                        update(identity_provisioning_commands)
                        .where(identity_provisioning_commands.c.id == command_id)
                        .values(bootstrap_credential=None, updated_at=now)
                    )
            db.execute(
                update(outbox)
                .where(
                    outbox.c.id == notification_id,
                    outbox.c.status == "processing",
                )
                .values(
                    status="sent",
                    attempts=outbox.c.attempts + 1,
                    provider_message_id=provider_message_id,
                    last_error=None,
                    locked_at=None,
                    sent_at=now,
                    payload=json.dumps(payload, sort_keys=True)
                    if payload is not None
                    else row["payload"]
                    if row
                    else None,
                    updated_at=now,
                )
            )

    def mark_notification_failed(
        self, notification_id: str, error: str, *, outbox_type: str = "lead"
    ) -> None:
        now = datetime.now(UTC)
        outbox = self._outbox(outbox_type)
        with self.engine.begin() as db:
            row = (
                db.execute(
                    select(outbox).where(
                        outbox.c.id == notification_id,
                        outbox.c.status == "processing",
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                return
            attempts = int(row["attempts"]) + 1
            exhausted = attempts >= int(row["max_attempts"])
            payload = json.loads(row["payload"]) if outbox_type == "employee" else None
            if exhausted and payload and payload.pop("bootstrap_credential", None):
                command_id = payload.get("identity_command_id")
                if command_id:
                    db.execute(
                        update(identity_provisioning_commands)
                        .where(identity_provisioning_commands.c.id == command_id)
                        .values(bootstrap_credential=None, updated_at=now)
                    )
            retry_minutes = min(60, 2 ** min(attempts - 1, 6))
            db.execute(
                update(outbox)
                .where(outbox.c.id == notification_id)
                .values(
                    status="failed" if exhausted else "pending",
                    attempts=attempts,
                    available_at=now + timedelta(minutes=retry_minutes),
                    locked_at=None,
                    last_error=error[:1_000],
                    payload=(
                        json.dumps(payload, sort_keys=True)
                        if exhausted and payload is not None
                        else row["payload"]
                    ),
                    updated_at=now,
                )
            )

    def mark_notification_disabled(self, notification_id: str) -> None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            db.execute(
                update(notification_outbox)
                .where(
                    notification_outbox.c.id == notification_id,
                    notification_outbox.c.status == "processing",
                )
                .values(
                    status="disabled",
                    locked_at=None,
                    last_error="SMS delivery disabled in Operations settings",
                    updated_at=now,
                )
            )

    def notification_settings(
        self, *, sms_enabled_default: bool = False
    ) -> dict[str, bool]:
        with self.engine.connect() as db:
            value = db.execute(
                select(operations_settings.c.value).where(
                    operations_settings.c.key == "sms_enabled"
                )
            ).scalar_one_or_none()
        return {
            "sms_enabled": sms_enabled_default if value is None else value == "true"
        }

    def update_notification_settings(
        self, *, sms_enabled: bool, actor: str
    ) -> dict[str, bool]:
        now = datetime.now(UTC)
        value = "true" if sms_enabled else "false"
        with self.engine.begin() as db:
            existing = db.execute(
                select(operations_settings.c.key).where(
                    operations_settings.c.key == "sms_enabled"
                )
            ).scalar_one_or_none()
            if existing is None:
                db.execute(
                    operations_settings.insert().values(
                        key="sms_enabled", value=value, updated_by=actor, updated_at=now
                    )
                )
            else:
                db.execute(
                    update(operations_settings)
                    .where(operations_settings.c.key == "sms_enabled")
                    .values(value=value, updated_by=actor, updated_at=now)
                )
            if not sms_enabled:
                db.execute(
                    update(notification_outbox)
                    .where(
                        notification_outbox.c.channel == "sms",
                        notification_outbox.c.status.in_(("pending", "processing")),
                    )
                    .values(
                        status="disabled",
                        locked_at=None,
                        last_error="SMS delivery disabled in Operations settings",
                        updated_at=now,
                    )
                )
            self._audit(
                db,
                event="settings.notifications_updated",
                actor=actor,
                subject_type="settings",
                subject_id="notifications",
                payload={"sms_enabled": sms_enabled},
            )
        return {"sms_enabled": sms_enabled}

    def notification_counts(self) -> dict[str, int]:
        with self.engine.connect() as db:
            rows = db.execute(
                select(notification_outbox.c.status, func.count()).group_by(
                    notification_outbox.c.status
                )
            ).all()
        return {str(status): int(count) for status, count in rows}
