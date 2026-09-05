from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import Principal, require_operations_staff
from .config import Settings, get_settings
from .dependencies import store
from .domain import (
    EstimateCreate,
    EstimateSummary,
    EstimateTransition,
    EstimateUpdate,
    Role,
)

router = APIRouter(prefix="/api/benson/v1/estimates", tags=["estimates"])


@router.get("", response_model=list[EstimateSummary])
def list_estimates(
    status_filter: Annotated[str, Query(alias="status")] = "",
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> list[EstimateSummary]:
    return store(settings).list_estimates(status=status_filter)


@router.post("", response_model=EstimateSummary, status_code=status.HTTP_201_CREATED)
def create_estimate(
    estimate: EstimateCreate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> EstimateSummary:
    try:
        return store(settings).create_estimate(estimate, actor=principal.email)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{estimate_id}/audit")
def estimate_audit(
    estimate_id: str,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    events = store(settings).list_estimate_audit(estimate_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return events


@router.patch("/{estimate_id}", response_model=EstimateSummary)
def update_estimate(
    estimate_id: str,
    change: EstimateUpdate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> EstimateSummary:
    if not change.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=400, detail="At least one estimate change is required"
        )
    estimate = store(settings).update_estimate(
        estimate_id, change, actor=principal.email
    )
    if estimate is None:
        raise HTTPException(status_code=404, detail="Editable draft estimate not found")
    return estimate


@router.post("/{estimate_id}/transition", response_model=EstimateSummary)
def transition_estimate(
    estimate_id: str,
    transition: EstimateTransition,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> EstimateSummary:
    if transition.status == "void" and principal.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(
            status_code=403, detail="Owner approval required to void an estimate"
        )
    if (
        transition.status in {"accepted", "declined", "void"}
        and not transition.note.strip()
    ):
        raise HTTPException(
            status_code=422,
            detail="A factual note is required for this estimate decision",
        )
    try:
        estimate = store(settings).transition_estimate(
            estimate_id,
            target=transition.status,
            actor=principal.email,
            delivery_confirmed=transition.external_delivery_confirmed,
            note=transition.note,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate
