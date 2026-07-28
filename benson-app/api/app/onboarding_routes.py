from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response as BinaryResponse

from .auth import Principal, require_employee, require_owner
from .config import Settings, get_settings
from .dependencies import store
from .onboarding_domain import (
    EmployeeDocumentSummary,
    EmployeeSignatureSummary,
    EmployeeSummary,
    OnboardingEmployeeSummary,
    OnboardingTaskSummary,
    VersionedApplicabilityReview,
    VersionedSignatureCreate,
    VersionedTaskReview,
)
from .onboarding_authorization import require_manage_employee_data
from .onboarding_lifecycle_store import OnboardingLifecycleStore, StaleOnboardingVersion
from .object_storage import (
    delete_upload,
    detect_upload_type,
    read_employee_document,
    store_employee_document,
)
from .storage import InvalidEmployeeTaskTransition

router = APIRouter()
_allowed_upload_types = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def _require_task_access(
    settings: Settings, principal: Principal, employee_id: str, task_id: str
) -> dict[str, Any]:
    task = OnboardingLifecycleStore(store(settings).engine).task_row(
        employee_id, task_id
    )
    if not task:
        raise HTTPException(status_code=404, detail="Onboarding record not found")
    require_manage_employee_data(principal, str(task["data_category"]))
    return task


def _require_all_task_access(
    settings: Settings, principal: Principal, employee_id: str
) -> None:
    rows = OnboardingLifecycleStore(store(settings).engine).list_task_rows(employee_id)
    for task in rows:
        require_manage_employee_data(principal, str(task["data_category"]))


@router.get("/api/benson/v1/onboarding/me", response_model=EmployeeSummary)
def onboarding_me(
    principal: Principal = Depends(require_employee),
    settings: Settings = Depends(get_settings),
) -> EmployeeSummary:
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee:
        raise HTTPException(status_code=403, detail="Active employee account required")
    return employee


@router.get("/api/benson/v1/onboarding/tasks")
def onboarding_tasks(
    principal: Principal = Depends(require_employee),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee:
        raise HTTPException(status_code=403, detail="Active employee account required")
    lifecycle = OnboardingLifecycleStore(store(settings).engine)
    tasks = [
        OnboardingTaskSummary.model_validate(row)
        for row in lifecycle.list_task_rows(str(employee.id))
    ]
    versioned_employee = OnboardingEmployeeSummary.model_validate(
        lifecycle.employee_row(str(employee.id))
    )
    applicable = [task for task in tasks if task.status != "not_applicable"]
    completed = sum(task.status == "completed" for task in applicable)
    return {
        "default_view": "tasks",
        "employee": versioned_employee,
        "tasks": tasks,
        "progress": {"completed": completed, "total": len(applicable)},
    }


@router.get(
    "/api/benson/v1/employees/{employee_id}/tasks",
    response_model=list[OnboardingTaskSummary],
)
def employee_tasks_for_review(
    employee_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[OnboardingTaskSummary]:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = OnboardingLifecycleStore(store(settings).engine).list_task_rows(employee_id)
    for task in rows:
        require_manage_employee_data(principal, str(task["data_category"]))
    return [OnboardingTaskSummary.model_validate(row) for row in rows]


async def _upload_task_evidence(
    *,
    employee_id: str,
    task_id: str,
    file: UploadFile,
    actor: str,
    actor_party: str,
    expected_version: int,
    settings: Settings,
) -> EmployeeDocumentSummary:
    operations = store(settings)
    context = operations.employee_document_upload_context(employee_id, task_id)
    if not context:
        raise HTTPException(status_code=404, detail="Onboarding task not found")
    task = context["task"]
    expected_parties = (
        {"employee", "contractor"} if actor_party == "employee" else {"employer"}
    )
    expected_method = (
        "document_upload" if actor_party == "employee" else "employer_evidence"
    )
    if (
        task["responsible_party"] not in expected_parties
        or task["completion_method"] != expected_method
    ):
        raise HTTPException(
            status_code=409,
            detail="The signed-in role cannot submit evidence for this task",
        )
    if task["status"] not in {"pending", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail=f"Evidence cannot be uploaded while task is {task['status']}",
        )
    content = await file.read(settings.upload_max_bytes + 1)
    if not content or len(content) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=413, detail="Evidence file is empty or too large"
        )
    content_type = detect_upload_type(content)
    if not content_type or content_type not in _allowed_upload_types:
        raise HTTPException(
            status_code=415, detail="Evidence must be PDF, JPEG, PNG, or WebP"
        )
    safe_name = Path(file.filename or "evidence").name[:500]
    try:
        storage_key, digest, nonce, key_version = await run_in_threadpool(
            store_employee_document,
            settings,
            employee_id=employee_id,
            task_id=task_id,
            version=context["version"],
            data_classification=context["data_classification"],
            original_name=safe_name,
            content_type=content_type,
            content=content,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=503, detail="Employee document encryption is unavailable"
        ) from error
    try:
        return operations.add_employee_document(
            employee_id=employee_id,
            task_id=task_id,
            version=context["version"],
            original_name=safe_name,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            data_classification=context["data_classification"],
            nonce_base64=nonce,
            key_version=key_version,
            actor=actor,
            actor_party=actor_party,
            expected_version=expected_version,
        )
    except (InvalidEmployeeTaskTransition, StaleOnboardingVersion) as error:
        await run_in_threadpool(delete_upload, settings, storage_key)
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/api/benson/v1/onboarding/tasks/{task_id}/evidence",
    response_model=EmployeeDocumentSummary,
    status_code=201,
)
async def upload_onboarding_evidence(
    task_id: str,
    file: Annotated[UploadFile, File()],
    expected_version: Annotated[int, Form(ge=1)],
    principal: Principal = Depends(require_employee),
    settings: Settings = Depends(get_settings),
) -> EmployeeDocumentSummary:
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee:
        raise HTTPException(status_code=403, detail="Active employee account required")
    return await _upload_task_evidence(
        employee_id=str(employee.id),
        task_id=task_id,
        file=file,
        actor=principal.email,
        actor_party="employee",
        expected_version=expected_version,
        settings=settings,
    )


@router.post(
    "/api/benson/v1/employees/{employee_id}/tasks/{task_id}/evidence",
    response_model=EmployeeDocumentSummary,
    status_code=201,
)
async def upload_employer_task_evidence(
    employee_id: str,
    task_id: str,
    file: Annotated[UploadFile, File()],
    expected_version: Annotated[int, Form(ge=1)],
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> EmployeeDocumentSummary:
    _require_task_access(settings, principal, employee_id, task_id)
    return await _upload_task_evidence(
        employee_id=employee_id,
        task_id=task_id,
        file=file,
        actor=principal.email,
        actor_party="employer",
        expected_version=expected_version,
        settings=settings,
    )


@router.get(
    "/api/benson/v1/onboarding/documents", response_model=list[EmployeeDocumentSummary]
)
def onboarding_documents(
    principal: Principal = Depends(require_employee),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeDocumentSummary]:
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee:
        raise HTTPException(status_code=403, detail="Active employee account required")
    return store(settings).list_employee_documents(str(employee.id))


@router.get(
    "/api/benson/v1/onboarding/signatures",
    response_model=list[EmployeeSignatureSummary],
)
def onboarding_signatures(
    principal: Principal = Depends(require_employee),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeSignatureSummary]:
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee:
        raise HTTPException(status_code=403, detail="Active employee account required")
    return store(settings).list_employee_signatures(str(employee.id))


@router.post(
    "/api/benson/v1/onboarding/tasks/{task_id}/signature",
    response_model=EmployeeSignatureSummary,
    status_code=201,
)
def sign_onboarding_task(
    task_id: str,
    signature: VersionedSignatureCreate,
    principal: Principal = Depends(require_employee),
    settings: Settings = Depends(get_settings),
) -> EmployeeSignatureSummary:
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee or not principal.subject:
        raise HTTPException(status_code=403, detail="Active employee account required")
    try:
        result = store(settings).submit_employee_signature(
            str(employee.id),
            task_id,
            signer_email=principal.email,
            signer_subject=principal.subject,
            typed_name=signature.typed_name,
            expected_version=signature.expected_version,
        )
    except (InvalidEmployeeTaskTransition, StaleOnboardingVersion) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not result:
        raise HTTPException(status_code=404, detail="Onboarding task not found")
    return result


@router.get(
    "/api/benson/v1/employees/{employee_id}/documents",
    response_model=list[EmployeeDocumentSummary],
)
def employee_documents_for_review(
    employee_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeDocumentSummary]:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    _require_all_task_access(settings, principal, employee_id)
    return store(settings).list_employee_documents(employee_id)


@router.get(
    "/api/benson/v1/employees/{employee_id}/signatures",
    response_model=list[EmployeeSignatureSummary],
)
def employee_signatures_for_review(
    employee_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeSignatureSummary]:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    _require_all_task_access(settings, principal, employee_id)
    return store(settings).list_employee_signatures(employee_id)


async def employee_document_response(
    document_id: str, *, employee_id: str, actor: str, settings: Settings
) -> BinaryResponse:
    operations = store(settings)
    document = operations.get_employee_document(document_id)
    if not document or document["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Employee document not found")
    try:
        content = await run_in_threadpool(
            read_employee_document,
            settings,
            storage_key=document["storage_key"],
            employee_id=document["employee_id"],
            task_id=document["task_id"],
            version=document["version"],
            data_classification=document["data_classification"],
            nonce_base64=document["nonce_base64"],
            key_version=document["key_version"],
        )
    except ValueError as error:
        raise HTTPException(
            status_code=503, detail="Employee document cannot be decrypted"
        ) from error
    operations.audit_employee_document_access(
        document_id, employee_id=employee_id, actor=actor
    )
    safe_name = Path(str(document["original_name"])).name.replace('"', "")
    return BinaryResponse(
        content,
        media_type=str(document["content_type"]),
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.get("/api/benson/v1/onboarding/documents/{document_id}")
async def download_onboarding_document(
    document_id: str,
    principal: Principal = Depends(require_employee),
    settings: Settings = Depends(get_settings),
) -> BinaryResponse:
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee:
        raise HTTPException(status_code=403, detail="Active employee account required")
    return await employee_document_response(
        document_id,
        employee_id=str(employee.id),
        actor=principal.email,
        settings=settings,
    )


@router.get("/api/benson/v1/employees/{employee_id}/documents/{document_id}")
async def download_employee_document(
    employee_id: str,
    document_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> BinaryResponse:
    document = store(settings).get_employee_document(document_id)
    if not document or document["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Employee document not found")
    _require_task_access(settings, principal, employee_id, str(document["task_id"]))
    return await employee_document_response(
        document_id, employee_id=employee_id, actor=principal.email, settings=settings
    )


@router.patch(
    "/api/benson/v1/employees/{employee_id}/tasks/{task_id}/applicability",
    response_model=OnboardingTaskSummary,
)
def review_employee_task_applicability(
    employee_id: str,
    task_id: str,
    review: VersionedApplicabilityReview,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> OnboardingTaskSummary:
    _require_task_access(settings, principal, employee_id, task_id)
    try:
        task = store(settings).decide_employee_task_applicability(
            employee_id,
            task_id,
            decision=review.decision,
            comment=review.comment,
            reviewer_name=review.reviewer_name,
            reviewer_qualification=review.reviewer_qualification,
            actor=principal.email,
            expected_version=review.expected_version,
        )
    except (InvalidEmployeeTaskTransition, StaleOnboardingVersion) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not task:
        raise HTTPException(status_code=404, detail="Onboarding task not found")
    return task


@router.patch(
    "/api/benson/v1/employees/{employee_id}/tasks/{task_id}",
    response_model=OnboardingTaskSummary,
)
def review_employee_task(
    employee_id: str,
    task_id: str,
    review: VersionedTaskReview,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> OnboardingTaskSummary:
    _require_task_access(settings, principal, employee_id, task_id)
    try:
        task = store(settings).review_employee_task(
            employee_id,
            task_id,
            decision=review.decision,
            comment=review.comment,
            actor=principal.email,
            expected_version=review.expected_version,
        )
    except (InvalidEmployeeTaskTransition, StaleOnboardingVersion) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not task:
        raise HTTPException(status_code=404, detail="Onboarding task not found")
    return task
