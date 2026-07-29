import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import Principal, create_access_token
from app.modules.people import repository as people_repository
from app.modules.people.audit import employee_audit_state
from app.modules.people.events import EMPLOYEE_ACTIVATED
from app.modules.people.models import Employee, EmployeeActivationRequest, EmployeeStatus
from app.modules.platform.audit import add_audit, add_outbox
from app.modules.platform.auth_schemas import (
    EmployeeActivationComplete,
    EmployeeActivationCompleteRead,
    EmployeeActivationInspectRead,
    EmployeeActivationToken,
    LoginRequest,
    SessionRead,
    TokenResponse,
)
from app.modules.platform.models import LoginEvent, LoginSession, Membership, Organization, User

password_hash = PasswordHash.recommended()
_DUMMY_HASH = password_hash.hash("not-a-real-account-password")
EMPLOYEE_SELF_SERVICE_PERMISSIONS = [
    "projects.read",
    "schedules.read_own",
    "time.certify_own",
    "time.correct_own",
    "time.enter_own",
]


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    return ip_address, request.headers.get("user-agent")


async def login(
    session: AsyncSession, request: Request, data: LoginRequest
) -> tuple[TokenResponse, str | None]:
    organization = await session.scalar(
        select(Organization).where(Organization.slug == data.organization.strip().lower())
    )
    if organization is None:
        password_hash.verify(data.password, _DUMMY_HASH)
        raise _invalid_credentials()
    await _set_tenant(session, organization.id)
    email = str(data.email).strip().lower()
    ip_address, user_agent = _request_metadata(request)
    if await _recent_failure_count(session, organization.id, email, ip_address) >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Try again later")

    row = (
        await session.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.tenant_id == organization.id,
                func.lower(User.email) == email,
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    user = row[0] if row else None
    membership = row[1] if row else None
    valid = (
        password_hash.verify(data.password, user.password_hash or _DUMMY_HASH) if user else False
    )
    if not valid or membership is None or user is None:
        session.add(
            _login_event(
                organization.id, user.id if user else None, email, False, request, "invalid"
            )
        )
        await session.commit()
        raise _invalid_credentials()
    assert user is not None

    if user.mfa_enabled:
        from app.modules.platform.mfa_service import create_challenge

        session.add(_login_event(organization.id, user.id, email, True, request, "mfa_pending"))
        await session.commit()
        return (
            TokenResponse(
                mfa_required=True,
                mfa_challenge_token=create_challenge(user.id, organization.id, email),
            ),
            None,
        )
    return await complete_login(
        session, request, organization.id, user, membership, data.device_name, email
    )


async def inspect_employee_activation(
    session: AsyncSession,
    data: EmployeeActivationToken,
) -> EmployeeActivationInspectRead:
    tenant_id, request_id = _activation_token_scope(data.token)
    await _set_tenant(session, tenant_id)
    activation = await people_repository.get_activation_request(session, tenant_id, request_id)
    employee = (
        await people_repository.get_employee(session, tenant_id, activation.employee_id)
        if activation is not None
        else None
    )
    if not _activation_available(activation, data.token) or not _employee_activation_ready(employee):
        raise _invalid_activation()
    organization = await session.get(Organization, tenant_id)
    if organization is None:
        raise _invalid_activation()
    assert activation is not None and employee is not None and employee.company_email is not None
    return EmployeeActivationInspectRead(
        employee_name=f"{employee.first_name} {employee.last_name}",
        company_email=employee.company_email,
        organization_name=organization.name,
        expires_at=activation.expires_at,
    )


async def complete_employee_activation(
    session: AsyncSession,
    data: EmployeeActivationComplete,
) -> EmployeeActivationCompleteRead:
    tenant_id, request_id = _activation_token_scope(data.token)
    await _set_tenant(session, tenant_id)
    activation = await people_repository.get_activation_request(
        session, tenant_id, request_id, for_update=True
    )
    employee = (
        await people_repository.get_employee(
            session, tenant_id, activation.employee_id, for_update=True
        )
        if activation is not None
        else None
    )
    if not _activation_available(activation, data.token) or not _employee_activation_ready(employee):
        raise _invalid_activation()
    assert activation is not None and employee is not None and employee.company_email is not None
    email = employee.company_email.strip().lower()
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is not None:
        existing_membership = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == user.id,
            )
        )
        linked_employee = await session.scalar(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.user_id == user.id,
            )
        )
        if (
            existing_membership is not None
            or linked_employee is not None
            or user.password_hash is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Employee activation cannot be completed",
            )
        user.password_hash = password_hash.hash(data.password)
        user.is_active = True
    else:
        user = User(
            email=email,
            password_hash=password_hash.hash(data.password),
            is_active=True,
        )
        session.add(user)
        await session.flush()
    before = employee_audit_state(employee)
    session.add(
        Membership(
            tenant_id=tenant_id,
            user_id=user.id,
            permissions=EMPLOYEE_SELF_SERVICE_PERMISSIONS,
        )
    )
    now = datetime.now(UTC)
    employee.user_id = user.id
    employee.status = EmployeeStatus.ACTIVE
    employee.erp_access_confirmed_at = now
    employee.updated_by = user.id
    employee.version += 1
    activation.used_at = now
    activation.encrypted_delivery_secret = ""
    activation.last_attempt_at = now
    activation.attempt_count += 1
    activation.updated_by = user.id
    activation.version += 1
    await session.execute(
        text(
            "UPDATE login_sessions SET revoked_at = :now "
            "WHERE tenant_id = :tenant_id AND user_id = :user_id AND revoked_at IS NULL"
        ),
        {"now": now, "tenant_id": tenant_id, "user_id": user.id},
    )
    principal = Principal(
        user_id=user.id,
        tenant_id=tenant_id,
        permissions=frozenset(EMPLOYEE_SELF_SERVICE_PERMISSIONS),
        session_id=uuid.uuid4(),
    )
    correlation_id = uuid.uuid4()
    add_audit(
        session,
        principal,
        "Employee",
        employee.id,
        "erp_access_activated",
        correlation_id,
        before,
        employee_audit_state(employee),
        "Employee completed one-time ERP activation",
    )
    add_outbox(
        session,
        principal,
        EMPLOYEE_ACTIVATED,
        "Employee",
        employee.id,
        correlation_id,
        f"employee-activated:{activation.id}",
        {"employee_id": str(employee.id), "user_id": str(user.id)},
    )
    organization = await session.get(Organization, tenant_id)
    await session.commit()
    return EmployeeActivationCompleteRead(
        activated=True,
        organization=organization.slug if organization is not None else str(tenant_id),
        email=email,
    )


async def complete_login(
    session: AsyncSession,
    request: Request,
    tenant_id: uuid.UUID,
    user: User,
    membership: Membership,
    device_name: str | None,
    email: str,
) -> tuple[TokenResponse, str]:
    await _set_tenant(session, tenant_id)
    ip_address, user_agent = _request_metadata(request)

    refresh_secret = secrets.token_urlsafe(48)
    refresh_token = f"{tenant_id}.{refresh_secret}"
    csrf_token = secrets.token_urlsafe(32)
    login_session = LoginSession(
        tenant_id=tenant_id,
        user_id=user.id,
        refresh_token_hash=hash_secret(refresh_token),
        csrf_token_hash=hash_secret(csrf_token),
        device_name=device_name,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    session.add(login_session)
    session.add(_login_event(tenant_id, user.id, email, True, request, None))
    await session.flush()
    principal = Principal(
        user_id=user.id,
        tenant_id=tenant_id,
        permissions=frozenset(membership.permissions),
        session_id=login_session.id,
    )
    await session.commit()
    return _token_response(principal, csrf_token), refresh_token


async def refresh(
    session: AsyncSession, refresh_token: str | None, csrf_token: str
) -> tuple[TokenResponse, str]:
    tenant_id = _tenant_from_refresh(refresh_token)
    await _set_tenant(session, tenant_id)
    login_session = await session.scalar(
        select(LoginSession).where(
            LoginSession.refresh_token_hash == hash_secret(refresh_token or "")
        )
    )
    now = datetime.now(UTC)
    if (
        login_session is None
        or login_session.revoked_at is not None
        or login_session.expires_at <= now
        or not secrets.compare_digest(login_session.csrf_token_hash, hash_secret(csrf_token))
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    membership = await session.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id, Membership.user_id == login_session.user_id
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    new_refresh = f"{tenant_id}.{secrets.token_urlsafe(48)}"
    new_csrf = secrets.token_urlsafe(32)
    login_session.refresh_token_hash = hash_secret(new_refresh)
    login_session.csrf_token_hash = hash_secret(new_csrf)
    login_session.last_seen_at = now
    principal = Principal(
        user_id=login_session.user_id,
        tenant_id=tenant_id,
        permissions=frozenset(membership.permissions),
        session_id=login_session.id,
    )
    await session.commit()
    return _token_response(principal, new_csrf), new_refresh


async def revoke(session: AsyncSession, principal: Principal) -> None:
    await _set_tenant(session, principal.tenant_id)
    login_session = await session.scalar(
        select(LoginSession).where(
            LoginSession.tenant_id == principal.tenant_id,
            LoginSession.id == principal.session_id,
            LoginSession.user_id == principal.user_id,
        )
    )
    if login_session:
        login_session.revoked_at = datetime.now(UTC)
        await session.commit()


async def list_sessions(session: AsyncSession, principal: Principal) -> list[SessionRead]:
    rows = list(
        await session.scalars(
            select(LoginSession)
            .where(
                LoginSession.tenant_id == principal.tenant_id,
                LoginSession.user_id == principal.user_id,
                LoginSession.revoked_at.is_(None),
                LoginSession.expires_at > datetime.now(UTC),
            )
            .order_by(LoginSession.last_seen_at.desc())
        )
    )
    return [
        SessionRead(
            id=str(row.id),
            device_name=row.device_name,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            created_at=row.created_at.isoformat(),
            last_seen_at=row.last_seen_at.isoformat(),
            expires_at=row.expires_at.isoformat(),
            current=row.id == principal.session_id,
        )
        for row in rows
    ]


async def revoke_session(
    session: AsyncSession, principal: Principal, session_id: uuid.UUID
) -> None:
    target = await session.scalar(
        select(LoginSession).where(
            LoginSession.tenant_id == principal.tenant_id,
            LoginSession.user_id == principal.user_id,
            LoginSession.id == session_id,
            LoginSession.revoked_at.is_(None),
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Session not found")
    target.revoked_at = datetime.now(UTC)
    await session.commit()


async def _set_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def _recent_failure_count(
    session: AsyncSession, tenant_id: uuid.UUID, email: str, ip_address: str | None
) -> int:
    since = datetime.now(UTC) - timedelta(minutes=15)
    count = await session.scalar(
        select(func.count(LoginEvent.id)).where(
            LoginEvent.tenant_id == tenant_id,
            LoginEvent.email == email,
            LoginEvent.ip_address == ip_address,
            LoginEvent.succeeded.is_(False),
            LoginEvent.occurred_at >= since,
        )
    )
    return int(count or 0)


def _login_event(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    email: str,
    succeeded: bool,
    request: Request,
    reason: str | None,
) -> LoginEvent:
    ip_address, user_agent = _request_metadata(request)
    return LoginEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        email=email,
        succeeded=succeeded,
        failure_reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def _tenant_from_refresh(refresh_token: str | None) -> uuid.UUID:
    try:
        return uuid.UUID((refresh_token or "").split(".", 1)[0])
    except (ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from exc


def _activation_token_scope(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    try:
        tenant, request_id, secret = token.split(".", 2)
        if len(secret) < 43:
            raise ValueError("Activation secret is too short")
        return uuid.UUID(tenant), uuid.UUID(request_id)
    except (ValueError, IndexError) as exc:
        raise _invalid_activation() from exc


def _activation_available(
    activation: EmployeeActivationRequest | None,
    token: str,
) -> bool:
    now = datetime.now(UTC)
    return bool(
        activation is not None
        and activation.used_at is None
        and activation.revoked_at is None
        and activation.expires_at > now
        and secrets.compare_digest(activation.token_hash, hash_secret(token))
    )


def _employee_activation_ready(employee: Employee | None) -> bool:
    return bool(
        employee is not None
        and employee.status is EmployeeStatus.IDENTITY_CREATED
        and employee.user_id is None
        and employee.company_email
        and employee.google_subject_id
    )


def _invalid_activation() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Activation link is invalid or no longer available",
    )


def _invalid_credentials() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


def _token_response(principal: Principal, csrf_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(principal),
        expires_in=settings.access_token_minutes * 60,
        csrf_token=csrf_token,
    )
