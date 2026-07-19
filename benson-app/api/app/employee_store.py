import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .compliance import RULE_VERSION, initial_employee_tasks
from .onboarding_domain import (
    EmployeeCreate,
    EmployeeSummary,
    EmployeeTaskSummary,
    OnboardingInviteReceipt,
)
from .identity_provisioning_store import IdentityProvisioningStore
from .onboarding_lifecycle_store import OnboardingLifecycleStore
from .onboarding_schema import (
    identity_provisioning_commands,
    onboarding_employee_versions,
    onboarding_offboarding_events,
    onboarding_retention_holds,
    onboarding_task_reviews,
    onboarding_task_submissions,
)
from .signing import employee_invite_token
from .sealed_secret import seal_secret
from .store_base import StoreBase
from .storage_schema import (
    InvalidEmployeeInvite,
    employee_documents,
    employee_invites,
    employee_notification_outbox,
    employee_signatures,
    employee_tasks,
    employees,
)


class EmployeeStoreMixin(StoreBase):
    def create_employee(
        self, employee: EmployeeCreate, *, actor: str
    ) -> EmployeeSummary:
        now = datetime.now(UTC)
        employee_id = str(uuid4())
        values = {
            "id": employee_id,
            "name": employee.name.strip(),
            "email": str(employee.email).lower(),
            "invite_delivery_email": str(employee.invite_delivery_email).lower(),
            "start_date": employee.start_date,
            "work_location": employee.work_location.strip(),
            "classification": employee.classification,
            "role": employee.role.value,
            "federal_contract_applicability": employee.federal_contract_applicability,
            "status": "draft",
            "workspace_account_status": "external_unlicensed_required",
            "phone": employee.phone,
            "created_by": actor,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self.engine.begin() as db:
                db.execute(employees.insert().values(**values))
                task_ids: list[str] = []
                for task in initial_employee_tasks(employee):
                    task_id = str(uuid4())
                    task_ids.append(task_id)
                    db.execute(
                        employee_tasks.insert().values(
                            id=task_id,
                            employee_id=employee_id,
                            requirement_id=task["requirement_id"],
                            label=task["label"],
                            responsible_party=task["responsible_party"],
                            status=task["status"],
                            due_date=task["due_date"],
                            instructions=task["instructions"],
                            applicability_reason=task["applicability_reason"],
                            evidence_required=int(task["evidence_required"]),
                            completion_method=task["completion_method"],
                            applicability_review_required=int(
                                task["applicability_review_required"]
                            ),
                            applicability_status=task["applicability_status"],
                            retention_rule=task["retention_rule"],
                            data_classification=task["data_classification"],
                            data_category=task["data_category"],
                            official_source=task["official_source"],
                            legal_review_status=task["legal_review_status"],
                            signature_statement=task["signature_statement"],
                            completed_at=(
                                now if task["status"] == "not_applicable" else None
                            ),
                            completed_by=(
                                actor if task["status"] == "not_applicable" else None
                            ),
                            applicability_decided_at=(
                                now if task["status"] == "not_applicable" else None
                            ),
                            applicability_decided_by=(
                                actor if task["status"] == "not_applicable" else None
                            ),
                            rule_version=RULE_VERSION,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                OnboardingLifecycleStore(self.engine).initialize_employee(
                    db, employee_id=employee_id, task_ids=task_ids, now=now
                )
                self._audit(
                    db,
                    event="employee.created",
                    actor=actor,
                    subject_type="employee",
                    subject_id=employee_id,
                    payload={
                        "classification": values["classification"],
                        "role": values["role"],
                        "rule_version": RULE_VERSION,
                    },
                )
        except IntegrityError as error:
            raise ValueError(
                "An employee record already exists for this email"
            ) from error
        return EmployeeSummary.model_validate(values)

    def list_employees(self) -> list[EmployeeSummary]:
        with self.engine.connect() as db:
            rows = (
                db.execute(select(employees).order_by(employees.c.name))
                .mappings()
                .all()
            )
        return [EmployeeSummary.model_validate(dict(row)) for row in rows]

    def get_employee(self, employee_id: str) -> EmployeeSummary | None:
        with self.engine.connect() as db:
            row = (
                db.execute(select(employees).where(employees.c.id == employee_id))
                .mappings()
                .first()
            )
        return EmployeeSummary.model_validate(dict(row)) if row else None

    def get_employee_by_identity(
        self, email: str, subject: str
    ) -> EmployeeSummary | None:
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

    def delete_employee(self, employee_id: str, *, actor: str) -> bool:
        with self.engine.begin() as db:
            # Fetch employee for audit (non-PII fields) and existence check
            employee_row = (
                db.execute(
                    select(employees.c.classification, employees.c.role).where(
                        employees.c.id == employee_id
                    )
                )
                .mappings()
                .first()
            )
            if not employee_row:
                return False

            # Delete from dependent tables in correct order
            db.execute(
                employee_tasks.delete().where(
                    employee_tasks.c.employee_id == employee_id
                )
            )
            db.execute(
                employee_documents.delete().where(
                    employee_documents.c.employee_id == employee_id
                )
            )
            db.execute(
                employee_signatures.delete().where(
                    employee_signatures.c.employee_id == employee_id
                )
            )
            db.execute(
                employee_invites.delete().where(
                    employee_invites.c.employee_id == employee_id
                )
            )
            db.execute(
                employee_notification_outbox.delete().where(
                    employee_notification_outbox.c.employee_id == employee_id
                )
            )
            db.execute(
                onboarding_offboarding_events.delete().where(
                    onboarding_offboarding_events.c.employee_id == employee_id
                )
            )
            db.execute(
                identity_provisioning_commands.delete().where(
                    identity_provisioning_commands.c.employee_id == employee_id
                )
            )
            db.execute(
                onboarding_employee_versions.delete().where(
                    onboarding_employee_versions.c.employee_id == employee_id
                )
            )
            db.execute(
                onboarding_retention_holds.delete().where(
                    onboarding_retention_holds.c.employee_id == employee_id
                )
            )
            db.execute(
                onboarding_task_reviews.delete().where(
                    onboarding_task_reviews.c.employee_id == employee_id
                )
            )
            db.execute(
                onboarding_task_submissions.delete().where(
                    onboarding_task_submissions.c.employee_id == employee_id
                )
            )

            # Delete employee
            result = db.execute(employees.delete().where(employees.c.id == employee_id))

            # Audit
            self._audit(
                db,
                event="employee.deleted",
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload={
                    "classification": employee_row["classification"],
                    "role": employee_row["role"],
                },
            )

            return result.rowcount > 0

    def create_employee_invite(
        self,
        employee_id: str,
        *,
        actor: str,
        invite_base_url: str,
        invite_signing_secret: str,
        expires_in_hours: int,
        notification_max_attempts: int,
        expected_version: int,
        bootstrap_password: str | None = None,
        encryption_key: bytes | None = None,
    ) -> OnboardingInviteReceipt | None:
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
            if employee["status"] not in {"draft", "invited"}:
                raise InvalidEmployeeInvite(
                    "Invitation is not available for this employee lifecycle state"
                )
            if not IdentityProvisioningStore(self.engine).invitation_is_allowed(
                db, employee
            ):
                raise InvalidEmployeeInvite(
                    "A verified no-paid-license identity is required before inviting"
                )
            version = OnboardingLifecycleStore(self.engine).guard_employee_version(
                db, employee_id, expected_version, now=now
            )
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
            payload = {
                "kind": "employee_invitation",
                "name": employee["name"],
                "workspace_email": employee["email"],
                "invite_base_url": invite_base_url.rstrip("/"),
                "invite_id": invite_id,
                "expires_at": expires_at.isoformat(),
            }
            if bootstrap_password:
                if encryption_key is None:
                    raise InvalidEmployeeInvite(
                        "Invitation credential encryption is unavailable"
                    )
                payload["bootstrap_credential"] = seal_secret(
                    bootstrap_password, encryption_key, context=invite_id
                )
            db.execute(
                employee_notification_outbox.insert().values(
                    id=str(uuid4()),
                    employee_id=employee_id,
                    destination=employee["invite_delivery_email"] or employee["email"],
                    payload=json.dumps(payload, sort_keys=True),
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
        return OnboardingInviteReceipt(
            id=invite_id,
            employee_id=employee_id,
            expires_at=expires_at,
            version=version,
        )

    def employee_invite_context(self, token: str) -> dict[str, str] | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(
                        employees.c.email,
                        employees.c.classification,
                        employee_invites.c.expires_at,
                        employee_invites.c.consumed_at,
                        employee_invites.c.revoked_at,
                    )
                    .join(
                        employee_invites,
                        employee_invites.c.employee_id == employees.c.id,
                    )
                    .where(employee_invites.c.token_hash == token_hash)
                )
                .mappings()
                .first()
            )
        if not row or row["consumed_at"] or row["revoked_at"]:
            return None
        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return None
        return {"email": row["email"], "classification": row["classification"]}

    def activate_employee_invite(
        self, token: str, *, email: str, google_subject: str
    ) -> EmployeeSummary:
        now = datetime.now(UTC)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.begin() as db:
            invitation = (
                db.execute(
                    select(employee_invites).where(
                        employee_invites.c.token_hash == token_hash
                    )
                )
                .mappings()
                .first()
            )
            if not invitation:
                raise InvalidEmployeeInvite(
                    "Invitation is invalid or no longer available"
                )
            expires_at = invitation["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if (
                invitation["consumed_at"]
                or invitation["revoked_at"]
                or expires_at <= now
            ):
                raise InvalidEmployeeInvite(
                    "Invitation is invalid or no longer available"
                )
            employee = (
                db.execute(
                    select(employees).where(employees.c.id == invitation["employee_id"])
                )
                .mappings()
                .one()
            )
            if employee["email"] != email.lower():
                raise InvalidEmployeeInvite(
                    "Invitation does not match the signed-in account"
                )
            already_bound = db.execute(
                select(employees.c.id).where(
                    employees.c.google_subject == google_subject,
                    employees.c.id != employee["id"],
                )
            ).first()
            if already_bound:
                raise InvalidEmployeeInvite(
                    "Google account is already linked to another employee"
                )
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
                raise InvalidEmployeeInvite(
                    "Invitation is invalid or no longer available"
                )
            db.execute(
                update(employees)
                .where(employees.c.id == employee["id"])
                .values(status="active", google_subject=google_subject, updated_at=now)
            )
            db.execute(
                update(onboarding_employee_versions)
                .where(onboarding_employee_versions.c.employee_id == employee["id"])
                .values(
                    version=onboarding_employee_versions.c.version + 1,
                    updated_at=now,
                )
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
            updated.update(
                status="active", google_subject=google_subject, updated_at=now
            )
        return EmployeeSummary.model_validate(updated)
