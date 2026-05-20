"""‌⁠‍Notification API routes.

Endpoints:
    GET    /                              — list current user's notifications
    GET    /unread-count                  — unread count for current user
    POST   /{notification_id}/read        — mark single as read
    POST   /read-all                      — mark all as read
    DELETE /{notification_id}             — delete single notification

Preferences + digest (Wave 3 / T9):
    GET    /preferences/                  — current user's prefs
    POST   /preferences/                  — upsert a pref row
    POST   /digest/flush                  — admin manual digest flush
    GET    /event-types/                  — known event-type catalogue
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    CurrentUserId,
    CurrentUserPayload,
    SessionDep,
)
from app.modules.notifications.schemas import (
    EventTypeCatalogEntry,
    NotificationListResponse,
    NotificationResponse,
    PreferenceRequest,
    PreferenceResponse,
)
from app.modules.notifications.service import (
    _DIGEST_FLUSHER,
    KNOWN_EVENT_TYPES,
    NotificationService,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> NotificationService:
    return NotificationService(session)


def _to_response(n: object) -> NotificationResponse:
    """‌⁠‍Build a NotificationResponse from a Notification ORM object."""
    return NotificationResponse(
        id=n.id,  # type: ignore[attr-defined]
        user_id=n.user_id,  # type: ignore[attr-defined]
        notification_type=n.notification_type,  # type: ignore[attr-defined]
        entity_type=n.entity_type,  # type: ignore[attr-defined]
        entity_id=n.entity_id,  # type: ignore[attr-defined]
        title_key=n.title_key,  # type: ignore[attr-defined]
        body_key=n.body_key,  # type: ignore[attr-defined]
        body_context=n.body_context or {},  # type: ignore[attr-defined]
        action_url=n.action_url,  # type: ignore[attr-defined]
        is_read=n.is_read,  # type: ignore[attr-defined]
        read_at=n.read_at,  # type: ignore[attr-defined]
        metadata=getattr(n, "metadata_", {}),  # type: ignore[attr-defined]
        created_at=n.created_at,  # type: ignore[attr-defined]
        updated_at=n.updated_at,  # type: ignore[attr-defined]
    )


# ── List ────────────────────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse, include_in_schema=False)
@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    user_id: CurrentUserId,
    service: NotificationService = Depends(_get_service),
    is_read: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NotificationListResponse:
    """‌⁠‍List current user's notifications (paginated)."""
    items, total = await service.list_for_user(
        user_id, is_read=is_read, limit=limit, offset=offset
    )
    unread = await service.count_unread(user_id)
    return NotificationListResponse(
        items=[_to_response(i) for i in items],
        total=total,
        unread_count=unread,
    )


# ── Unread count ────────────────────────────────────────────────────────────


@router.get("/unread-count/")
async def unread_count(
    user_id: CurrentUserId,
    service: NotificationService = Depends(_get_service),
) -> dict[str, int]:
    """Get the number of unread notifications for the current user."""
    count = await service.count_unread(user_id)
    return {"count": count}


# ── Mark read ───────────────────────────────────────────────────────────────


@router.post("/{notification_id}/read/")
async def mark_read(
    notification_id: uuid.UUID,
    user_id: CurrentUserId,
    service: NotificationService = Depends(_get_service),
) -> dict[str, bool]:
    """Mark a single notification as read."""
    updated = await service.mark_read(notification_id, user_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or already read",
        )
    return {"success": True}


@router.post("/read-all/")
async def mark_all_read(
    user_id: CurrentUserId,
    service: NotificationService = Depends(_get_service),
) -> dict[str, int]:
    """Mark all notifications as read for the current user."""
    count = await service.mark_all_read(user_id)
    return {"marked_read": count}


# ── Delete ──────────────────────────────────────────────────────────────────


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: uuid.UUID,
    user_id: CurrentUserId,
    service: NotificationService = Depends(_get_service),
) -> None:
    """Delete a single notification."""
    deleted = await service.delete(notification_id, user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )


# ── Preferences + digest (Wave 3 / T9) ─────────────────────────────────────


def _pref_to_response(p: object) -> PreferenceResponse:
    return PreferenceResponse(
        id=p.id,  # type: ignore[attr-defined]
        user_id=p.user_id,  # type: ignore[attr-defined]
        event_type=p.event_type,  # type: ignore[attr-defined]
        channel=p.channel,  # type: ignore[attr-defined]
        enabled=p.enabled,  # type: ignore[attr-defined]
        digest=p.digest,  # type: ignore[attr-defined]
        created_at=p.created_at,  # type: ignore[attr-defined]
        updated_at=p.updated_at,  # type: ignore[attr-defined]
    )


@router.get("/preferences/", response_model=list[PreferenceResponse])
async def list_preferences(
    user_id: CurrentUserId,
    service: NotificationService = Depends(_get_service),
) -> list[PreferenceResponse]:
    """‌⁠‍Return all notification preferences for the current user."""
    prefs = await service.get_preferences(user_id)
    return [_pref_to_response(p) for p in prefs]


@router.post("/preferences/", response_model=PreferenceResponse)
async def upsert_preference(
    body: PreferenceRequest,
    user_id: CurrentUserId,
    service: NotificationService = Depends(_get_service),
) -> PreferenceResponse:
    """‌⁠‍Upsert a single (event_type, channel) preference for the current user."""
    pref = await service.set_preference(
        user_id,
        event_type=body.event_type,
        channel=body.channel,
        enabled=body.enabled,
        digest=body.digest,
    )
    return _pref_to_response(pref)


@router.get("/event-types/", response_model=list[EventTypeCatalogEntry])
async def list_event_types(
    user_id: CurrentUserId,  # noqa: ARG001 — auth gate only
) -> list[EventTypeCatalogEntry]:
    """‌⁠‍Return the catalogue of known event-types the platform may emit."""
    return [EventTypeCatalogEntry(**entry) for entry in KNOWN_EVENT_TYPES]


@router.post("/digest/flush/")
async def flush_digest(
    payload: CurrentUserPayload,
    channel: str = Query(default="email", pattern=r"^(email|inapp|webhook)$"),
) -> dict[str, int | str]:
    """‌⁠‍Manually trigger a digest flush for the given channel.

    Admin-only — guarded inline because ``notifications.admin`` is not yet
    registered with the global permission registry; falling back to the
    ``role == 'admin'`` check matches the pattern used by
    :class:`RequirePermission` for the admin role bypass.
    """
    role = payload.get("role", "")
    permissions = payload.get("permissions", []) or []
    if role != "admin" and "notifications.admin" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    count = await _DIGEST_FLUSHER(channel)
    return {"channel": channel, "rows_sent": count}
