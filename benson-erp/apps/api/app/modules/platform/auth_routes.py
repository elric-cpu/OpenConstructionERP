import uuid

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.platform import auth_service, mfa_service
from app.modules.platform.auth_schemas import (
    EmployeeActivationComplete,
    EmployeeActivationCompleteRead,
    EmployeeActivationInspectRead,
    EmployeeActivationToken,
    LoginRequest,
    MfaConfirmRequest,
    MfaEnrollment,
    MfaVerifyRequest,
    RefreshRequest,
    SessionRead,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "erp_refresh",
        token,
        httponly=True,
        secure=settings.environment != "development",
        samesite="strict",
        max_age=settings.refresh_token_days * 86400,
        path="/api/v1/auth",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    tokens, refresh_token = await auth_service.login(session, request, data)
    if refresh_token:
        _set_refresh_cookie(response, refresh_token)
    return tokens


@router.post(
    "/employee-activations/inspect",
    response_model=EmployeeActivationInspectRead,
)
async def inspect_employee_activation(
    data: EmployeeActivationToken,
    session: AsyncSession = Depends(get_session),
) -> EmployeeActivationInspectRead:
    return await auth_service.inspect_employee_activation(session, data)


@router.post(
    "/employee-activations/complete",
    response_model=EmployeeActivationCompleteRead,
)
async def complete_employee_activation(
    data: EmployeeActivationComplete,
    session: AsyncSession = Depends(get_session),
) -> EmployeeActivationCompleteRead:
    return await auth_service.complete_employee_activation(session, data)


@router.post("/mfa/verify", response_model=TokenResponse)
async def verify_mfa(
    data: MfaVerifyRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    tokens, refresh_token = await mfa_service.verify_login(session, request, data)
    _set_refresh_cookie(response, refresh_token)
    return tokens


@router.post("/mfa/enroll", response_model=MfaEnrollment)
async def enroll_mfa(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> MfaEnrollment:
    return await mfa_service.begin_enrollment(session, principal)


@router.post("/mfa/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_mfa(
    data: MfaConfirmRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> None:
    await mfa_service.confirm_enrollment(session, principal, data.code)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias="erp_refresh"),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    tokens, rotated_refresh = await auth_service.refresh(session, refresh_token, data.csrf_token)
    _set_refresh_cookie(response, rotated_refresh)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> None:
    await auth_service.revoke(session, principal)
    response.delete_cookie("erp_refresh", path="/api/v1/auth")


@router.get("/sessions", response_model=list[SessionRead])
async def sessions(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[SessionRead]:
    return await auth_service.list_sessions(session, principal)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> None:
    await auth_service.revoke_session(session, principal, session_id)
