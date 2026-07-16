from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response as BinaryResponse

from .auth import Principal, require_employee, require_owner, verify_google_identity
from .compliance import ONBOARDING_REQUIREMENTS
from .config import Settings, get_settings
from .dependencies import store
from .domain import (
    EmployeeCreate,
    EmployeeDocumentSummary,
    EmployeeInviteActivation,
    EmployeeInviteReceipt,
    EmployeeSignatureCreate,
    EmployeeSignatureSummary,
    EmployeeSummary,
    EmployeeTaskApplicabilityReview,
    EmployeeTaskReview,
    EmployeeTaskSummary,
)
from .object_storage import (
    delete_upload,
    detect_upload_type,
    read_employee_document,
    store_employee_document,
)
from .storage import (
    InvalidEmployeeInvite,
    InvalidEmployeeTaskTransition,
)

router = APIRouter()
_allowed_upload_types = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


@router.get("/api/benson/v1/onboarding/requirements")
async def onboarding_requirements(
    _principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    return {
        "review_status": "pending_qualified_hr_legal_review",
        "requirements": [
            item.model_dump(mode="json") for item in ONBOARDING_REQUIREMENTS
        ],
    }


@router.get("/api/benson/v1/employees", response_model=list[EmployeeSummary])
def list_employees(
    _principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeSummary]:
    return store(settings).list_employees()


@router.post(
    "/api/benson/v1/employees", response_model=EmployeeSummary, status_code=201
)
def create_employee(
    employee: EmployeeCreate,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> EmployeeSummary:
    if employee.classification == "employee":
        email_domain = str(employee.email).lower().partition("@")[2]
        if email_domain != settings.staff_google_domain.lower():
            raise HTTPException(
                status_code=422,
                detail=f"Employees must use an @{settings.staff_google_domain} Workspace email",
            )
    try:
        return store(settings).create_employee(employee, actor=principal.email)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/api/benson/v1/employees/{employee_id}/invite",
    response_model=EmployeeInviteReceipt,
    status_code=202,
)
def invite_employee(
    employee_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> EmployeeInviteReceipt:
    try:
        invitation = store(settings).create_employee_invite(
            employee_id,
            actor=principal.email,
            invite_base_url=str(settings.upload_base_url),
            invite_signing_secret=settings.employee_invite_signing_secret,
            expires_in_hours=72,
            notification_max_attempts=settings.notification_max_attempts,
        )
    except InvalidEmployeeInvite as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not invitation:
        raise HTTPException(status_code=404, detail="Employee not found")
    return invitation


@router.post("/api/benson/v1/onboarding/activate", response_model=EmployeeSummary)
def activate_employee_invitation(
    activation: EmployeeInviteActivation,
    settings: Settings = Depends(get_settings),
) -> EmployeeSummary:
    claims = verify_google_identity(activation.credential, settings)
    hosted_domain = str(claims.get("hd", "")).lower()
    if (
        not claims.get("email_verified")
        or not claims.get("email")
        or not claims.get("sub")
        or hosted_domain != settings.staff_google_domain.lower()
    ):
        raise HTTPException(
            status_code=403,
            detail="Managed Benson Workspace account required",
        )
    try:
        return store(settings).activate_employee_invite(
            activation.token,
            email=str(claims["email"]),
            google_subject=str(claims["sub"]),
        )
    except InvalidEmployeeInvite as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
    tasks = store(settings).list_employee_tasks(str(employee.id))
    applicable = [task for task in tasks if task.status != "not_applicable"]
    completed = sum(task.status == "completed" for task in applicable)
    return {
        "default_view": "tasks",
        "employee": employee,
        "tasks": tasks,
        "progress": {"completed": completed, "total": len(applicable)},
    }


@router.get(
    "/api/benson/v1/employees/{employee_id}/tasks",
    response_model=list[EmployeeTaskSummary],
)
def employee_tasks_for_review(
    employee_id: str,
    _principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeTaskSummary]:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return store(settings).list_employee_tasks(employee_id)


async def _upload_task_evidence(
    *,
    employee_id: str,
    task_id: str,
    file: UploadFile,
    actor: str,
    actor_party: str,
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
        )
    except InvalidEmployeeTaskTransition as error:
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
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> EmployeeDocumentSummary:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return await _upload_task_evidence(
        employee_id=employee_id,
        task_id=task_id,
        file=file,
        actor=principal.email,
        actor_party="employer",
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
    signature: EmployeeSignatureCreate,
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
        )
    except InvalidEmployeeTaskTransition as error:
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
    _principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeDocumentSummary]:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return store(settings).list_employee_documents(employee_id)


@router.get(
    "/api/benson/v1/employees/{employee_id}/signatures",
    response_model=list[EmployeeSignatureSummary],
)
def employee_signatures_for_review(
    employee_id: str,
    _principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[EmployeeSignatureSummary]:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
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
    return await employee_document_response(
        document_id, employee_id=employee_id, actor=principal.email, settings=settings
    )


@router.patch(
    "/api/benson/v1/employees/{employee_id}/tasks/{task_id}/applicability",
    response_model=EmployeeTaskSummary,
)
def review_employee_task_applicability(
    employee_id: str,
    task_id: str,
    review: EmployeeTaskApplicabilityReview,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> EmployeeTaskSummary:
    try:
        task = store(settings).decide_employee_task_applicability(
            employee_id,
            task_id,
            decision=review.decision,
            comment=review.comment,
            reviewer_name=review.reviewer_name,
            reviewer_qualification=review.reviewer_qualification,
            actor=principal.email,
        )
    except InvalidEmployeeTaskTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not task:
        raise HTTPException(status_code=404, detail="Onboarding task not found")
    return task


@router.patch(
    "/api/benson/v1/employees/{employee_id}/tasks/{task_id}",
    response_model=EmployeeTaskSummary,
)
def review_employee_task(
    employee_id: str,
    task_id: str,
    review: EmployeeTaskReview,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> EmployeeTaskSummary:
    try:
        task = store(settings).review_employee_task(
            employee_id,
            task_id,
            decision=review.decision,
            comment=review.comment,
            actor=principal.email,
        )
    except InvalidEmployeeTaskTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not task:
        raise HTTPException(status_code=404, detail="Onboarding task not found")
    return task
