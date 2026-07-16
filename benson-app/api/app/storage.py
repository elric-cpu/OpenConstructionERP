import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Column,
    create_engine,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.exc import IntegrityError

from .domain import LeadCreate, LeadReceipt, LeadSummary, LeadUpdate

metadata = MetaData()

LEAD_TRANSITIONS = {
    "new": {"contacted", "closed"},
    "contacted": {"qualified", "closed"},
    "qualified": {"scheduled", "closed"},
    "scheduled": {"closed"},
    "closed": set(),
}


class InvalidLeadTransition(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


leads = Table(
    "leads",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("idempotency_key", String(200), nullable=False, unique=True),
    Column("status", String(40), nullable=False),
    Column("priority", String(40), nullable=False),
    Column("name", String(200), nullable=False),
    Column("phone", String(40), nullable=False),
    Column("email", String(320)),
    Column("service_type", String(120), nullable=False),
    Column("city", String(120), nullable=False),
    Column("assigned_to", String(320)),
    Column("payload", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

upload_sessions = Table(
    "upload_sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("uploaded_files", Integer, nullable=False, default=0),
    Column("uploaded_bytes", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

attachments = Table(
    "attachments",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("original_name", String(500), nullable=False),
    Column("storage_key", String(1_000), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

lead_notes = Table(
    "lead_notes",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("author", String(320), nullable=False),
    Column("body", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("event", String(120), nullable=False, index=True),
    Column("actor", String(320), nullable=False),
    Column("subject_type", String(80), nullable=False),
    Column("subject_id", String(80), nullable=False, index=True),
    Column("payload", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

ai_runs = Table(
    "ai_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("skill_id", String(120), nullable=False),
    Column("actor", String(320), nullable=False),
    Column("role", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("model", String(200), nullable=False),
    Column("context", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ai_proposals = Table(
    "ai_proposals",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("run_id", String(36), nullable=False, index=True),
    Column("status", String(40), nullable=False),
    Column("risk", String(40), nullable=False),
    Column("action", Text, nullable=False),
    Column("decided_by", String(320)),
    Column("decision_comment", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
)

notification_outbox = Table(
    "notification_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("channel", String(20), nullable=False),
    Column("destination", String(320), nullable=False),
    Column("payload", Text, nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("attempts", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False, index=True),
    Column("locked_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("provider_message_id", String(200)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True)),
)

operations_settings = Table(
    "operations_settings",
    metadata,
    Column("key", String(120), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_by", String(320), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class OperationsStore:
    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            database_url, pool_pre_ping=True, connect_args=connect_args
        )

    def initialize_schema(self) -> None:
        metadata.create_all(self.engine)

    def readiness_probe(self) -> None:
        with self.engine.connect() as db:
            db.execute(select(1)).scalar_one()

    def _audit(
        self,
        db: Any,
        *,
        event: str,
        actor: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        db.execute(
            audit_events.insert().values(
                id=str(uuid4()),
                event=event,
                actor=actor,
                subject_type=subject_type,
                subject_id=subject_id,
                payload=json.dumps(payload, sort_keys=True),
                occurred_at=datetime.now(UTC),
            )
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
        notification_max_attempts: int,
    ) -> LeadReceipt:
        now = datetime.now(UTC)
        lead_id = str(uuid4())
        upload_session_id = str(uuid4())
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
                        "urgency": lead.urgency,
                        "city": lead.city,
                        "message": lead.message,
                    },
                    sort_keys=True,
                )
                destinations = [("email", notification_email_to)]
                if lead.urgency == "emergency" and emergency_sms_to:
                    destinations.append(("sms", emergency_sms_to))
                for channel, destination in destinations:
                    db.execute(
                        notification_outbox.insert().values(
                            id=str(uuid4()),
                            lead_id=lead_id,
                            channel=channel,
                            destination=destination,
                            payload=notification_payload,
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
                    payload={"idempotency_key": idempotency_key, "priority": values["priority"]},
                )
        except IntegrityError:
            with self.engine.connect() as db:
                existing = (
                    db.execute(select(leads).where(leads.c.idempotency_key == idempotency_key))
                    .mappings()
                    .one()
                )
                session = (
                    db.execute(
                        select(upload_sessions).where(upload_sessions.c.lead_id == existing["id"])
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
                        notification_outbox.c.attempts < notification_outbox.c.max_attempts,
                        notification_outbox.c.available_at <= now,
                        or_(
                            notification_outbox.c.status == "pending",
                            (
                                (notification_outbox.c.status == "processing")
                                & (notification_outbox.c.locked_at <= stale_before)
                            ),
                        ),
                    )
                    .order_by(notification_outbox.c.available_at, notification_outbox.c.created_at)
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
                    claimed.append(item)
        return claimed

    def mark_notification_sent(self, notification_id: str, provider_message_id: str) -> None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            db.execute(
                update(notification_outbox)
                .where(
                    notification_outbox.c.id == notification_id,
                    notification_outbox.c.status == "processing",
                )
                .values(
                    status="sent",
                    attempts=notification_outbox.c.attempts + 1,
                    provider_message_id=provider_message_id,
                    last_error=None,
                    locked_at=None,
                    sent_at=now,
                    updated_at=now,
                )
            )

    def mark_notification_failed(self, notification_id: str, error: str) -> None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            row = (
                db.execute(
                    select(notification_outbox).where(
                        notification_outbox.c.id == notification_id,
                        notification_outbox.c.status == "processing",
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                return
            attempts = int(row["attempts"]) + 1
            exhausted = attempts >= int(row["max_attempts"])
            retry_minutes = min(60, 2 ** min(attempts - 1, 6))
            db.execute(
                update(notification_outbox)
                .where(notification_outbox.c.id == notification_id)
                .values(
                    status="failed" if exhausted else "pending",
                    attempts=attempts,
                    available_at=now + timedelta(minutes=retry_minutes),
                    locked_at=None,
                    last_error=error[:1_000],
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

    def notification_settings(self, *, sms_enabled_default: bool = False) -> dict[str, bool]:
        with self.engine.connect() as db:
            value = db.execute(
                select(operations_settings.c.value).where(
                    operations_settings.c.key == "sms_enabled"
                )
            ).scalar_one_or_none()
        return {"sms_enabled": sms_enabled_default if value is None else value == "true"}

    def update_notification_settings(self, *, sms_enabled: bool, actor: str) -> dict[str, bool]:
        now = datetime.now(UTC)
        value = "true" if sms_enabled else "false"
        with self.engine.begin() as db:
            existing = db.execute(
                select(operations_settings.c.key).where(operations_settings.c.key == "sms_enabled")
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

    @staticmethod
    def _receipt(
        lead_row: RowMapping, session_row: RowMapping, upload_base_url: str, *, duplicate: bool
    ) -> LeadReceipt:
        return LeadReceipt(
            lead_id=lead_row["id"],
            upload_session_id=session_row["id"],
            upload_url=f"{upload_base_url.rstrip('/')}/uploads/{session_row['id']}",
            accepted_at=lead_row["created_at"],
            duplicate=duplicate,
        )

    def get_upload_session(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(select(upload_sessions).where(upload_sessions.c.id == session_id))
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

    def add_attachments(self, *, lead_id: str, items: list[dict[str, Any]]) -> list[str]:
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

    def release_upload_capacity(self, session_id: str, *, file_count: int, size_bytes: int) -> None:
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
            return int(db.execute(select(func.count()).select_from(leads)).scalar_one())

    def list_leads(
        self,
        limit: int = 100,
        *,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
        query: str | None = None,
    ) -> list[LeadSummary]:
        statement = select(leads)
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
            )
            for row in rows
        ]

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            lead = db.execute(select(leads).where(leads.c.id == lead_id)).mappings().first()
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

    def update_lead(self, lead_id: str, change: LeadUpdate, *, actor: str) -> dict[str, Any] | None:
        values = change.model_dump(exclude_none=True, exclude={"note"})
        if "assigned_to" in values:
            values["assigned_to"] = str(values["assigned_to"]).lower()
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            existing = db.execute(select(leads).where(leads.c.id == lead_id)).mappings().first()
            if not existing:
                return None
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
                        if key != "updated_at" and existing[key] != value
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

    def create_ai_run(
        self,
        *,
        skill_id: str,
        actor: str,
        role: str,
        status: str,
        prompt: str,
        summary: str,
        model: str,
        context: dict[str, Any],
        risk: str,
    ) -> tuple[str, str | None]:
        run_id = str(uuid4())
        proposal_id = str(uuid4()) if risk != "internal" else None
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            db.execute(
                ai_runs.insert().values(
                    id=run_id,
                    skill_id=skill_id,
                    actor=actor,
                    role=role,
                    status=status,
                    prompt=prompt,
                    summary=summary,
                    model=model,
                    context=json.dumps(context, sort_keys=True),
                    created_at=now,
                )
            )
            if proposal_id:
                db.execute(
                    ai_proposals.insert().values(
                        id=proposal_id,
                        run_id=run_id,
                        status="pending",
                        risk=risk,
                        action=json.dumps(
                            {"skill_id": skill_id, "summary": summary}, sort_keys=True
                        ),
                        created_at=now,
                    )
                )
            self._audit(
                db,
                event="ai.run_completed",
                actor=actor,
                subject_type="ai_run",
                subject_id=run_id,
                payload={"skill_id": skill_id, "risk": risk, "proposal_id": proposal_id},
            )
        return run_id, proposal_id

    def decide_proposal(
        self, proposal_id: str, *, approved: bool, actor: str, comment: str
    ) -> bool:
        with self.engine.begin() as db:
            existing = (
                db.execute(select(ai_proposals).where(ai_proposals.c.id == proposal_id))
                .mappings()
                .first()
            )
            if not existing or existing["status"] != "pending":
                return False
            result = db.execute(
                update(ai_proposals)
                .where(ai_proposals.c.id == proposal_id, ai_proposals.c.status == "pending")
                .values(
                    status="approved" if approved else "rejected",
                    decided_by=actor,
                    decision_comment=comment,
                    decided_at=datetime.now(UTC),
                )
            )
            if result.rowcount != 1:
                return False
            self._audit(
                db,
                event="ai.proposal_approved" if approved else "ai.proposal_rejected",
                actor=actor,
                subject_type="ai_proposal",
                subject_id=proposal_id,
                payload={"run_id": existing["run_id"], "comment": comment},
            )
        return True


@lru_cache(maxsize=16)
def operations_store(database_url: str) -> OperationsStore:
    return OperationsStore(database_url)
