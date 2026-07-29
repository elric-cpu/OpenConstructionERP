from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import Principal, require_schedule_planner, require_schedule_viewer
from .config import Settings, get_settings
from .dependencies import store
from .domain import STAFF
from .schedule_domain import (
    ScheduleEntryCreate,
    ScheduleEntrySummary,
    ScheduleEntryUpdate,
    ScheduleStatusHistorySummary,
    ScheduleTransition,
)
from .schedule_store import ScheduleConflict, ScheduleStaleWrite

router = APIRouter(prefix="/api/benson/v1/schedule", tags=["schedule"])

MAX_SCHEDULE_WINDOW = timedelta(days=180)


def _bounded_window(
    starts_at: datetime | None, ends_at: datetime | None
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    start = starts_at or now - timedelta(days=30)
    end = ends_at or now + timedelta(days=90)
    if (
        start.tzinfo is None
        or start.utcoffset() is None
        or end.tzinfo is None
        or end.utcoffset() is None
    ):
        raise HTTPException(
            status_code=422, detail="Schedule window must include offsets"
        )
    if end <= start:
        raise HTTPException(
            status_code=422, detail="Schedule window end must follow start"
        )
    if end - start > MAX_SCHEDULE_WINDOW:
        raise HTTPException(
            status_code=422, detail="Schedule window cannot exceed 180 days"
        )
    return start, end


def _validate_delivery_assignee(email: object, settings: Settings) -> None:
    normalized = str(email).lower()
    if normalized in {member["email"] for member in settings.assignable_staff()}:
        return
    if store(settings).is_active_delivery_assignee(normalized):
        return
    raise HTTPException(
        status_code=422,
        detail="Assignee must be an active authorized delivery staff member",
    )


@router.get("", response_model=list[ScheduleEntrySummary])
def list_schedule_entries(
    starts_at: Annotated[datetime | None, Query(alias="start")] = None,
    ends_at: Annotated[datetime | None, Query(alias="end")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    principal: Principal = Depends(require_schedule_viewer),
    settings: Settings = Depends(get_settings),
) -> list[ScheduleEntrySummary]:
    window_start, window_end = _bounded_window(starts_at, ends_at)
    return store(settings).list_schedule_entries(
        window_start=window_start,
        window_end=window_end,
        actor=principal.email,
        role=principal.role,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ScheduleEntrySummary,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_entry(
    entry: ScheduleEntryCreate,
    principal: Principal = Depends(require_schedule_planner),
    settings: Settings = Depends(get_settings),
) -> ScheduleEntrySummary:
    _validate_delivery_assignee(entry.assigned_to, settings)
    try:
        return store(settings).create_schedule_entry(entry, actor=principal.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ScheduleConflict, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{entry_id}", response_model=ScheduleEntrySummary)
def update_schedule_entry(
    entry_id: UUID,
    change: ScheduleEntryUpdate,
    principal: Principal = Depends(require_schedule_planner),
    settings: Settings = Depends(get_settings),
) -> ScheduleEntrySummary:
    if not change.model_dump(exclude_unset=True, exclude={"expected_version"}):
        raise HTTPException(status_code=400, detail="A schedule change is required")
    if change.assigned_to is not None:
        _validate_delivery_assignee(change.assigned_to, settings)
    try:
        entry = store(settings).update_schedule_entry(
            str(entry_id), change, actor=principal.email
        )
    except (ScheduleConflict, ScheduleStaleWrite, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if entry is None:
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return entry


@router.post("/{entry_id}/transition", response_model=ScheduleEntrySummary)
def transition_schedule_entry(
    entry_id: UUID,
    transition: ScheduleTransition,
    principal: Principal = Depends(require_schedule_viewer),
    settings: Settings = Depends(get_settings),
) -> ScheduleEntrySummary:
    if transition.status == "cancelled":
        if principal.role not in STAFF:
            raise HTTPException(status_code=403, detail="Planner approval required")
        if not transition.note.strip():
            raise HTTPException(status_code=422, detail="Cancellation note required")
        restrict_to_assignee = False
    else:
        if transition.status == "completed" and not transition.note.strip():
            raise HTTPException(status_code=422, detail="Completion note required")
        restrict_to_assignee = True
    try:
        entry = store(settings).transition_schedule_entry(
            str(entry_id),
            target=transition.status,
            expected_version=transition.expected_version,
            actor=principal.email,
            restrict_to_assignee=restrict_to_assignee,
            note=transition.note,
        )
    except (ScheduleStaleWrite, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if entry is None:
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return entry


@router.get("/{entry_id}/history", response_model=list[ScheduleStatusHistorySummary])
def schedule_entry_history(
    entry_id: UUID,
    _principal: Principal = Depends(require_schedule_planner),
    settings: Settings = Depends(get_settings),
) -> list[ScheduleStatusHistorySummary]:
    history = store(settings).list_schedule_status_history(str(entry_id))
    if history is None:
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return history


@router.get("/{entry_id}/audit")
def schedule_entry_audit(
    entry_id: UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    principal: Principal = Depends(require_schedule_viewer),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    events = store(settings).list_schedule_audit(
        str(entry_id),
        actor=principal.email,
        role=principal.role,
        limit=limit,
        offset=offset,
    )
    if events is None:
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return events
