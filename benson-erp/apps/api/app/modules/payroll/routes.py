import uuid

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.payroll import reconciliation, service
from app.modules.payroll.models import PayrollPeriod
from app.modules.payroll.permissions import PAYROLL_VIEW_WAGES
from app.modules.payroll.schemas import (
    EmployeePayRateCreate,
    EmployeePayRateRead,
    PayrollExceptionResolution,
    PayrollExportCreate,
    PayrollExportRead,
    PayrollMappingCreate,
    PayrollMappingRead,
    PayrollPeriodCreate,
    PayrollPeriodRead,
    PayrollPeriodTransition,
    PayrollPreview,
    PayrollReconciliationExceptionRead,
    PayrollReconciliationRead,
    PayrollResultImportCreate,
    PayrollResultImportRead,
)

router = APIRouter(prefix="/payroll", tags=["payroll"])


@router.post("/periods", response_model=PayrollPeriodRead, status_code=status.HTTP_201_CREATED)
async def create_payroll_period(
    data: PayrollPeriodCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollPeriodRead:
    return _period_read(await service.create_period(session, principal, data), principal)


@router.get("/periods", response_model=list[PayrollPeriodRead])
async def list_payroll_periods(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[PayrollPeriodRead]:
    return [
        _period_read(period, principal)
        for period in await service.list_periods(session, principal)
    ]


@router.post(
    "/pay-rates",
    response_model=EmployeePayRateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee_pay_rate(
    data: EmployeePayRateCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeePayRateRead:
    return EmployeePayRateRead.model_validate(
        await service.add_pay_rate(session, principal, data)
    )


@router.get("/pay-rates", response_model=list[EmployeePayRateRead])
async def list_employee_pay_rates(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[EmployeePayRateRead]:
    return [
        EmployeePayRateRead.model_validate(item)
        for item in await service.list_pay_rates(session, principal)
    ]


@router.post(
    "/mappings",
    response_model=PayrollMappingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_payroll_mapping(
    data: PayrollMappingCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollMappingRead:
    return PayrollMappingRead.model_validate(
        await service.add_mapping(session, principal, data)
    )


@router.get("/mappings", response_model=list[PayrollMappingRead])
async def list_payroll_mappings(
    provider: str | None = Query(default=None, min_length=2, max_length=80),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[PayrollMappingRead]:
    return [
        PayrollMappingRead.model_validate(item)
        for item in await service.list_mappings(session, principal, provider)
    ]


@router.get("/periods/{period_id}/preview", response_model=PayrollPreview)
async def preview_payroll_period(
    period_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollPreview:
    return await service.preview_period(session, principal, period_id)


@router.post("/periods/{period_id}/transitions", response_model=PayrollPeriodRead)
async def transition_payroll_period(
    period_id: uuid.UUID,
    data: PayrollPeriodTransition,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollPeriodRead:
    return _period_read(
        await service.transition_period(
            session,
            principal,
            period_id,
            expected_version,
            data,
        ),
        principal,
    )


@router.post(
    "/periods/{period_id}/exports",
    response_model=PayrollExportRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_payroll_export(
    period_id: uuid.UUID,
    data: PayrollExportCreate,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollExportRead:
    return PayrollExportRead.model_validate(
        await service.generate_export(
            session,
            principal,
            period_id,
            expected_version,
            data,
        )
    )


@router.get("/periods/{period_id}/exports", response_model=list[PayrollExportRead])
async def list_payroll_exports(
    period_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[PayrollExportRead]:
    return [
        PayrollExportRead.model_validate(item)
        for item in await service.list_exports(session, principal, period_id)
    ]


@router.get("/exports/{export_id}/download")
async def download_payroll_export(
    export_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    payroll_export, content = await service.download_export(
        session,
        principal,
        export_id,
    )
    return Response(
        content=content,
        media_type=payroll_export.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{payroll_export.filename}"',
            "ETag": f'"{payroll_export.file_checksum}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _period_read(period: PayrollPeriod, principal: Principal) -> PayrollPeriodRead:
    result = PayrollPeriodRead.model_validate(period)
    if PAYROLL_VIEW_WAGES in principal.permissions:
        return result
    return result.model_copy(
        update={"validation_snapshot": service.redact_wages(result.validation_snapshot)}
    )


@router.post(
    "/periods/{period_id}/result-imports",
    response_model=PayrollResultImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_payroll_results(
    period_id: uuid.UUID,
    data: PayrollResultImportCreate,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollResultImportRead:
    return PayrollResultImportRead.model_validate(
        await reconciliation.import_results(
            session,
            principal,
            period_id,
            expected_version,
            data,
        )
    )


@router.get(
    "/result-imports/{import_id}/reconciliation",
    response_model=PayrollReconciliationRead,
)
async def get_payroll_reconciliation(
    import_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollReconciliationRead:
    return await reconciliation.get_reconciliation(session, principal, import_id)


@router.get(
    "/periods/{period_id}/result-imports",
    response_model=list[PayrollResultImportRead],
)
async def list_payroll_result_imports(
    period_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[PayrollResultImportRead]:
    return [
        PayrollResultImportRead.model_validate(item)
        for item in await reconciliation.list_result_imports(
            session,
            principal,
            period_id,
        )
    ]


@router.post(
    "/reconciliation-exceptions/{exception_id}/resolve",
    response_model=PayrollReconciliationExceptionRead,
)
async def resolve_payroll_exception(
    exception_id: uuid.UUID,
    data: PayrollExceptionResolution,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollReconciliationExceptionRead:
    return PayrollReconciliationExceptionRead.model_validate(
        await reconciliation.resolve_exception(
            session,
            principal,
            exception_id,
            expected_version,
            data.reason,
        )
    )


@router.post(
    "/result-imports/{import_id}/reconcile",
    response_model=PayrollResultImportRead,
)
async def reconcile_payroll_results(
    import_id: uuid.UUID,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollResultImportRead:
    return PayrollResultImportRead.model_validate(
        await reconciliation.reconcile(
            session,
            principal,
            import_id,
            expected_version,
        )
    )
