import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .auth import (
    Principal,
    require_notification_worker,
    require_operations_staff,
    require_owner,
    require_portal_user,
    require_staff,
    staff_role_for_email,
)
from .config import Settings, get_settings
from .dependencies import store
from .domain import (
    BENSON_MODULES,
    NotificationSettings,
    NotificationSettingsUpdate,
    PortalSession,
)
from .notifications import NotificationDeliveryError, deliver_notification

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/health")
async def health(
    request: Request, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    await run_in_threadpool(store(settings).readiness_probe)
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": request.app.version,
        "profile": {"currency": "USD", "state": "OR", "county": "Harney"},
        "storage": (
            "postgresql"
            if settings.resolved_database_url().startswith("postgresql")
            else "sqlite"
        ),
    }


@router.post("/api/internal/v1/notifications/drain")
def drain_notifications(
    _worker: str = Depends(require_notification_worker),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    notification_store = store(settings)
    claimed = notification_store.claim_notifications(
        limit=settings.notification_batch_size
    )
    remaining = max(0, settings.notification_batch_size - len(claimed))
    if remaining:
        claimed.extend(notification_store.claim_employee_notifications(limit=remaining))
    sent = 0
    failed = 0
    sms_enabled = (
        notification_store.notification_settings(
            sms_enabled_default=settings.sms_enabled_default
        )["sms_enabled"]
        and settings.twilio_is_configured()
    )
    for item in claimed:
        if item["channel"] == "sms" and not sms_enabled:
            notification_store.mark_notification_disabled(item["id"])
            continue
        try:
            result = deliver_notification(item, settings)
        except NotificationDeliveryError:
            failed += 1
            notification_store.mark_notification_failed(
                item["id"],
                "provider delivery failed",
                outbox_type=item["outbox_type"],
            )
            logger.exception(
                "notification_delivery_failed notification_id=%s channel=%s attempt=%s",
                item["id"],
                item["channel"],
                int(item["attempts"]) + 1,
            )
        else:
            sent += 1
            notification_store.mark_notification_sent(
                item["id"],
                result.provider_message_id,
                outbox_type=item["outbox_type"],
            )
    counts = notification_store.notification_counts()
    logger.info(
        "notification_drain_complete claimed=%s sent=%s failed=%s pending=%s exhausted=%s",
        len(claimed),
        sent,
        failed,
        counts.get("pending", 0),
        counts.get("failed", 0),
    )
    return {"claimed": len(claimed), "sent": sent, "failed": failed, "outbox": counts}


@router.get(
    "/api/benson/v1/settings/notifications", response_model=NotificationSettings
)
def get_notification_settings(
    _principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> NotificationSettings:
    saved = store(settings).notification_settings(
        sms_enabled_default=settings.sms_enabled_default
    )
    return NotificationSettings(
        sms_enabled=saved["sms_enabled"],
        sms_configured=settings.twilio_is_configured(),
    )


@router.patch(
    "/api/benson/v1/settings/notifications", response_model=NotificationSettings
)
def update_notification_settings(
    change: NotificationSettingsUpdate,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> NotificationSettings:
    if change.sms_enabled and not settings.twilio_is_configured():
        raise HTTPException(status_code=409, detail="Twilio is not configured")
    saved = store(settings).update_notification_settings(
        sms_enabled=change.sms_enabled, actor=principal.email
    )
    return NotificationSettings(
        sms_enabled=saved["sms_enabled"],
        sms_configured=settings.twilio_is_configured(),
    )


@router.get("/api/benson/v1/auth/config")
async def auth_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "provider": "google_workspace",
        "client_id": settings.staff_google_audience,
        "hosted_domain": settings.staff_google_domain,
    }


@router.get("/api/benson/v1/session", response_model=PortalSession)
def portal_session(
    principal: Principal = Depends(require_portal_user),
    settings: Settings = Depends(get_settings),
) -> PortalSession:
    staff_role = staff_role_for_email(principal.email, settings)
    if staff_role:
        return PortalSession(
            kind="staff",
            email=principal.email,
            role=staff_role,
            default_view="overview",
        )
    employee = store(settings).get_employee_by_identity(
        principal.email, principal.subject
    )
    if not employee:
        raise HTTPException(status_code=403, detail="Active employee account required")
    return PortalSession(
        kind="employee",
        email=principal.email,
        role=employee.role,
        default_view="tasks",
        employee=employee,
    )


@router.get("/api/v1/config/modules")
async def modules(principal: Principal = Depends(require_staff)) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for module in BENSON_MODULES:
        if principal.role in module.roles:
            grouped[module.group].append({"id": module.id, "label": module.label})
    return {"role": principal.role, "groups": grouped}


@router.get("/api/benson/v1/staff")
async def staff_directory(
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return {"staff": settings.assignable_staff()}
