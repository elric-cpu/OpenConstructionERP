from fastapi import APIRouter, Depends, HTTPException

from .auth import Principal, require_identity_provisioning_worker, require_owner
from .config import Settings, get_settings
from .dependencies import store
from .directory_provider import (
    DirectoryProviderConfig,
    DirectoryProviderError,
    GoogleDirectoryProvider,
)
from .identity_provisioning_store import IdentityProvisioningStore
from .identity_provisioning_worker import IdentityProvisioningWorker
from .onboarding_domain import (
    IdentityAdminConfirmation,
    IdentityCommandMutation,
    IdentityProvisioningRequest,
    IdentityProvisioningSummary,
)
from .onboarding_lifecycle_store import (
    InvalidOnboardingLifecycle,
    OnboardingLifecycleStore,
    StaleOnboardingVersion,
)
from .storage import InvalidEmployeeInvite
from .sealed_secret import open_secret
from .domain import Role


router = APIRouter()


def _commands(settings: Settings) -> IdentityProvisioningStore:
    return IdentityProvisioningStore(store(settings).engine)


def _target_ou(settings: Settings) -> str:
    return (
        settings.google_production_onboarding_ou
        if settings.environment == "production"
        else settings.google_test_onboarding_ou
    )


def _require_true_owner(principal: Principal = Depends(require_owner)) -> Principal:
    if principal.role is not Role.OWNER:
        raise HTTPException(status_code=403, detail="Owner approval required")
    return principal


def _translate(error: ValueError) -> HTTPException:
    if isinstance(error, StaleOnboardingVersion):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=409, detail=str(error))


def _queue_invitation(
    settings: Settings,
    employee_id: str,
    *,
    actor: str,
    bootstrap_password: str | None = None,
) -> None:
    row = OnboardingLifecycleStore(store(settings).engine).employee_row(employee_id)
    if not row or row["status"] != "draft":
        return
    store(settings).create_employee_invite(
        employee_id,
        actor=actor,
        invite_base_url=str(settings.upload_base_url),
        invite_signing_secret=settings.employee_invite_signing_secret,
        expires_in_hours=72,
        notification_max_attempts=settings.notification_max_attempts,
        expected_version=int(row["version"]),
        bootstrap_password=bootstrap_password,
        encryption_key=settings.employee_document_key_bytes(),
    )


@router.post(
    "/api/benson/v1/identity-provisioning",
    response_model=IdentityProvisioningSummary,
    status_code=202,
)
def request_identity_provisioning(
    request: IdentityProvisioningRequest,
    principal: Principal = Depends(_require_true_owner),
    settings: Settings = Depends(get_settings),
) -> IdentityProvisioningSummary:
    try:
        result = _commands(settings).request_create(
            str(request.employee_id),
            expected_version=request.expected_version,
            idempotency_key=request.idempotency_key,
            target_org_unit=_target_ou(settings),
            actor=principal.email,
        )
    except InvalidOnboardingLifecycle as error:
        raise _translate(error) from error
    if not result:
        raise HTTPException(status_code=404, detail="Employee not found")
    return IdentityProvisioningSummary.model_validate(result)


@router.post(
    "/api/benson/v1/identity-provisioning/{command_id}/approve",
    response_model=IdentityProvisioningSummary,
)
def approve_identity_provisioning(
    command_id: str,
    mutation: IdentityCommandMutation,
    principal: Principal = Depends(_require_true_owner),
    settings: Settings = Depends(get_settings),
) -> IdentityProvisioningSummary:
    try:
        result = _commands(settings).approve(
            command_id,
            expected_version=mutation.expected_version,
            actor=principal.email,
        )
    except (InvalidOnboardingLifecycle, StaleOnboardingVersion) as error:
        raise _translate(error) from error
    if not result:
        raise HTTPException(status_code=404, detail="Provisioning command not found")
    return IdentityProvisioningSummary.model_validate(result)


@router.post(
    "/api/benson/v1/identity-provisioning/{command_id}/admin-confirm",
    response_model=IdentityProvisioningSummary,
)
def confirm_identity_license_state(
    command_id: str,
    confirmation: IdentityAdminConfirmation,
    principal: Principal = Depends(_require_true_owner),
    settings: Settings = Depends(get_settings),
) -> IdentityProvisioningSummary:
    try:
        result = _commands(settings).confirm_unavailable_verification(
            command_id,
            expected_version=confirmation.expected_version,
            reason=confirmation.reason,
            evidence_reference=confirmation.evidence_reference,
            actor=principal.email,
        )
    except (InvalidOnboardingLifecycle, StaleOnboardingVersion) as error:
        raise _translate(error) from error
    if not result:
        raise HTTPException(status_code=404, detail="Provisioning command not found")
    try:
        bootstrap_password = None
        if result.get("bootstrap_credential"):
            bootstrap_password = open_secret(
                str(result["bootstrap_credential"]),
                settings.employee_document_key_bytes(),
                context=str(result["id"]),
            )
        _queue_invitation(
            settings,
            str(result["employee_id"]),
            actor=principal.email,
            bootstrap_password=bootstrap_password,
        )
    except InvalidEmployeeInvite as error:
        raise _translate(error) from error
    return IdentityProvisioningSummary.model_validate(result)


@router.post(
    "/api/benson/v1/identity-provisioning/{command_id}/retry",
    response_model=IdentityProvisioningSummary,
)
def retry_identity_provisioning(
    command_id: str,
    mutation: IdentityCommandMutation,
    principal: Principal = Depends(_require_true_owner),
    settings: Settings = Depends(get_settings),
) -> IdentityProvisioningSummary:
    try:
        result = _commands(settings).retry(
            command_id,
            expected_version=mutation.expected_version,
            actor=principal.email,
        )
    except (InvalidOnboardingLifecycle, StaleOnboardingVersion) as error:
        raise _translate(error) from error
    if not result:
        raise HTTPException(status_code=404, detail="Provisioning command not found")
    return IdentityProvisioningSummary.model_validate(result)


@router.get(
    "/api/benson/v1/employees/{employee_id}/identity-provisioning",
    response_model=list[IdentityProvisioningSummary],
)
def list_identity_provisioning(
    employee_id: str,
    _principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> list[IdentityProvisioningSummary]:
    if not store(settings).get_employee(employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return [
        IdentityProvisioningSummary.model_validate(item)
        for item in _commands(settings).list_for_employee(employee_id)
    ]


@router.post("/api/internal/v1/identity-provisioning/drain")
def drain_identity_provisioning(
    worker: str = Depends(require_identity_provisioning_worker),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        config = DirectoryProviderConfig.from_settings(settings)
        provider = GoogleDirectoryProvider(config)
        processed = IdentityProvisioningWorker(
            store(settings).engine,
            provider,
            settings.employee_document_key_bytes(),
        ).process_one(worker=worker)
        if processed and processed["status"] == "verified":
            _queue_invitation(
                settings,
                str(processed["employee_id"]),
                actor=worker,
                bootstrap_password=processed.get("bootstrap_password"),
            )
    except (DirectoryProviderError, InvalidEmployeeInvite) as error:
        code = error.code if isinstance(error, DirectoryProviderError) else str(error)
        raise HTTPException(status_code=503, detail=code) from error
    return {
        "processed": bool(processed),
        "command_id": processed["id"] if processed else None,
        "status": processed["status"] if processed else None,
    }
