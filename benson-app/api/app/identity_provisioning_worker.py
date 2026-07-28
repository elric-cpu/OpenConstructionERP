import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection, Engine, RowMapping

from .directory_provider import DirectoryProvider, DirectoryProviderError
from .onboarding_lifecycle_store import StaleOnboardingVersion
from .onboarding_schema import (
    identity_provisioning_attempts,
    identity_provisioning_commands,
    onboarding_employee_versions,
)
from .storage_schema import audit_events, employees
from .sealed_secret import seal_secret


class IdentityProvisioningWorker:
    def __init__(
        self,
        engine: Engine,
        provider: DirectoryProvider,
        encryption_key: bytes | None = None,
    ):
        self.engine = engine
        self.provider = provider
        self.encryption_key = encryption_key

    def process_one(self, *, worker: str) -> dict[str, Any] | None:
        reconciled = self._reconcile_stale(worker=worker)
        if reconciled:
            return reconciled
        claimed = self._claim(worker=worker)
        if not claimed:
            return None
        employee = self._employee_for_command(claimed["employee_id"])
        if not employee:
            return self._finish_error(
                claimed, worker=worker, code="employee_missing", status="failed"
            )
        try:
            if claimed["kind"] == "create":
                given_name, family_name = self._split_name(employee["name"])
                created_identity = self.provider.create_identity(
                    primary_email=employee["email"],
                    given_name=given_name,
                    family_name=family_name,
                    recovery_email=employee["invite_delivery_email"],
                    org_unit_path=claimed["target_org_unit"],
                )
                identity = self.provider.verify_identity(
                    primary_email=employee["email"],
                    org_unit_path=claimed["target_org_unit"],
                )
                status = {
                    "verified": "verified",
                    "verification_unavailable": "admin_confirmation_required",
                    "paid_license_detected": "failed",
                    "mismatch": "failed",
                }[identity.verification_status]
            else:
                identity = self.provider.suspend_identity(
                    primary_email=employee["email"]
                )
                status = (
                    "suspended"
                    if identity.suspended and identity.verification_status == "verified"
                    else "failed"
                )
        except DirectoryProviderError as error:
            if self._is_retriable(error.code):
                return self._schedule_retry(
                    claimed, worker=worker, provider_code=error.code
                )
            return self._finish_error(
                claimed, worker=worker, code=error.code, status="failed"
            )
        bootstrap_credential = None
        if claimed["kind"] == "create" and created_identity.bootstrap_password:
            if self.encryption_key is None:
                return self._finish_error(
                    claimed,
                    worker=worker,
                    code="credential_encryption_unavailable",
                    status="failed",
                )
            bootstrap_credential = seal_secret(
                created_identity.bootstrap_password,
                self.encryption_key,
                context=str(claimed["id"]),
            )
        result = self._finish(
            claimed,
            worker=worker,
            status=status,
            external_user_id=identity.external_user_id,
            provider_code=identity.provider_code,
            details={
                "org_unit_matches": identity.org_unit_path
                == claimed["target_org_unit"],
                "suspended": identity.suspended,
                "verification_status": identity.verification_status,
            },
            bootstrap_credential=bootstrap_credential,
        )
        if claimed["kind"] == "create" and status == "verified":
            result["bootstrap_password"] = created_identity.bootstrap_password
        return result

    def _claim(self, *, worker: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            candidates = (
                db.execute(
                    select(identity_provisioning_commands)
                    .where(
                        identity_provisioning_commands.c.status == "approved",
                        identity_provisioning_commands.c.available_at <= now,
                    )
                    .order_by(identity_provisioning_commands.c.created_at)
                    .limit(5)
                )
                .mappings()
                .all()
            )
            for command in candidates:
                changed = db.execute(
                    update(identity_provisioning_commands)
                    .where(
                        identity_provisioning_commands.c.id == command["id"],
                        identity_provisioning_commands.c.status == "approved",
                        identity_provisioning_commands.c.version == command["version"],
                    )
                    .values(
                        status="executing",
                        version=command["version"] + 1,
                        executed_by=worker,
                        locked_at=now,
                        updated_at=now,
                    )
                )
                if changed.rowcount == 1:
                    values = dict(command)
                    values.update(
                        status="executing",
                        version=command["version"] + 1,
                        executed_by=worker,
                        locked_at=now,
                        updated_at=now,
                    )
                    return values
        return None

    def _reconcile_stale(self, *, worker: str) -> dict[str, Any] | None:
        stale_before = datetime.now(UTC) - timedelta(minutes=15)
        with self.engine.connect() as db:
            command = (
                db.execute(
                    select(identity_provisioning_commands)
                    .where(
                        identity_provisioning_commands.c.status == "executing",
                        identity_provisioning_commands.c.locked_at < stale_before,
                    )
                    .order_by(identity_provisioning_commands.c.locked_at)
                    .limit(1)
                )
                .mappings()
                .first()
            )
        if not command:
            return None
        employee = self._employee_for_command(command["employee_id"])
        if not employee:
            return self._finish_error(
                dict(command), worker=worker, code="employee_missing", status="failed"
            )
        try:
            identity = self.provider.verify_identity(
                primary_email=employee["email"],
                org_unit_path=command["target_org_unit"],
            )
        except DirectoryProviderError as error:
            if error.code == "directory_user_missing":
                return self._schedule_retry(
                    dict(command), worker=worker, provider_code=error.code
                )
            return self._finish_error(
                dict(command), worker=worker, code=error.code, status="failed"
            )
        if command["kind"] == "suspend":
            if identity.suspended:
                return self._finish(
                    dict(command),
                    worker=worker,
                    status="suspended",
                    external_user_id=identity.external_user_id,
                    provider_code="reconciled_suspended",
                    details={"reconciled": True, "suspended": True},
                )
            return self._schedule_retry(
                dict(command), worker=worker, provider_code="suspension_not_observed"
            )
        status = {
            "verified": "verified",
            "verification_unavailable": "admin_confirmation_required",
            "paid_license_detected": "failed",
            "mismatch": "failed",
        }[identity.verification_status]
        return self._finish(
            dict(command),
            worker=worker,
            status=status,
            external_user_id=identity.external_user_id,
            provider_code=f"reconciled:{identity.provider_code}",
            details={
                "reconciled": True,
                "verification_status": identity.verification_status,
            },
        )

    def _schedule_retry(
        self, command: dict[str, Any], *, worker: str, provider_code: str
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            attempt = self._next_attempt(db, command["id"])
            terminal = attempt >= 5
            delay_minutes = min(2 ** (attempt - 1), 60)
            available_at = now + timedelta(minutes=delay_minutes)
            changed = db.execute(
                update(identity_provisioning_commands)
                .where(
                    identity_provisioning_commands.c.id == command["id"],
                    identity_provisioning_commands.c.status == "executing",
                    identity_provisioning_commands.c.version == command["version"],
                )
                .values(
                    status="manual_review_required" if terminal else "approved",
                    version=command["version"] + 1,
                    failure_code="ambiguous_provider_outcome",
                    available_at=now if terminal else available_at,
                    locked_at=None,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise StaleOnboardingVersion(
                    "Provisioning command changed during reconciliation"
                )
            self._attempt(
                db,
                command_id=command["id"],
                attempt=attempt,
                result="manual_review_required" if terminal else "retry_scheduled",
                provider_code=provider_code,
                details={"reconciled": True},
                now=now,
            )
            self._audit(
                db,
                event=(
                    "employee.identity_provisioning_manual_review_required"
                    if terminal
                    else "employee.identity_provisioning_retry_scheduled"
                ),
                actor=worker,
                employee_id=command["employee_id"],
                command_id=command["id"],
                now=now,
            )
        values = dict(command)
        values.update(
            status="manual_review_required" if terminal else "approved",
            version=command["version"] + 1,
            failure_code="ambiguous_provider_outcome",
            available_at=now if terminal else available_at,
            locked_at=None,
            updated_at=now,
        )
        return values

    def _finish_error(
        self,
        command: dict[str, Any],
        *,
        worker: str,
        code: str,
        status: str,
    ) -> dict[str, Any]:
        return self._finish(
            command,
            worker=worker,
            status=status,
            external_user_id=None,
            provider_code=code,
            details={"verification_status": "provider_error"},
        )

    def _finish(
        self,
        command: dict[str, Any],
        *,
        worker: str,
        status: str,
        external_user_id: str | None,
        provider_code: str,
        details: dict[str, Any],
        bootstrap_credential: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            attempt = self._next_attempt(db, command["id"])
            changed = db.execute(
                update(identity_provisioning_commands)
                .where(
                    identity_provisioning_commands.c.id == command["id"],
                    identity_provisioning_commands.c.status == "executing",
                    identity_provisioning_commands.c.version == command["version"],
                )
                .values(
                    status=status,
                    version=command["version"] + 1,
                    external_user_id=external_user_id,
                    failure_code=None
                    if status in {"verified", "suspended"}
                    else provider_code,
                    bootstrap_credential=bootstrap_credential,
                    locked_at=None,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise StaleOnboardingVersion(
                    "Provisioning command changed while the provider was responding"
                )
            self._attempt(
                db,
                command_id=command["id"],
                attempt=attempt,
                result=status,
                provider_code=provider_code,
                details=details,
                now=now,
            )
            if status == "verified":
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
                        onboarding_employee_versions.c.employee_id
                        == command["employee_id"]
                    )
                    .values(
                        version=onboarding_employee_versions.c.version + 1,
                        updated_at=now,
                    )
                )
            self._audit(
                db,
                event=f"employee.identity_provisioning_{status}",
                actor=worker,
                employee_id=command["employee_id"],
                command_id=command["id"],
                now=now,
            )
        values = dict(command)
        values.update(
            status=status,
            version=command["version"] + 1,
            external_user_id=external_user_id,
            failure_code=None if status in {"verified", "suspended"} else provider_code,
            locked_at=None,
            updated_at=now,
        )
        return values

    def _employee_for_command(self, employee_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = self._employee(db, employee_id)
        return dict(row) if row else None

    @staticmethod
    def _employee(db: Connection, employee_id: str) -> RowMapping | None:
        return (
            db.execute(select(employees).where(employees.c.id == employee_id))
            .mappings()
            .first()
        )

    @staticmethod
    def _next_attempt(db: Connection, command_id: str) -> int:
        latest = db.execute(
            select(func.max(identity_provisioning_attempts.c.attempt)).where(
                identity_provisioning_attempts.c.command_id == command_id
            )
        ).scalar_one()
        return int(latest or 0) + 1

    @staticmethod
    def _attempt(
        db: Connection,
        *,
        command_id: str,
        attempt: int,
        result: str,
        provider_code: str,
        details: dict[str, Any],
        now: datetime,
    ) -> None:
        db.execute(
            identity_provisioning_attempts.insert().values(
                id=str(uuid4()),
                command_id=command_id,
                attempt=attempt,
                result=result,
                provider_code=provider_code,
                details=json.dumps(details, sort_keys=True),
                occurred_at=now,
            )
        )

    @staticmethod
    def _split_name(name: str) -> tuple[str, str]:
        given, separator, family = name.strip().partition(" ")
        return given, family if separator else "Team Member"

    @staticmethod
    def _is_retriable(code: str) -> bool:
        return code.endswith(("_408", "_409", "_429", "_500", "_502", "_503", "_504"))

    @staticmethod
    def _audit(
        db: Connection,
        *,
        event: str,
        actor: str,
        employee_id: str,
        command_id: str,
        now: datetime,
    ) -> None:
        db.execute(
            audit_events.insert().values(
                id=str(uuid4()),
                event=event,
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload=json.dumps({"command_id": command_id}, sort_keys=True),
                occurred_at=now,
            )
        )
