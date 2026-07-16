from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .config import Settings, get_settings
from .domain import FIELD_STAFF, FINANCE_STAFF, STAFF, Role


@dataclass(frozen=True)
class Principal:
    email: str
    role: Role
    subject: str


def staff_role_for_email(email: str, settings: Settings) -> Role | None:
    for role in (
        Role.OWNER,
        Role.ADMIN,
        Role.ESTIMATOR_PM,
        Role.ACCOUNTING,
        Role.FIELD,
        Role.OFFICE,
    ):
        if email in settings.role_emails(role.value):
            return role
    return None


def verify_google_identity(credential: str, settings: Settings) -> dict[str, Any]:
    if not settings.staff_google_audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )
    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            credential,
            google_requests.Request(),
            settings.staff_google_audience,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google identity token",
        ) from error
    return claims


def require_staff(
    authorization: Annotated[str | None, Header()] = None,
    x_dev_staff_email: Annotated[str | None, Header(alias="X-Dev-Staff-Email")] = None,
    settings: Settings = Depends(get_settings),
) -> Principal:
    if settings.environment != "production" and x_dev_staff_email:
        email = x_dev_staff_email.strip().lower()
        role = staff_role_for_email(email, settings)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff account is not authorized",
            )
        return Principal(email=email, role=role, subject=f"dev:{email}")
    if not settings.staff_google_audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Staff SSO is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in is required",
        )
    claims = verify_google_identity(
        authorization.removeprefix("Bearer ").strip(), settings
    )
    email = str(claims.get("email", "")).lower()
    hosted_domain = str(claims.get("hd", "")).lower()
    if (
        not claims.get("email_verified")
        or hosted_domain != settings.staff_google_domain.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benson Workspace account required",
        )
    role = staff_role_for_email(email, settings)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff account is not authorized",
        )
    return Principal(email=email, role=role, subject=str(claims.get("sub", email)))


def require_employee(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in is required",
        )
    claims = verify_google_identity(
        authorization.removeprefix("Bearer ").strip(), settings
    )
    if (
        not claims.get("email_verified")
        or not claims.get("email")
        or not claims.get("sub")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verified Google account required",
        )
    email = str(claims["email"]).lower()
    subject = str(claims["sub"])
    from .storage import operations_store

    employee = operations_store(
        settings.resolved_database_url()
    ).get_employee_by_identity(email, subject)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active employee account required",
        )
    return Principal(email=email, role=employee.role, subject=subject)


def require_portal_user(
    authorization: Annotated[str | None, Header()] = None,
    x_dev_staff_email: Annotated[str | None, Header(alias="X-Dev-Staff-Email")] = None,
    settings: Settings = Depends(get_settings),
) -> Principal:
    if settings.environment != "production" and x_dev_staff_email:
        return require_staff(
            authorization=authorization,
            x_dev_staff_email=x_dev_staff_email,
            settings=settings,
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in is required",
        )
    claims = verify_google_identity(
        authorization.removeprefix("Bearer ").strip(), settings
    )
    email = str(claims.get("email", "")).lower()
    subject = str(claims.get("sub", ""))
    hosted_domain = str(claims.get("hd", "")).lower()
    if (
        not claims.get("email_verified")
        or not email
        or not subject
        or hosted_domain != settings.staff_google_domain.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benson Workspace account required",
        )
    staff_role = staff_role_for_email(email, settings)
    if staff_role:
        return Principal(email=email, role=staff_role, subject=subject)
    from .storage import operations_store

    employee = operations_store(
        settings.resolved_database_url()
    ).get_employee_by_identity(email, subject)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Portal account is not authorized",
        )
    return Principal(email=email, role=employee.role, subject=subject)


def require_owner(principal: Principal = Depends(require_staff)) -> Principal:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner approval required"
        )
    return principal


def require_operations_staff(
    principal: Principal = Depends(require_staff),
) -> Principal:
    if principal.role not in STAFF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lead workspace access required",
        )
    return principal


def require_job_staff(principal: Principal = Depends(require_staff)) -> Principal:
    if principal.role not in FIELD_STAFF | FINANCE_STAFF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job workspace access required",
        )
    return principal


def require_delivery_staff(principal: Principal = Depends(require_staff)) -> Principal:
    if principal.role not in FIELD_STAFF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job delivery access required",
        )
    return principal


def require_notification_worker(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> str:
    if settings.environment != "production":
        return "development-notification-worker"
    if (
        not settings.notification_worker_audience
        or not settings.notification_worker_email
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification worker identity is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Notification worker identity is required",
        )
    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            authorization.removeprefix("Bearer ").strip(),
            google_requests.Request(),
            str(settings.notification_worker_audience).rstrip("/"),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid notification worker identity",
        ) from error
    email = str(claims.get("email", "")).lower()
    if (
        not claims.get("email_verified")
        or email != settings.notification_worker_email.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Notification worker is not authorized",
        )
    return email
