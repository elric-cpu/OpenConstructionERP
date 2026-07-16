import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .compliance import RULE_VERSION, initial_employee_tasks
from .domain import (
    EmployeeCreate,
    EmployeeInviteReceipt,
    EmployeeSummary,
    EmployeeTaskSummary,
)
from .signing import employee_invite_token
from .store_base import StoreBase
from .storage_schema import (
    InvalidEmployeeInvite,
    employee_invites,
    employee_notification_outbox,
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
            "invite_delivery_email": str(
                employee.invite_delivery_email or employee.email
            ).lower(),
            "start_date": employee.start_date,
            "work_location": employee.work_location.strip(),
            "classification": employee.classification,
            "role": employee.role.value,
            "federal_contract_applicability": employee.federal_contract_applicability,
            "status": "draft",
            "workspace_account_status": (
                "unlicensed_attested"
                if employee.workspace_unlicensed_confirmed
                else "external_unlicensed_required"
            ),
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
            if employee["workspace_account_status"] != "unlicensed_attested":
                raise InvalidEmployeeInvite(
                    "Confirm the Workspace account exists without a paid license before inviting"
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
            db.execute(
                employee_notification_outbox.insert().values(
                    id=str(uuid4()),
                    employee_id=employee_id,
                    destination=employee["invite_delivery_email"] or employee["email"],
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
