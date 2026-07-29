import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.modules.platform.models import LoginSession

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    permissions: frozenset[str]
    session_id: uuid.UUID

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


def create_access_token(principal: Principal) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(principal.user_id),
        "tenant": str(principal.tenant_id),
        "sid": str(principal.session_id),
        "permissions": sorted(principal.permissions),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "aud": "benson-erp",
        "iss": "benson-erp",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


async def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=["HS256"],
            audience="benson-erp",
            issuer="benson-erp",
        )
        principal = Principal(
            user_id=uuid.UUID(payload["sub"]),
            tenant_id=uuid.UUID(payload["tenant"]),
            session_id=uuid.UUID(payload["sid"]),
            permissions=frozenset(payload.get("permissions", [])),
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(principal.tenant_id)},
    )
    active_session = await session.scalar(
        select(LoginSession.id).where(
            LoginSession.tenant_id == principal.tenant_id,
            LoginSession.id == principal.session_id,
            LoginSession.user_id == principal.user_id,
            LoginSession.revoked_at.is_(None),
            LoginSession.expires_at > datetime.now(UTC),
        )
    )
    if active_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
    request.state.principal = principal
    return principal
