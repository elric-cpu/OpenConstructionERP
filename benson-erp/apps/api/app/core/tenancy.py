import uuid
from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import Principal, get_principal


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def get_tenant_session(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[AsyncSession]:
    await set_tenant_context(session, principal.tenant_id)
    yield session
