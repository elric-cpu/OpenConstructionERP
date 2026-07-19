import re
import unicodedata
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import Principal, require_owner, verify_google_identity
from .compliance import ONBOARDING_REQUIREMENTS
from .config import Settings, get_settings
from .dependencies import store
from .identity_provisioning_store import IdentityProvisioningStore
from .onboarding_domain import (
    EmployeeCreate,
    EmployeeInviteActivation,
    EmployeeInviteCommand,
    EmployeeSummary,
    OnboardingEmployeeSummary,
    OnboardingInviteReceipt,
)
from .onboarding_lifecycle_store import OnboardingLifecycleStore, StaleOnboardingVersion
from .storage import InvalidEmployeeInvite

router = APIRouter()


def _managed_email(name: str, settings: Settings) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    parts = re.findall(r"[a-z0-9]+", normalized.lower())
    base = ".".join((parts[0], parts[-1])) if len(parts) > 1 else parts[0]
    existing = {str(item.email).casefold() for item in store(settings).list_employees()}
    candidate = f"{base}@{settings.staff_google_domain}".lower()
    suffix = 2
    while candidate.casefold() in existing:
        candidate = f"{base}{suffix}@{settings.staff_google_domain}".lower()
        suffix += 1
    return candidate


@router.get("/api/benson/v1/onboarding/requirements")
async def onboarding_requirements(
    _principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    return {
        "review_status": "pending_qualified_hr_legal_review",
        "requirements": [
            item.model_dump(mode="json") for item in ONBOARDING_REQUIREMENTS
        ],
    }


@router.get("/api/benson/v1/employees", response_model=list[OnboardingEmployeeSummary])
def list_employees(
    _principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[OnboardingEmployeeSummary]:
    rows = OnboardingLifecycleStore(store(settings).engine).list_employee_rows()
    return [OnboardingEmployeeSummary.model_validate(row) for row in rows]


def _normalize_employee(employee: EmployeeCreate, settings: Settings) -> EmployeeCreate:
    if employee.classification != "employee":
        if employee.email is None:
            raise HTTPException(status_code=422, detail="Contractor email is required")
        contractor_delivery_email = employee.invite_delivery_email or employee.email
        return employee.model_copy(
            update={"invite_delivery_email": contractor_delivery_email}
        )
    delivery_email = employee.invite_delivery_email or employee.email
    if delivery_email is None:
        raise HTTPException(
            status_code=422, detail="A reachable new-hire email is required"
        )
    if any(
        str(existing.invite_delivery_email or "").casefold()
        == str(delivery_email).casefold()
        for existing in store(settings).list_employees()
    ):
        raise HTTPException(
            status_code=409, detail="A new-hire record already exists for this email"
        )
    return employee.model_copy(
        update={
            "email": _managed_email(employee.name, settings),
            "invite_delivery_email": delivery_email,
        }
    )


@router.post(
    "/api/benson/v1/employees",
    response_model=OnboardingEmployeeSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    employee: EmployeeCreate,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> OnboardingEmployeeSummary:
    employee = _normalize_employee(employee, settings)
    try:
        created = store(settings).create_employee(
            actor=principal.email, employee=employee
        )
        lifecycle = OnboardingLifecycleStore(store(settings).engine)
        row = lifecycle.employee_row(str(created.id))
        if row is None:
            raise ValueError("Created employee lifecycle row was not initialized")
        if employee.classification == "employee":
            commands = IdentityProvisioningStore(store(settings).engine)
            command = commands.request_create(
                str(created.id),
                expected_version=int(row["version"]),
                idempotency_key=f"new-hire:{created.id}",
                target_org_unit=(
                    settings.google_production_onboarding_ou
                    if settings.environment == "production"
                    else settings.google_test_onboarding_ou
                ),
                actor=principal.email,
            )
            if not command:
                raise ValueError("Identity provisioning command was not created")
            commands.approve(
                str(command["id"]),
                expected_version=int(command["version"]),
                actor=principal.email,
            )
            row = lifecycle.employee_row(str(created.id))
        return OnboardingEmployeeSummary.model_validate(row)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/api/benson/v1/employees/{employee_id}/invite",
    response_model=OnboardingInviteReceipt,
    status_code=202,
)
def invite_employee(
    employee_id: str,
    command: EmployeeInviteCommand | None = None,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> OnboardingInviteReceipt:
    expected_version = command.expected_version if command else None
    if expected_version is None:
        employee = OnboardingLifecycleStore(store(settings).engine).employee_row(
            employee_id
        )
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        expected_version = int(employee["version"])
    try:
        invitation = store(settings).create_employee_invite(
            employee_id,
            actor=principal.email,
            invite_base_url=str(settings.upload_base_url),
            invite_signing_secret=settings.employee_invite_signing_secret,
            expires_in_hours=72,
            notification_max_attempts=settings.notification_max_attempts,
            expected_version=expected_version,
            encryption_key=settings.employee_document_key_bytes(),
        )
    except (InvalidEmployeeInvite, StaleOnboardingVersion) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not invitation:
        raise HTTPException(status_code=404, detail="Employee not found")
    return invitation


@router.post("/api/benson/v1/onboarding/activate", response_model=EmployeeSummary)
def activate_employee_invitation(
    activation: EmployeeInviteActivation,
    settings: Settings = Depends(get_settings),
) -> EmployeeSummary:
    claims = verify_google_identity(activation.credential, settings)
    context = store(settings).employee_invite_context(activation.token)
    if (
        not claims.get("email_verified")
        or not claims.get("email")
        or not claims.get("sub")
        or not context
        or str(claims["email"]).casefold() != context["email"].casefold()
        or (
            context["classification"] == "employee"
            and str(claims.get("hd", "")).lower()
            != settings.staff_google_domain.lower()
        )
    ):
        raise HTTPException(
            status_code=403, detail="Invitation is invalid or no longer available"
        )
    try:
        return store(settings).activate_employee_invite(
            activation.token,
            email=str(claims["email"]),
            google_subject=str(claims["sub"]),
        )
    except InvalidEmployeeInvite as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
