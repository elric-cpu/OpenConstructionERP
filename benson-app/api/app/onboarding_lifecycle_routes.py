from fastapi import APIRouter, Depends, HTTPException, Response

from .auth import Principal, require_owner
from .config import Settings, get_settings
from .dependencies import store
from .onboarding_authorization import require_manage_employee_data
from .onboarding_domain import (
    OffboardingReceipt,
    OffboardingRequest,
    RetentionHoldCreate,
    RetentionHoldRelease,
    RetentionHoldSummary,
    TaskReviewSummary,
)
from .onboarding_lifecycle_store import (
    InvalidOnboardingLifecycle,
    OnboardingLifecycleStore,
    StaleOnboardingVersion,
)
from .domain import Role


router = APIRouter()


def _lifecycle(settings: Settings) -> OnboardingLifecycleStore:
    return OnboardingLifecycleStore(store(settings).engine)


def _target_ou(settings: Settings) -> str:
    return (
        settings.google_production_onboarding_ou
        if settings.environment == "production"
        else settings.google_test_onboarding_ou
    )


def _require_true_owner(principal: Principal = Depends(require_owner)) -> Principal:
    if principal.role is not Role.OWNER:
        raise HTTPException(status_code=403, detail="Owner approval required")
    return principal


def _conflict(error: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


@router.get(
    "/api/benson/v1/employees/{employee_id}/tasks/{task_id}/reviews",
    response_model=list[TaskReviewSummary],
)
def list_task_reviews(
    employee_id: str,
    task_id: str,
    principal: Principal = Depends(_require_true_owner),
    settings: Settings = Depends(get_settings),
) -> list[TaskReviewSummary]:
    operations = _lifecycle(settings)
    task = operations.task_row(employee_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Onboarding task not found")
    require_manage_employee_data(principal, str(task["data_category"]))
    return [
        TaskReviewSummary.model_validate(item)
        for item in operations.list_reviews(employee_id, task_id)
    ]


@router.post(
    "/api/benson/v1/employees/{employee_id}/retention-holds",
    response_model=RetentionHoldSummary,
    status_code=201,
)
def create_retention_hold(
    employee_id: str,
    request: RetentionHoldCreate,
    principal: Principal = Depends(_require_true_owner),
    settings: Settings = Depends(get_settings),
) -> RetentionHoldSummary:
    try:
        result = _lifecycle(settings).create_retention_hold(
            employee_id,
            expected_version=request.expected_version,
            reason=request.reason,
            actor=principal.email,
        )
    except (InvalidOnboardingLifecycle, StaleOnboardingVersion) as error:
        raise _conflict(error) from error
    return RetentionHoldSummary.model_validate(result)


@router.post(
    "/api/benson/v1/employees/{employee_id}/retention-holds/{hold_id}/release",
    response_model=RetentionHoldSummary,
)
def release_retention_hold(
    employee_id: str,
    hold_id: str,
    request: RetentionHoldRelease,
    principal: Principal = Depends(_require_true_owner),
    settings: Settings = Depends(get_settings),
) -> RetentionHoldSummary:
    try:
        result = _lifecycle(settings).release_retention_hold(
            employee_id,
            hold_id,
            expected_version=request.expected_version,
            actor=principal.email,
        )
    except (InvalidOnboardingLifecycle, StaleOnboardingVersion) as error:
        raise _conflict(error) from error
    if not result:
        raise HTTPException(status_code=404, detail="Retention hold not found")
    return RetentionHoldSummary.model_validate(result)


@router.post(
    "/api/benson/v1/employees/{employee_id}/offboard",
    response_model=OffboardingReceipt,
)
def offboard_employee(
    employee_id: str,
    request: OffboardingRequest,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> OffboardingReceipt:
    try:
        result = _lifecycle(settings).offboard(
            employee_id,
            expected_version=request.expected_version,
            reason=request.reason,
            directory_idempotency_key=request.directory_idempotency_key,
            target_org_unit=_target_ou(settings),
            actor=principal.email,
        )
    except (InvalidOnboardingLifecycle, StaleOnboardingVersion) as error:
        raise _conflict(error) from error
    if not result:
        raise HTTPException(status_code=404, detail="Employee not found")
    return OffboardingReceipt.model_validate({**result, "status": "inactive"})


@router.delete("/api/benson/v1/employees/{employee_id}", status_code=204)
def delete_employee(
    employee_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not store(settings).delete_employee(employee_id, actor=principal.email):
        raise HTTPException(status_code=404, detail="Employee not found")
    return Response(status_code=204)
