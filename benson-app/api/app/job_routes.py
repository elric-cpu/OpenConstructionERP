from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import (
    Principal,
    require_delivery_staff,
    require_job_staff,
    require_operations_staff,
)
from .config import Settings, get_settings
from .dependencies import store
from .domain import JobCreateFromEstimate, JobSummary, JobTransition, JobUpdate, Role

router = APIRouter(prefix="/api/benson/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummary])
def list_jobs(
    status_filter: Annotated[str, Query(alias="status")] = "",
    _principal: Principal = Depends(require_job_staff),
    settings: Settings = Depends(get_settings),
) -> list[JobSummary]:
    return store(settings).list_jobs(
        status=status_filter, actor=_principal.email, role=_principal.role
    )


def _validate_assignee(email: object, settings: Settings) -> None:
    if email and str(email) not in {
        member["email"] for member in settings.assignable_staff()
    }:
        raise HTTPException(status_code=422, detail="Assigned staff must be authorized")


@router.post(
    "/from-estimate/{estimate_id}",
    response_model=JobSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    estimate_id: str,
    plan: JobCreateFromEstimate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> JobSummary:
    _validate_assignee(plan.assigned_to, settings)
    try:
        return store(settings).create_job_from_estimate(
            estimate_id, plan, actor=principal.email
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{job_id}", response_model=JobSummary)
def update_job(
    job_id: str,
    change: JobUpdate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> JobSummary:
    if not change.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=400, detail="At least one job change is required"
        )
    _validate_assignee(change.assigned_to, settings)
    try:
        job = store(settings).update_job(job_id, change, actor=principal.email)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if job is None:
        raise HTTPException(status_code=404, detail="Editable job not found")
    return job


@router.post("/{job_id}/transition", response_model=JobSummary)
def transition_job(
    job_id: str,
    transition: JobTransition,
    principal: Principal = Depends(require_delivery_staff),
    settings: Settings = Depends(get_settings),
) -> JobSummary:
    if transition.status == "cancelled" and principal.role not in {
        Role.OWNER,
        Role.ADMIN,
    }:
        raise HTTPException(status_code=403, detail="Owner approval required")
    if transition.status in {"on_hold", "completed", "cancelled"} and not (
        transition.note.strip()
    ):
        raise HTTPException(status_code=422, detail="A factual note is required")
    try:
        job = store(settings).transition_job(
            job_id,
            target=transition.status,
            actor=principal.email,
            note=transition.note,
            restrict_to_assignee=principal.role is Role.FIELD,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/audit")
def job_audit(
    job_id: str,
    _principal: Principal = Depends(require_job_staff),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    events = store(settings).list_job_audit(
        job_id, actor=_principal.email, role=_principal.role
    )
    if events is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return events
