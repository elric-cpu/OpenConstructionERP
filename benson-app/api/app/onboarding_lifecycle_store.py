import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection, Engine, RowMapping

from .compliance import ONBOARDING_REQUIREMENTS, RULE_VERSION
from .onboarding_schema import (
    identity_provisioning_commands,
    onboarding_employee_versions,
    onboarding_offboarding_events,
    onboarding_retention_holds,
    onboarding_rule_versions,
    onboarding_task_reviews,
    onboarding_task_submissions,
    onboarding_task_versions,
)
from .storage_schema import (
    audit_events,
    employee_documents,
    employee_invites,
    employee_signatures,
    employee_tasks,
    employees,
)


class StaleOnboardingVersion(ValueError):
    pass


class InvalidOnboardingLifecycle(ValueError):
    pass


class OnboardingLifecycleStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def ensure_rule_version(self, db: Connection, *, now: datetime) -> None:
        snapshot = json.dumps(
            [item.model_dump(mode="json") for item in ONBOARDING_REQUIREMENTS],
            sort_keys=True,
            separators=(",", ":"),
        )
        exists = db.execute(
            select(onboarding_rule_versions.c.id).where(
                onboarding_rule_versions.c.id == RULE_VERSION
            )
        ).first()
        if not exists:
            db.execute(
                onboarding_rule_versions.insert().values(
                    id=RULE_VERSION,
                    status=(
                        "pending_legal_review"
                        if "pending-legal-review" in RULE_VERSION
                        else "approved"
                    ),
                    requirements_digest=hashlib.sha256(snapshot.encode()).hexdigest(),
                    requirements_snapshot=snapshot,
                    created_at=now,
                )
            )

    def initialize_employee(
        self, db: Connection, *, employee_id: str, task_ids: list[str], now: datetime
    ) -> None:
        self.ensure_rule_version(db, now=now)
        db.execute(
            onboarding_employee_versions.insert().values(
                employee_id=employee_id, version=1, updated_at=now
            )
        )
        if task_ids:
            db.execute(
                onboarding_task_versions.insert(),
                [
                    {
                        "task_id": task_id,
                        "employee_id": employee_id,
                        "version": 1,
                        "updated_at": now,
                    }
                    for task_id in task_ids
                ],
            )

    def list_employee_rows(self) -> list[dict[str, Any]]:
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(employees, onboarding_employee_versions.c.version)
                    .join(
                        onboarding_employee_versions,
                        onboarding_employee_versions.c.employee_id == employees.c.id,
                    )
                    .order_by(employees.c.name)
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def employee_row(self, employee_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(employees, onboarding_employee_versions.c.version)
                    .join(
                        onboarding_employee_versions,
                        onboarding_employee_versions.c.employee_id == employees.c.id,
                    )
                    .where(employees.c.id == employee_id)
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def list_task_rows(self, employee_id: str) -> list[dict[str, Any]]:
        latest_rejection = (
            select(onboarding_task_reviews.c.comment)
            .where(
                onboarding_task_reviews.c.task_id == employee_tasks.c.id,
                onboarding_task_reviews.c.decision == "reject",
            )
            .order_by(onboarding_task_reviews.c.created_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(
                        employee_tasks,
                        onboarding_task_versions.c.version,
                        latest_rejection.label("latest_rejection_reason"),
                    )
                    .join(
                        onboarding_task_versions,
                        onboarding_task_versions.c.task_id == employee_tasks.c.id,
                    )
                    .where(employee_tasks.c.employee_id == employee_id)
                    .order_by(employee_tasks.c.due_date, employee_tasks.c.label)
                )
                .mappings()
                .all()
            )
        return [
            {**dict(row), "evidence_required": bool(row["evidence_required"])}
            for row in rows
        ]

    def task_row(self, employee_id: str, task_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(employee_tasks, onboarding_task_versions.c.version)
                    .join(
                        onboarding_task_versions,
                        onboarding_task_versions.c.task_id == employee_tasks.c.id,
                    )
                    .where(
                        employee_tasks.c.id == task_id,
                        employee_tasks.c.employee_id == employee_id,
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def guard_employee_version(
        self, db: Connection, employee_id: str, expected_version: int, *, now: datetime
    ) -> int:
        result = db.execute(
            update(onboarding_employee_versions)
            .where(
                onboarding_employee_versions.c.employee_id == employee_id,
                onboarding_employee_versions.c.version == expected_version,
            )
            .values(version=expected_version + 1, updated_at=now)
        )
        if result.rowcount != 1:
            raise StaleOnboardingVersion(
                "Employee record changed; refresh and try again"
            )
        return expected_version + 1

    def guard_task_version(
        self, db: Connection, task_id: str, expected_version: int, *, now: datetime
    ) -> int:
        result = db.execute(
            update(onboarding_task_versions)
            .where(
                onboarding_task_versions.c.task_id == task_id,
                onboarding_task_versions.c.version == expected_version,
            )
            .values(version=expected_version + 1, updated_at=now)
        )
        if result.rowcount != 1:
            raise StaleOnboardingVersion(
                "Onboarding task changed; refresh and try again"
            )
        return expected_version + 1

    def record_review(
        self,
        db: Connection,
        *,
        task: RowMapping,
        to_status: str,
        review_type: str,
        decision: str,
        comment: str,
        reviewer_email: str,
        reviewer_name: str | None,
        reviewer_qualification: str | None,
        task_version: int,
        now: datetime,
    ) -> None:
        db.execute(
            onboarding_task_reviews.insert().values(
                id=str(uuid4()),
                employee_id=task["employee_id"],
                task_id=task["id"],
                review_type=review_type,
                from_status=task["status"],
                to_status=to_status,
                decision=decision,
                comment=comment,
                reviewer_email=reviewer_email,
                reviewer_name=reviewer_name,
                reviewer_qualification=reviewer_qualification,
                rule_version=task["rule_version"],
                task_version=task_version,
                created_at=now,
            )
        )

    def record_submission(
        self,
        db: Connection,
        *,
        employee_id: str,
        task_id: str,
        evidence_type: str,
        evidence_id: str,
        submitted_by: str,
        now: datetime,
    ) -> int:
        latest = db.execute(
            select(func.max(onboarding_task_submissions.c.submission_version)).where(
                onboarding_task_submissions.c.task_id == task_id
            )
        ).scalar_one()
        version = int(latest or 0) + 1
        db.execute(
            onboarding_task_submissions.insert().values(
                id=str(uuid4()),
                employee_id=employee_id,
                task_id=task_id,
                evidence_type=evidence_type,
                evidence_id=evidence_id,
                submission_version=version,
                submitted_by=submitted_by,
                created_at=now,
            )
        )
        return version

    def list_reviews(self, employee_id: str, task_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(onboarding_task_reviews)
                    .where(
                        onboarding_task_reviews.c.employee_id == employee_id,
                        onboarding_task_reviews.c.task_id == task_id,
                    )
                    .order_by(onboarding_task_reviews.c.created_at.desc())
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def create_retention_hold(
        self,
        employee_id: str,
        *,
        expected_version: int,
        reason: str,
        actor: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        hold_id = str(uuid4())
        with self.engine.begin() as db:
            employee = self._employee_for_update(db, employee_id)
            if not employee:
                raise InvalidOnboardingLifecycle("Employee not found")
            self.guard_employee_version(db, employee_id, expected_version, now=now)
            values = {
                "id": hold_id,
                "employee_id": employee_id,
                "reason": reason,
                "created_by": actor,
                "created_at": now,
            }
            db.execute(onboarding_retention_holds.insert().values(**values))
            self._audit(
                db,
                event="employee.retention_hold_created",
                actor=actor,
                employee_id=employee_id,
                payload={"hold_id": hold_id},
                now=now,
            )
        return values

    def release_retention_hold(
        self,
        employee_id: str,
        hold_id: str,
        *,
        expected_version: int,
        actor: str,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            hold = (
                db.execute(
                    select(onboarding_retention_holds).where(
                        onboarding_retention_holds.c.id == hold_id,
                        onboarding_retention_holds.c.employee_id == employee_id,
                        onboarding_retention_holds.c.released_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
            if not hold:
                return None
            self.guard_employee_version(db, employee_id, expected_version, now=now)
            db.execute(
                update(onboarding_retention_holds)
                .where(onboarding_retention_holds.c.id == hold_id)
                .values(released_by=actor, released_at=now)
            )
            self._audit(
                db,
                event="employee.retention_hold_released",
                actor=actor,
                employee_id=employee_id,
                payload={"hold_id": hold_id},
                now=now,
            )
            values = dict(hold)
            values.update(released_by=actor, released_at=now)
        return values

    def offboard(
        self,
        employee_id: str,
        *,
        expected_version: int,
        reason: str,
        directory_idempotency_key: str,
        target_org_unit: str,
        actor: str,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        event_id = str(uuid4())
        with self.engine.begin() as db:
            employee = self._employee_for_update(db, employee_id)
            if not employee:
                return None
            if employee["status"] == "inactive":
                raise InvalidOnboardingLifecycle("Employee is already inactive")
            version = self.guard_employee_version(
                db, employee_id, expected_version, now=now
            )
            directory_command_id: str | None = None
            if employee["classification"] == "employee":
                directory_command_id = str(uuid4())
                db.execute(
                    identity_provisioning_commands.insert().values(
                        id=directory_command_id,
                        employee_id=employee_id,
                        kind="suspend",
                        status="approved",
                        version=1,
                        idempotency_key=directory_idempotency_key,
                        target_email=employee["email"],
                        target_org_unit=target_org_unit,
                        requested_by=actor,
                        approved_by=actor,
                        available_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.execute(
                update(employees)
                .where(employees.c.id == employee_id)
                .values(status="inactive", updated_at=now)
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
                onboarding_offboarding_events.insert().values(
                    id=event_id,
                    employee_id=employee_id,
                    reason=reason,
                    previous_status=employee["status"],
                    session_revoked_at=now,
                    directory_command_id=directory_command_id,
                    actor=actor,
                    occurred_at=now,
                )
            )
            self._audit(
                db,
                event="employee.offboarded",
                actor=actor,
                employee_id=employee_id,
                payload={
                    "from_status": employee["status"],
                    "to_status": "inactive",
                    "directory_command_id": directory_command_id,
                },
                now=now,
            )
        return {
            "id": event_id,
            "employee_id": employee_id,
            "version": version,
            "directory_command_id": directory_command_id,
            "session_revoked_at": now,
        }

    @staticmethod
    def _employee_for_update(db: Connection, employee_id: str) -> RowMapping | None:
        return (
            db.execute(select(employees).where(employees.c.id == employee_id))
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


def task_has_active_evidence(db: Connection, task_id: str) -> bool:
    documents = db.execute(
        select(func.count())
        .select_from(employee_documents)
        .where(
            employee_documents.c.task_id == task_id,
            employee_documents.c.status == "active",
        )
    ).scalar_one()
    signatures = db.execute(
        select(func.count())
        .select_from(employee_signatures)
        .where(
            employee_signatures.c.task_id == task_id,
            employee_signatures.c.status == "active",
        )
    ).scalar_one()
    return bool(documents or signatures)
