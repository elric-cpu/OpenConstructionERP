from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .onboarding_domain import EmployeeDocumentSummary
from .onboarding_lifecycle_store import OnboardingLifecycleStore
from .store_base import StoreBase
from .storage_schema import (
    InvalidEmployeeTaskTransition,
    employee_documents,
    employee_tasks,
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
        return {
            "task": dict(task),
            "version": int(latest_version or 0) + 1,
            "data_classification": task["data_classification"],
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
        actor_party: str,
        expected_version: int,
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
            allowed_parties = (
                {"employee", "contractor"}
                if actor_party == "employee"
                else {"employer"}
            )
            if task["responsible_party"] not in allowed_parties:
                raise InvalidEmployeeTaskTransition(
                    "The signed-in role cannot submit evidence for this task"
                )
            expected_method = (
                "employer_evidence" if actor_party == "employer" else "document_upload"
            )
            if task["completion_method"] != expected_method:
                raise InvalidEmployeeTaskTransition(
                    "This task does not accept uploaded evidence from this role"
                )
            if task["status"] not in {"pending", "rejected"}:
                raise InvalidEmployeeTaskTransition(
                    f"Evidence cannot be uploaded while task is {task['status']}"
                )
            OnboardingLifecycleStore(self.engine).guard_task_version(
                db, task_id, expected_version, now=now
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
            OnboardingLifecycleStore(self.engine).record_submission(
                db,
                employee_id=employee_id,
                task_id=task_id,
                evidence_type="document",
                evidence_id=document_id,
                submitted_by=actor,
                now=now,
            )
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
