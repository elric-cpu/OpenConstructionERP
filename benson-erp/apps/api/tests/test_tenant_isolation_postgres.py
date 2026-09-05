import os
import uuid

import pytest
from app.core.database import SessionFactory
from app.modules.crm.models import Lead
from sqlalchemy import select, text

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1", reason="PostgreSQL integration tests disabled"
    ),
]


async def test_database_rls_hides_another_tenants_lead() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    lead_id = uuid.uuid4()
    async with SessionFactory() as tenant_a_session:
        await tenant_a_session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_a)},
        )
        tenant_a_session.add(
            Lead(
                id=lead_id,
                tenant_id=tenant_a,
                created_by=actor,
                updated_by=actor,
                contact_name="Tenant A Customer",
                source="TEST",
                summary="RLS verification",
            )
        )
        await tenant_a_session.commit()

    async with SessionFactory() as tenant_b_session:
        await tenant_b_session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_b)},
        )
        leaked = await tenant_b_session.scalar(select(Lead).where(Lead.id == lead_id))
        assert leaked is None

    async with SessionFactory() as cleanup_session:
        await cleanup_session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_a)},
        )
        record = await cleanup_session.get(Lead, lead_id)
        assert record is not None
        await cleanup_session.delete(record)
        await cleanup_session.commit()
