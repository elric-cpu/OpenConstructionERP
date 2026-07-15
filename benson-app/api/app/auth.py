from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .config import Settings, get_settings
from .domain import STAFF, Role


@dataclass(frozen=True)
class Principal:
    email: str
    role: Role
    subject: str


def _role_for_email(email: str, settings: Settings) -> Role:
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
    return Role.OFFICE


def require_staff(
    authorization: Annotated[str | None, Header()] = None,
    x_dev_staff_email: Annotated[str | None, Header(alias="X-Dev-Staff-Email")] = None,
    settings: Settings = Depends(get_settings),
) -> Principal:
    if settings.environment != "production" and x_dev_staff_email:
        email = x_dev_staff_email.strip().lower()
        return Principal(email=email, role=_role_for_email(email, settings), subject=f"dev:{email}")
    if not settings.staff_google_audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Staff SSO is not configured"
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in is required"
        )
    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            authorization.removeprefix("Bearer ").strip(),
            google_requests.Request(),
            settings.staff_google_audience,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google identity token"
        ) from error
    email = str(claims.get("email", "")).lower()
    hosted_domain = str(claims.get("hd", "")).lower()
    if not claims.get("email_verified") or hosted_domain != settings.staff_google_domain.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Benson Workspace account required"
        )
    return Principal(
        email=email, role=_role_for_email(email, settings), subject=str(claims.get("sub", email))
    )


def require_owner(principal: Principal = Depends(require_staff)) -> Principal:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner approval required")
    return principal


def require_operations_staff(principal: Principal = Depends(require_staff)) -> Principal:
    if principal.role not in STAFF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lead workspace access required",
        )
    return principal
