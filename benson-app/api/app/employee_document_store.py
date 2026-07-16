from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .domain import EmployeeDocumentSummary, EmployeeTaskSummary
from .store_base import StoreBase
from .storage_schema import (
    InvalidEmployeeTaskTransition,
    employee_documents,
    employee_tasks,
    employees,
)


class EmployeeDocumentStoreMixin(StoreBase):
    def employee_document_upload_context(
        self, employee_id: str, task_id: str
    ) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            task = (
                db.execute(
                    select(employee_tasks).where(
                        employee_tasks.c.id == task_id,
                        employee_tasks.c.employee_id == employee_id,
                    )
                )
                .mappings()
                .first()
            )
            if not task:
                return None
            latest_version = db.execute(
                select(func.max(employee_documents.c.version)).where(
                    employee_documents.c.task_id == task_id
                )
            ).scalar_one()
        highly_restricted = {
            "form-i9",
            "federal-w4",
            "oregon-w4",
            "payroll-enrollment",
            "payment-election",
            "contractor-w9",
        }
        return {
            "task": dict(task),
            "version": int(latest_version or 0) + 1,
            "data_classification": (
                "highly_restricted"
                if task["requirement_id"] in highly_restricted
                else "restricted"
            ),
        }

    def add_employee_document(
        self,
        *,
        employee_id: str,
        task_id: str,
        version: int,
        original_name: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        data_classification: str,
        nonce_base64: str,
        key_version: str,
        actor: str,
    ) -> EmployeeDocumentSummary:
        now = datetime.now(UTC)
        document_id = str(uuid4())
        with self.engine.begin() as db:
            task = (
                db.execute(
                    select(employee_tasks).where(
                        employee_tasks.c.id == task_id,
                        employee_tasks.c.employee_id == employee_id,
                    )
                )
                .mappings()
                .first()
            )
            if not task:
                raise InvalidEmployeeTaskTransition("Onboarding task not found")
            if task["responsible_party"] not in {"employee", "contractor"}:
                raise InvalidEmployeeTaskTransition(
                    "This task is completed by Benson staff"
                )
            if task["status"] not in {"pending", "rejected"}:
                raise InvalidEmployeeTaskTransition(
                    f"Evidence cannot be uploaded while task is {task['status']}"
                )
            db.execute(
                update(employee_documents)
                .where(
                    employee_documents.c.task_id == task_id,
                    employee_documents.c.status == "active",
                )
                .values(status="superseded")
            )
            try:
                db.execute(
                    employee_documents.insert().values(
                        id=document_id,
                        employee_id=employee_id,
                        task_id=task_id,
                        version=version,
                        original_name=original_name,
                        storage_key=storage_key,
                        content_type=content_type,
                        size_bytes=size_bytes,
                        sha256=sha256,
                        data_classification=data_classification,
                        nonce_base64=nonce_base64,
                        key_version=key_version,
                        status="active",
                        uploaded_by=actor,
                        created_at=now,
                    )
                )
            except IntegrityError as error:
                raise InvalidEmployeeTaskTransition(
                    "A newer evidence version was uploaded; refresh and try again"
                ) from error
            db.execute(
                update(employee_tasks)
                .where(employee_tasks.c.id == task_id)
                .values(status="submitted", updated_at=now)
            )
            self._audit(
                db,
                event="employee.document_uploaded",
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload={
                    "document_id": document_id,
                    "task_id": task_id,
                    "version": version,
                    "data_classification": data_classification,
                },
            )
        return EmployeeDocumentSummary(
            id=document_id,
            employee_id=employee_id,
            task_id=task_id,
            version=version,
            original_name=original_name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            data_classification=data_classification,
            status="active",
            uploaded_by=actor,
            created_at=now,
        )

    def list_employee_documents(
        self, employee_id: str
    ) -> list[EmployeeDocumentSummary]:
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(employee_documents)
                    .where(employee_documents.c.employee_id == employee_id)
                    .order_by(employee_documents.c.created_at.desc())
                )
                .mappings()
                .all()
            )
        return [EmployeeDocumentSummary.model_validate(dict(row)) for row in rows]

    def get_employee_document(self, document_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(employee_documents).where(
                        employee_documents.c.id == document_id
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def audit_employee_document_access(
        self, document_id: str, *, employee_id: str, actor: str
    ) -> None:
        with self.engine.begin() as db:
            self._audit(
                db,
                event="employee.document_accessed",
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload={"document_id": document_id},
            )

    def review_employee_task(
        self, employee_id: str, task_id: str, *, decision: str, comment: str, actor: str
    ) -> EmployeeTaskSummary | None:
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            task = (
                db.execute(
                    select(employee_tasks).where(
                        employee_tasks.c.id == task_id,
                        employee_tasks.c.employee_id == employee_id,
                    )
                )
                .mappings()
                .first()
            )
            if not task:
                return None
            if decision == "complete":
                if task["status"] == "blocked":
                    raise InvalidEmployeeTaskTransition(
                        "Blocked compliance tasks require applicability approval first"
                    )
                evidence_exists = db.execute(
                    select(func.count())
                    .select_from(employee_documents)
                    .where(
                        employee_documents.c.task_id == task_id,
                        employee_documents.c.status == "active",
                    )
                ).scalar_one()
                if task["evidence_required"] and not evidence_exists:
                    raise InvalidEmployeeTaskTransition(
                        "Required evidence has not been submitted"
                    )
                status_value = "completed"
                completed_at = now
                completed_by = actor
            elif decision == "reject":
                if task["status"] != "submitted":
                    raise InvalidEmployeeTaskTransition(
                        "Only submitted tasks can be rejected"
                    )
                status_value = "rejected"
                completed_at = None
                completed_by = None
            else:
                status_value = "not_applicable"
                completed_at = now
                completed_by = actor
            db.execute(
                update(employee_tasks)
                .where(employee_tasks.c.id == task_id)
                .values(
                    status=status_value,
                    completed_at=completed_at,
                    completed_by=completed_by,
                    updated_at=now,
                )
            )
            self._audit(
                db,
                event=f"employee.task_{status_value}",
                actor=actor,
                subject_type="employee",
                subject_id=employee_id,
                payload={"task_id": task_id, "comment": comment},
            )
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
        tasks = {str(item.id): item for item in self.list_employee_tasks(employee_id)}
        return tasks[task_id]
