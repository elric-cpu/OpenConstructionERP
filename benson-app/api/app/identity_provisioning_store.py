import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import IntegrityError

from .onboarding_lifecycle_store import (
    InvalidOnboardingLifecycle,
    OnboardingLifecycleStore,
    StaleOnboardingVersion,
)
from .onboarding_schema import (
    identity_provisioning_commands,
    onboarding_admin_confirmations,
    onboarding_employee_versions,
)
from .storage_schema import audit_events, employees
from .sealed_secret import seal_secret


class IdentityProvisioningStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.lifecycle = OnboardingLifecycleStore(engine)

    def request_create(
        self,
        employee_id: str,
        *,
        expected_version: int,
        idempotency_key: str,
        target_org_unit: str,
        actor: str,
        initial_status: str = "pending_approval",
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        command_id = str(uuid4())
        try:
            with self.engine.begin() as db:
                existing = self._by_idempotency_key(db, idempotency_key)
                if existing:
                    if (
                        existing["employee_id"] != employee_id
                        or existing["kind"] != "create"
                    ):
                        raise InvalidOnboardingLifecycle(
                            "Idempotency key belongs to another provisioning command"
                        )
                    return dict(existing)
                employee = self._employee(db, employee_id)
                if not employee:
                    return None
                if employee["classification"] != "employee":
                    raise InvalidOnboardingLifecycle(
                        "Contractors use their verified external Google identity"
                    )
                if employee["status"] not in {"draft", "invited"}:
                    raise InvalidOnboardingLifecycle(
                        "Identity provisioning is unavailable for this employee lifecycle state"
                    )
                if initial_status not in {"pending_approval", "manual_setup_required"}:
                    raise InvalidOnboardingLifecycle(
                        "Invalid initial provisioning state"
                    )
                self.lifecycle.guard_employee_version(
                    db, employee_id, expected_version, now=now
                )
                values = {
                    "id": command_id,
                    "employee_id": employee_id,
                    "kind": "create",
                    "status": initial_status,
                    "version": 1,
                    "idempotency_key": idempotency_key,
                    "target_email": employee["email"],
                    "target_org_unit": target_org_unit,
                    "requested_by": actor,
                    "available_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
                db.execute(identity_provisioning_commands.insert().values(**values))
                self._audit(
                    db,
                    event="employee.identity_provisioning_requested",
                    actor=actor,
                    employee_id=employee_id,
                    payload={
                        "command_id": command_id,
                        "kind": "create",
                        "status": initial_status,
                    },
                    now=now,
                )
        except IntegrityError as error:
            raise InvalidOnboardingLifecycle(
                "Provisioning command could not be created"
            ) from error
        return values

    def approve(
        self, command_id: str, *, expected_version: int, actor: str
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            command = self._command(db, command_id)
            if not command:
                return None
            if command["status"] != "pending_approval":
                raise InvalidOnboardingLifecycle(
                    "Only pending provisioning commands can be approved"
                )
            changed = db.execute(
                update(identity_provisioning_commands)
                .where(
                    identity_provisioning_commands.c.id == command_id,
                    identity_provisioning_commands.c.status == "pending_approval",
                    identity_provisioning_commands.c.version == expected_version,
                )
                .values(
                    status="approved",
                    version=expected_version + 1,
                    approved_by=actor,
                    available_at=now,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise StaleOnboardingVersion(
                    "Provisioning command changed; refresh and try again"
                )
            values = dict(command)
            values.update(
                status="approved",
                version=expected_version + 1,
                approved_by=actor,
                available_at=now,
                updated_at=now,
            )
            self._audit(
                db,
                event="employee.identity_provisioning_approved",
                actor=actor,
                employee_id=command["employee_id"],
                payload={"command_id": command_id, "kind": command["kind"]},
                now=now,
            )
        return values

    def confirm_unavailable_verification(
        self,
        command_id: str,
        *,
        expected_version: int,
        reason: str,
        evidence_reference: str,
        actor: str,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            command = self._command(db, command_id)
            if not command:
                return None
            if command["status"] != "admin_confirmation_required":
                raise InvalidOnboardingLifecycle(
                    "Administrator confirmation is allowed only when verification is unavailable"
                )
            changed = db.execute(
                update(identity_provisioning_commands)
                .where(
                    identity_provisioning_commands.c.id == command_id,
                    identity_provisioning_commands.c.status
                    == "admin_confirmation_required",
                    identity_provisioning_commands.c.version == expected_version,
                )
                .values(
                    status="admin_confirmed",
                    version=expected_version + 1,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise StaleOnboardingVersion(
                    "Provisioning command changed; refresh and try again"
                )
            db.execute(
                onboarding_admin_confirmations.insert().values(
                    id=str(uuid4()),
                    command_id=command_id,
                    confirmed_by=actor,
                    reason=reason,
                    evidence_reference=evidence_reference,
                    confirmed_at=now,
                )
            )
            db.execute(
                update(employees)
                .where(employees.c.id == command["employee_id"])
                .values(workspace_account_status="unlicensed_attested", updated_at=now)
            )
            db.execute(
                update(onboarding_employee_versions)
                .where(
                    onboarding_employee_versions.c.employee_id == command["employee_id"]
                )
                .values(
                    version=onboarding_employee_versions.c.version + 1,
                    updated_at=now,
                )
            )
            self._audit(
                db,
                event="employee.identity_license_admin_confirmed",
                actor=actor,
                employee_id=command["employee_id"],
                payload={
                    "command_id": command_id,
                    "evidence_reference": evidence_reference,
                },
                now=now,
            )
            values = dict(command)
            values.update(
                status="admin_confirmed",
                version=expected_version + 1,
                updated_at=now,
            )
        return values

    def confirm_manual_setup(
        self,
        command_id: str,
        *,
        expected_version: int,
        reason: str,
        evidence_reference: str,
        bootstrap_password: str,
        encryption_key: bytes,
        actor: str,
        reissue: bool = False,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            command = self._command(db, command_id)
            if not command:
                return None
            allowed = (
                {"admin_confirmed", "verified"}
                if reissue
                else {
                    "manual_setup_required",
                    "admin_confirmation_required",
                }
            )
            if command["status"] not in allowed:
                raise InvalidOnboardingLifecycle(
                    "A fresh Google credential cannot be attached in this provisioning state"
                )
            next_status = command["status"] if reissue else "admin_confirmed"
            encrypted = seal_secret(
                bootstrap_password, encryption_key, context=command_id
            )
            changed = db.execute(
                update(identity_provisioning_commands)
                .where(
                    identity_provisioning_commands.c.id == command_id,
                    identity_provisioning_commands.c.status == command["status"],
                    identity_provisioning_commands.c.version == expected_version,
                )
                .values(
                    status=next_status,
                    version=expected_version + 1,
                    bootstrap_credential=encrypted,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise StaleOnboardingVersion(
                    "Provisioning command changed; refresh and try again"
                )
            if not reissue:
                db.execute(
                    onboarding_admin_confirmations.insert().values(
                        id=str(uuid4()),
                        command_id=command_id,
                        confirmed_by=actor,
                        reason=reason,
                        evidence_reference=evidence_reference,
                        confirmed_at=now,
                    )
                )
                db.execute(
                    update(employees)
                    .where(employees.c.id == command["employee_id"])
                    .values(
                        workspace_account_status="unlicensed_attested", updated_at=now
                    )
                )
            db.execute(
                update(onboarding_employee_versions)
                .where(
                    onboarding_employee_versions.c.employee_id == command["employee_id"]
                )
                .values(
                    version=onboarding_employee_versions.c.version + 1, updated_at=now
                )
            )
            self._audit(
                db,
                event=(
                    "employee.identity_invitation_credential_reissued"
                    if reissue
                    else "employee.identity_manual_setup_confirmed"
                ),
                actor=actor,
                employee_id=command["employee_id"],
                payload={
                    "command_id": command_id,
                    "evidence_reference": evidence_reference,
                    "confirmed_no_paid_license": True,
                },
                now=now,
            )
            values = dict(command)
            values.update(
                status=next_status,
                version=expected_version + 1,
                bootstrap_credential=encrypted,
                updated_at=now,
            )
        return values

    def retry(
        self, command_id: str, *, expected_version: int, actor: str
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            command = self._command(db, command_id)
            if not command:
                return None
            if command["status"] not in {"failed", "manual_review_required"}:
                raise InvalidOnboardingLifecycle(
                    "Only failed or manual-review commands can be retried"
                )
            changed = db.execute(
                update(identity_provisioning_commands)
                .where(
                    identity_provisioning_commands.c.id == command_id,
                    identity_provisioning_commands.c.version == expected_version,
                    identity_provisioning_commands.c.status == command["status"],
                )
                .values(
                    status="approved",
                    version=expected_version + 1,
                    failure_code=None,
                    available_at=now,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise StaleOnboardingVersion(
                    "Provisioning command changed; refresh and try again"
                )
            self._audit(
                db,
                event="employee.identity_provisioning_retry_approved",
                actor=actor,
                employee_id=command["employee_id"],
                payload={"command_id": command_id},
                now=now,
            )
            values = dict(command)
            values.update(
                status="approved",
                version=expected_version + 1,
                failure_code=None,
                available_at=now,
                updated_at=now,
            )
        return values

    def get(self, command_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = self._command(db, command_id)
        return dict(row) if row else None

    def list_for_employee(self, employee_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(identity_provisioning_commands)
                    .where(identity_provisioning_commands.c.employee_id == employee_id)
                    .order_by(identity_provisioning_commands.c.created_at.desc())
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    @staticmethod
    def invitation_is_allowed(db: Connection, employee: RowMapping) -> bool:
        if employee["classification"] == "independent_contractor":
            return True
        verified = db.execute(
            select(func.count())
            .select_from(identity_provisioning_commands)
            .where(
                identity_provisioning_commands.c.employee_id == employee["id"],
                identity_provisioning_commands.c.kind == "create",
                identity_provisioning_commands.c.status.in_(
                    ("verified", "admin_confirmed")
                ),
            )
        ).scalar_one()
        return bool(verified)

    @staticmethod
    def _employee(db: Connection, employee_id: str) -> RowMapping | None:
        return (
            db.execute(select(employees).where(employees.c.id == employee_id))
            .mappings()
            .first()
        )

    @staticmethod
    def _command(db: Connection, command_id: str) -> RowMapping | None:
        return (
            db.execute(
                select(identity_provisioning_commands).where(
                    identity_provisioning_commands.c.id == command_id
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    def _by_idempotency_key(db: Connection, key: str) -> RowMapping | None:
        return (
            db.execute(
                select(identity_provisioning_commands).where(
                    identity_provisioning_commands.c.idempotency_key == key
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    def _audit(
        db: Connection,
        *,
        event: str,
        actor: str,
        employee_id: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        db.execute(
            audit_events.insert().values(
                id=str(uuid4()),
                event=event,
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload=json.dumps(payload, sort_keys=True),
                occurred_at=now,
            )
        )
