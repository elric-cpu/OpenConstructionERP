import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.timekeeping import service
from app.modules.timekeeping.schemas import (
    TimeApproval,
    TimeCertification,
    TimeCorrectionCreate,
    TimeCorrectionRead,
    TimeEntryCreate,
    TimeEntryEmployeeOption,
    TimeEntryRead,
)

router = APIRouter(prefix="/time-entries", tags=["timekeeping"])


@router.get("/resources/employees", response_model=list[TimeEntryEmployeeOption])
async def get_time_entry_employee_options(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[TimeEntryEmployeeOption]:
    return [
        TimeEntryEmployeeOption(
            id=employee.id,
            employee_number=employee.employee_number,
            first_name=employee.first_name,
            last_name=employee.last_name,
            is_self=employee.user_id == principal.user_id,
        )
        for employee in await service.list_entry_employee_options(session, principal)
    ]


@router.post("", response_model=TimeEntryRead, status_code=status.HTTP_201_CREATED)
async def create_time_entry(
    data: TimeEntryCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> TimeEntryRead:
    return TimeEntryRead.model_validate(await service.create_entry(session, principal, data))


@router.get("", response_model=list[TimeEntryRead])
async def get_time_entries(
    date_from: date = Query(),
    date_to: date = Query(),
    employee_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[TimeEntryRead]:
    return [
        TimeEntryRead.model_validate(entry)
        for entry in await service.list_entries(
            session,
            principal,
            employee_id,
            date_from,
            date_to,
        )
    ]


@router.post("/{entry_id}/certify", response_model=TimeEntryRead)
async def certify_time_entry(
    entry_id: uuid.UUID,
    data: TimeCertification,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> TimeEntryRead:
    return TimeEntryRead.model_validate(
        await service.certify_entry(
            session,
            principal,
            entry_id,
            expected_version,
            data,
        )
    )


@router.post("/{entry_id}/approve", response_model=TimeEntryRead)
async def approve_time_entry(
    entry_id: uuid.UUID,
    data: TimeApproval,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> TimeEntryRead:
    return TimeEntryRead.model_validate(
        await service.approve_entry(
            session,
            principal,
            entry_id,
            expected_version,
            data,
        )
    )


@router.post(
    "/{entry_id}/corrections",
    response_model=TimeCorrectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def request_time_correction(
    entry_id: uuid.UUID,
    data: TimeCorrectionCreate,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> TimeCorrectionRead:
    correction, replacement = await service.request_correction(
        session,
        principal,
        entry_id,
        expected_version,
        data,
    )
    return TimeCorrectionRead(
        id=correction.id,
        original_entry_id=correction.original_entry_id,
        replacement_entry_id=correction.replacement_entry_id,
        reason=correction.reason,
        requested_by=correction.requested_by,
        requested_at=correction.requested_at,
        status=correction.status,
        completed_at=correction.completed_at,
        version=correction.version,
        replacement=TimeEntryRead.model_validate(replacement),
    )
