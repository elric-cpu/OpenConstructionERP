import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.scheduling import service
from app.modules.scheduling.schemas import (
    ActivityCreate,
    ActivityRead,
    AssignmentCreate,
    AssignmentRead,
    ScheduleCreate,
    ScheduleEntryRead,
    ScheduleRead,
)

router = APIRouter(tags=["scheduling"])


@router.post("/schedules", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    data: ScheduleCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ScheduleRead:
    return ScheduleRead.model_validate(await service.create_schedule(session, principal, data))


@router.get("/projects/{project_id}/schedule", response_model=ScheduleRead)
async def get_project_schedule(
    project_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ScheduleRead:
    return ScheduleRead.model_validate(
        await service.get_project_schedule(session, principal, project_id)
    )


@router.post(
    "/schedules/{schedule_id}/activities",
    response_model=ActivityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity(
    schedule_id: uuid.UUID,
    data: ActivityCreate,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ActivityRead:
    return ActivityRead.model_validate(
        await service.create_activity(
            session,
            principal,
            schedule_id,
            expected_version,
            data,
        )
    )


@router.post(
    "/schedule-activities/{activity_id}/assignments",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def assign_employee(
    activity_id: uuid.UUID,
    data: AssignmentCreate,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> AssignmentRead:
    return AssignmentRead.model_validate(
        await service.assign_employee(
            session,
            principal,
            activity_id,
            expected_version,
            data,
        )
    )


@router.get("/schedule-entries", response_model=list[ScheduleEntryRead])
async def list_schedule_entries(
    start_at: datetime = Query(),
    end_at: datetime = Query(),
    employee_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ScheduleEntryRead]:
    return await service.list_entries(
        session,
        principal,
        start_at,
        end_at,
        employee_id,
    )
