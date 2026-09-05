import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection, RowMapping

from .domain import EmployeeSignatureSummary, EmployeeTaskSummary
from .store_base import StoreBase
from .storage_schema import (
    InvalidEmployeeTaskTransition,
    employee_documents,
    employee_signatures,
    employee_tasks,
    employees,
)


class EmployeeTaskStoreMixin(StoreBase):
    def decide_employee_task_applicability(
        self,
        employee_id: str,
        task_id: str,
        *,
        decision: str,
        comment: str,
        reviewer_name: str,
        reviewer_qualification: str,
        actor: str,
    ) -> EmployeeTaskSummary | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            task = self._task_for_update(db, employee_id, task_id)
            if not task:
                return None
            if not task["applicability_review_required"]:
                raise InvalidEmployeeTaskTransition(
                    "This task does not permit an applicability override"
                )
            if task["applicability_status"] != "pending_review":
                raise InvalidEmployeeTaskTransition(
                    "Task applicability has already been decided"
                )
            applicable = decision == "applicable"
            status = "pending" if applicable else "not_applicable"
            db.execute(
                update(employee_tasks)
                .where(employee_tasks.c.id == task_id)
                .values(
                    status=status,
                    applicability_status=(
                        "applied" if applicable else "not_applicable"
                    ),
                    applicability_reason=(
                        "Qualified review marked this requirement applicable."
                        if applicable
                        else "Qualified review marked this requirement not applicable."
                    ),
                    legal_review_status="approved",
                    applicability_decided_at=now,
                    applicability_decided_by=actor,
                    completed_at=None if applicable else now,
                    completed_by=None if applicable else actor,
                    updated_at=now,
                )
            )
            self._audit(
                db,
                event="employee.task_applicability_decided",
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload={
                    "task_id": task_id,
                    "requirement_id": task["requirement_id"],
                    "decision": decision,
                    "comment": comment,
                    "reviewer_name": reviewer_name,
                    "reviewer_qualification": reviewer_qualification,
                    "official_source": task["official_source"],
                    "rule_version": task["rule_version"],
                },
            )
            self._update_employee_completion(db, employee_id, now)
        return self._task_summary(employee_id, task_id)

    def submit_employee_signature(
        self,
        employee_id: str,
        task_id: str,
        *,
        signer_email: str,
        signer_subject: str,
        typed_name: str,
    ) -> EmployeeSignatureSummary | None:
        now = datetime.now(UTC)
        signature_id = str(uuid4())
        with self.engine.begin() as db:
            employee = (
                db.execute(select(employees).where(employees.c.id == employee_id))
                .mappings()
                .first()
            )
            task = self._task_for_update(db, employee_id, task_id)
            if not employee or not task:
                return None
            if task["completion_method"] != "employee_signature":
                raise InvalidEmployeeTaskTransition(
                    "This task does not accept an electronic acknowledgement"
                )
            if task["status"] not in {"pending", "rejected"}:
                raise InvalidEmployeeTaskTransition(
                    f"Task cannot be signed while it is {task['status']}"
                )
            if self._normalized_name(typed_name) != self._normalized_name(
                employee["name"]
            ):
                raise InvalidEmployeeTaskTransition(
                    "Typed name must match the employee record"
                )
            statement = task["signature_statement"]
            if not statement:
                raise InvalidEmployeeTaskTransition(
                    "The approved acknowledgement statement is unavailable"
                )
            latest = db.execute(
                select(func.max(employee_signatures.c.version)).where(
                    employee_signatures.c.task_id == task_id
                )
            ).scalar_one()
            version = int(latest or 0) + 1
            db.execute(
                update(employee_signatures)
                .where(
                    employee_signatures.c.task_id == task_id,
                    employee_signatures.c.status == "active",
                )
                .values(status="superseded")
            )
            statement_hash = hashlib.sha256(statement.encode()).hexdigest()
            values = {
                "id": signature_id,
                "employee_id": employee_id,
                "task_id": task_id,
                "version": version,
                "signer_email": signer_email.lower(),
                "signer_subject_hash": hashlib.sha256(
                    signer_subject.encode()
                ).hexdigest(),
                "typed_name": typed_name.strip(),
                "statement_version": task["rule_version"],
                "statement_text": statement,
                "statement_hash": statement_hash,
                "status": "active",
                "signed_at": now,
            }
            db.execute(employee_signatures.insert().values(**values))
            db.execute(
                update(employee_tasks)
                .where(employee_tasks.c.id == task_id)
                .values(status="submitted", updated_at=now)
            )
            self._audit(
                db,
                event="employee.task_signed",
                actor=signer_email.lower(),
                subject_type="employee",
                subject_id=employee_id,
                payload={
                    "task_id": task_id,
                    "signature_id": signature_id,
                    "version": version,
                    "statement_hash": statement_hash,
                    "statement_version": task["rule_version"],
                },
            )
        return EmployeeSignatureSummary.model_validate(values)

    def list_employee_signatures(
        self, employee_id: str
    ) -> list[EmployeeSignatureSummary]:
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(employee_signatures)
                    .where(employee_signatures.c.employee_id == employee_id)
                    .order_by(employee_signatures.c.signed_at.desc())
                )
                .mappings()
                .all()
            )
        return [EmployeeSignatureSummary.model_validate(dict(row)) for row in rows]

    def review_employee_task(
        self,
        employee_id: str,
        task_id: str,
        *,
        decision: str,
        comment: str,
        actor: str,
    ) -> EmployeeTaskSummary | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            task = self._task_for_update(db, employee_id, task_id)
            if not task:
                return None
            if task["status"] == "blocked":
                raise InvalidEmployeeTaskTransition(
                    "Blocked compliance tasks require applicability approval first"
                )
            if decision == "complete":
                self._require_completion_evidence(db, task_id, task)
                status = "completed"
                completed_at = now
                completed_by = actor
            else:
                if task["status"] != "submitted":
                    raise InvalidEmployeeTaskTransition(
                        "Only submitted tasks can be rejected"
                    )
                status = "rejected"
                completed_at = None
                completed_by = None
            db.execute(
                update(employee_tasks)
                .where(employee_tasks.c.id == task_id)
                .values(
                    status=status,
                    completed_at=completed_at,
                    completed_by=completed_by,
                    updated_at=now,
                )
            )
            self._audit(
                db,
                event=f"employee.task_{status}",
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload={"task_id": task_id, "comment": comment},
            )
            self._update_employee_completion(db, employee_id, now)
        return self._task_summary(employee_id, task_id)

    def _require_completion_evidence(
        self, db: Connection, task_id: str, task: RowMapping
    ) -> None:
        if task["completion_method"] == "manual_review":
            return
        if task["status"] != "submitted":
            raise InvalidEmployeeTaskTransition(
                "Task must be submitted before it can be completed"
            )
        if task["completion_method"] == "employee_signature":
            evidence = db.execute(
                select(func.count())
                .select_from(employee_signatures)
                .where(
                    employee_signatures.c.task_id == task_id,
                    employee_signatures.c.status == "active",
                )
            ).scalar_one()
        else:
            evidence = db.execute(
                select(func.count())
                .select_from(employee_documents)
                .where(
                    employee_documents.c.task_id == task_id,
                    employee_documents.c.status == "active",
                )
            ).scalar_one()
        if not evidence:
            raise InvalidEmployeeTaskTransition(
                "Required evidence has not been submitted"
            )

    def _task_for_update(
        self, db: Connection, employee_id: str, task_id: str
    ) -> RowMapping | None:
        return (
            db.execute(
                select(employee_tasks).where(
                    employee_tasks.c.id == task_id,
                    employee_tasks.c.employee_id == employee_id,
                )
            )
            .mappings()
            .first()
        )

    def _task_summary(self, employee_id: str, task_id: str) -> EmployeeTaskSummary:
        tasks = {str(item.id): item for item in self.list_employee_tasks(employee_id)}
        return tasks[task_id]

    def _update_employee_completion(
        self, db: Connection, employee_id: str, now: datetime
    ) -> None:
        remaining = db.execute(
            select(func.count())
            .select_from(employee_tasks)
            .where(
                employee_tasks.c.employee_id == employee_id,
                employee_tasks.c.status.not_in(("completed", "not_applicable")),
            )
        ).scalar_one()
        if remaining == 0:
            db.execute(
                update(employees)
                .where(employees.c.id == employee_id)
                .values(status="onboarding_complete", updated_at=now)
            )

    @staticmethod
    def _normalized_name(value: str) -> str:
        return " ".join(value.split()).casefold()
