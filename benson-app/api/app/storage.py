import hashlib
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
    Date,
    create_engine,
    func,
    inspect,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.exc import IntegrityError

from .domain import (
    EmployeeCreate,
    EmployeeInviteReceipt,
    EmployeeSummary,
    EmployeeTaskSummary,
    LeadCreate,
    LeadReceipt,
    LeadSummary,
    LeadUpdate,
)
from .compliance import RULE_VERSION, initial_employee_tasks
from .signing import employee_invite_token

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


class InvalidEmployeeInvite(ValueError):
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
    Column("source", String(200), nullable=False, default="Website"),
    Column("is_spam", Integer, nullable=False, default=0),
    Column("spam_reason", String(500)),
    Column("deleted_at", DateTime(timezone=True)),
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

employees = Table(
    "employees",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("email", String(320), nullable=False, unique=True),
    Column("start_date", Date, nullable=False),
    Column("work_location", String(200), nullable=False),
    Column("classification", String(40), nullable=False),
    Column("role", String(40), nullable=False),
    Column("federal_contract_applicability", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("created_by", String(320), nullable=False),
    Column("google_subject", String(200), unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

employee_invites = Table(
    "employee_invites",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

employee_tasks = Table(
    "employee_tasks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
    Column("requirement_id", String(120), nullable=False),
    Column("label", String(300), nullable=False),
    Column("responsible_party", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("due_date", Date, nullable=False),
    Column("instructions", Text, nullable=False),
    Column("applicability_reason", Text, nullable=False),
    Column("evidence_required", Integer, nullable=False),
    Column("rule_version", String(120), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("completed_by", String(320)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

employee_notification_outbox = Table(
    "employee_notification_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
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


def lead_source(payload: dict[str, Any]) -> str:
    utm_source = str(payload.get("utm_source", "")).strip()
    if utm_source:
        return utm_source[:200]
    context = str(payload.get("form_context", "")).strip()
    if context and context not in {"general", "contact"}:
        return context[:200]
    source_page = str(payload.get("source_page", "")).strip()
    return source_page[:200] if source_page else "Website"


def classify_spam(payload: dict[str, Any]) -> tuple[bool, str | None]:
    content = " ".join(
        str(payload.get(field, "")) for field in ("name", "email", "service_type", "message")
    ).lower()
    reasons: list[str] = []
    spam_phrases = (
        "backlink",
        "guest post",
        "search engine optimization",
        "seo services",
        "crypto",
        "casino",
        "domain authority",
        "web traffic",
    )
    matched = [phrase for phrase in spam_phrases if phrase in content]
    if matched:
        reasons.append(f"spam language: {', '.join(matched[:2])}")
    link_count = content.count("http://") + content.count("https://") + content.count("www.")
    if link_count >= 2:
        reasons.append("multiple external links")
    is_spam = bool(matched) or link_count >= 3
    return is_spam, "; ".join(reasons)[:500] if is_spam else None


class OperationsStore:
    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            database_url, pool_pre_ping=True, connect_args=connect_args
        )

    def initialize_schema(self) -> None:
        metadata.create_all(self.engine)
        existing = {column["name"] for column in inspect(self.engine).get_columns("leads")}
        source_added = "source" not in existing
        additions = {
            "source": "VARCHAR(200) NOT NULL DEFAULT 'Website'",
            "is_spam": "INTEGER NOT NULL DEFAULT 0",
            "spam_reason": "VARCHAR(500)",
            "deleted_at": "TIMESTAMP WITH TIME ZONE",
        }
        with self.engine.begin() as db:
            for name, definition in additions.items():
                if name not in existing:
                    db.execute(text(f"ALTER TABLE leads ADD COLUMN {name} {definition}"))
            if source_added:
                rows = db.execute(select(leads.c.id, leads.c.payload)).mappings()
                for row in rows:
                    payload = json.loads(row["payload"])
                    source = lead_source(payload)
                    is_spam, reason = classify_spam(payload)
                    db.execute(
                        update(leads)
                        .where(leads.c.id == row["id"])
                        .values(source=source, is_spam=int(is_spam), spam_reason=reason)
                    )

    def readiness_probe(self) -> None:
        with self.engine.connect() as db:
            db.execute(select(1)).scalar_one()

    def create_employee(self, employee: EmployeeCreate, *, actor: str) -> EmployeeSummary:
        now = datetime.now(UTC)
        employee_id = str(uuid4())
        values = {
            "id": employee_id,
            "name": employee.name.strip(),
            "email": str(employee.email).lower(),
            "start_date": employee.start_date,
            "work_location": employee.work_location.strip(),
            "classification": employee.classification,
            "role": employee.role.value,
            "federal_contract_applicability": employee.federal_contract_applicability,
            "status": "draft",
            "created_by": actor,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self.engine.begin() as db:
                db.execute(employees.insert().values(**values))
                for task in initial_employee_tasks(employee):
                    db.execute(
                        employee_tasks.insert().values(
                            id=str(uuid4()),
                            employee_id=employee_id,
                            requirement_id=task["requirement_id"],
                            label=task["label"],
                            responsible_party=task["responsible_party"],
                            status="blocked" if task["blocked"] else "pending",
                            due_date=employee.start_date,
                            instructions=task["instructions"],
                            applicability_reason=task["applicability_reason"],
                            evidence_required=int(task["evidence_required"]),
                            rule_version=RULE_VERSION,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                self._audit(
                    db,
                    event="employee.created",
                    actor=actor,
                    subject_type="employee",
                    subject_id=employee_id,
                    payload={
                        "name": values["name"],
                        "email": values["email"],
                        "classification": values["classification"],
                        "role": values["role"],
                    },
                )
        except IntegrityError as error:
            raise ValueError("An employee record already exists for this email") from error
        return EmployeeSummary.model_validate(values)

    def list_employees(self) -> list[EmployeeSummary]:
        with self.engine.connect() as db:
            rows = db.execute(select(employees).order_by(employees.c.name)).mappings().all()
        return [EmployeeSummary.model_validate(dict(row)) for row in rows]

    def get_employee_by_identity(self, email: str, subject: str) -> EmployeeSummary | None:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(employees).where(
                        employees.c.email == email.lower(),
                        employees.c.google_subject == subject,
                        employees.c.status.in_(("active", "onboarding_complete")),
                    )
                )
                .mappings()
                .first()
            )
        return EmployeeSummary.model_validate(dict(row)) if row else None

    def list_employee_tasks(self, employee_id: str) -> list[EmployeeTaskSummary]:
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(employee_tasks)
                    .where(employee_tasks.c.employee_id == employee_id)
                    .order_by(employee_tasks.c.due_date, employee_tasks.c.label)
                )
                .mappings()
                .all()
            )
        return [
            EmployeeTaskSummary.model_validate(
                {**dict(row), "evidence_required": bool(row["evidence_required"])}
            )
            for row in rows
        ]

    def create_employee_invite(
        self,
        employee_id: str,
        *,
        actor: str,
        invite_base_url: str,
        invite_signing_secret: str,
        expires_in_hours: int,
        notification_max_attempts: int,
    ) -> EmployeeInviteReceipt | None:
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=expires_in_hours)
        invite_id = str(uuid4())
        token = employee_invite_token(invite_signing_secret, invite_id)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.begin() as db:
            employee = (
                db.execute(select(employees).where(employees.c.id == employee_id))
                .mappings()
                .first()
            )
            if not employee:
                return None
            db.execute(
                update(employee_invites)
                .where(
                    employee_invites.c.employee_id == employee_id,
                    employee_invites.c.consumed_at.is_(None),
                    employee_invites.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            db.execute(
                employee_invites.insert().values(
                    id=invite_id,
                    employee_id=employee_id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                    created_by=actor,
                    created_at=now,
                )
            )
            db.execute(
                employee_notification_outbox.insert().values(
                    id=str(uuid4()),
                    employee_id=employee_id,
                    destination=employee["email"],
                    payload=json.dumps(
                        {
                            "kind": "employee_invitation",
                            "name": employee["name"],
                            "invite_base_url": invite_base_url.rstrip("/"),
                            "invite_id": invite_id,
                            "expires_at": expires_at.isoformat(),
                        },
                        sort_keys=True,
                    ),
                    status="pending",
                    attempts=0,
                    max_attempts=notification_max_attempts,
                    available_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.execute(
                update(employees)
                .where(employees.c.id == employee_id)
                .values(status="invited", updated_at=now)
            )
            self._audit(
                db,
                event="employee.invited",
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload={"invite_id": invite_id, "expires_at": expires_at.isoformat()},
            )
        return EmployeeInviteReceipt(
            id=invite_id,
            employee_id=employee_id,
            expires_at=expires_at,
        )

    def activate_employee_invite(
        self, token: str, *, email: str, google_subject: str
    ) -> EmployeeSummary:
        now = datetime.now(UTC)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.begin() as db:
            invitation = (
                db.execute(
                    select(employee_invites).where(employee_invites.c.token_hash == token_hash)
                )
                .mappings()
                .first()
            )
            if not invitation:
                raise InvalidEmployeeInvite("Invitation is invalid or no longer available")
            expires_at = invitation["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if invitation["consumed_at"] or invitation["revoked_at"] or expires_at <= now:
                raise InvalidEmployeeInvite("Invitation is invalid or no longer available")
            employee = (
                db.execute(select(employees).where(employees.c.id == invitation["employee_id"]))
                .mappings()
                .one()
            )
            if employee["email"] != email.lower():
                raise InvalidEmployeeInvite("Invitation does not match the signed-in account")
            already_bound = db.execute(
                select(employees.c.id).where(
                    employees.c.google_subject == google_subject,
                    employees.c.id != employee["id"],
                )
            ).first()
            if already_bound:
                raise InvalidEmployeeInvite("Google account is already linked to another employee")
            consumed = db.execute(
                update(employee_invites)
                .where(
                    employee_invites.c.id == invitation["id"],
                    employee_invites.c.consumed_at.is_(None),
                    employee_invites.c.revoked_at.is_(None),
                )
                .values(consumed_at=now)
            )
            if consumed.rowcount != 1:
                raise InvalidEmployeeInvite("Invitation is invalid or no longer available")
            db.execute(
                update(employees)
                .where(employees.c.id == employee["id"])
                .values(status="active", google_subject=google_subject, updated_at=now)
            )
            self._audit(
                db,
                event="employee.invitation_accepted",
                actor=email.lower(),
                subject_type="employee",
                subject_id=employee["id"],
                payload={"invite_id": invitation["id"]},
            )
            updated = dict(employee)
            updated.update(status="active", google_subject=google_subject, updated_at=now)
        return EmployeeSummary.model_validate(updated)

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
                        "urgency": lead.urgency,
                        "city": lead.city,
                        "message": lead.message,
                    },
                    sort_keys=True,
                )
                destinations = [] if is_spam else [("email", notification_email_to)]
                if not is_spam and lead.urgency == "emergency" and emergency_sms_to:
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
                                & (employee_notification_outbox.c.locked_at <= stale_before)
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
        return employee_notification_outbox if outbox_type == "employee" else notification_outbox

    def mark_notification_sent(
        self, notification_id: str, provider_message_id: str, *, outbox_type: str = "lead"
    ) -> None:
        now = datetime.now(UTC)
        outbox = self._outbox(outbox_type)
        with self.engine.begin() as db:
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
                db.execute(select(leads).where(leads.c.id == lead_id, leads.c.deleted_at.is_(None)))
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

    def update_lead(self, lead_id: str, change: LeadUpdate, *, actor: str) -> dict[str, Any] | None:
        values = change.model_dump(exclude_none=True, exclude={"note"})
        if "assigned_to" in values:
            values["assigned_to"] = str(values["assigned_to"]).lower()
        if "email" in values:
            values["email"] = str(values["email"]).lower()
        if "is_spam" in values:
            values["is_spam"] = int(values["is_spam"])
            values["spam_reason"] = None if not values["is_spam"] else "Marked as spam by staff"
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            existing = (
                db.execute(select(leads).where(leads.c.id == lead_id, leads.c.deleted_at.is_(None)))
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
                        if key not in {"updated_at", "payload"} and existing[key] != value
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
                db.execute(select(leads).where(leads.c.id == lead_id, leads.c.deleted_at.is_(None)))
                .mappings()
                .first()
            )
            if not existing:
                return False
            db.execute(
                update(leads).where(leads.c.id == lead_id).values(deleted_at=now, updated_at=now)
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
