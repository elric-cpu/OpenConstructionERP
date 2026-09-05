import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.database import SessionFactory
from app.core.security import Principal, create_access_token
from app.main import app
from app.modules.crm.models import Customer, Lead, Property
from app.modules.documents.models import Document
from app.modules.estimating.models import Estimate, EstimateLine, EstimateSection, Proposal
from app.modules.platform.models import (
    AuditEvent,
    InboxReceipt,
    LoginSession,
    Organization,
    OutboxEvent,
)
from app.modules.projects.models import BudgetLine, Contract, Project
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1", reason="PostgreSQL integration tests disabled"
    ),
]


async def test_complete_lead_to_project_api_workflow() -> None:
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    principal = Principal(
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=uuid.uuid4(),
        permissions=frozenset(
            {
                "leads.create",
                "leads.qualify",
                "leads.convert",
                "estimates.create",
                "estimates.write",
                "estimates.approve",
                "proposals.create",
                "proposals.read",
                "proposals.accept",
                "projects.create",
            }
        ),
    )
    await _seed_session(principal)
    request_correlation_id = uuid.uuid4()
    headers = {
        "Authorization": f"Bearer {create_access_token(principal)}",
        "X-Correlation-ID": str(request_correlation_id),
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://benson-ai", headers=headers
    ) as client:
        lead_response = await client.post(
            "/api/v1/leads",
            json={
                "contact_name": "Ada Builder",
                "email": f"ada+{tenant_id}@bensonhomesolutions.com",
                "phone": "458-555-0100",
                "source": "WEBSITE",
                "summary": "Residential addition",
            },
        )
        assert lead_response.status_code == 201, lead_response.text
        assert lead_response.headers["X-Correlation-ID"] == str(request_correlation_id)
        lead = lead_response.json()
        qualified_response = await client.post(
            f"/api/v1/leads/{lead['id']}/qualify",
            json={"reason": "Budget and property confirmed", "expected_version": 1},
        )
        assert qualified_response.status_code == 200
        converted_response = await client.post(
            f"/api/v1/leads/{lead['id']}/convert",
            json={
                "property": {
                    "address_line_1": "100 Main Street",
                    "city": "Burns",
                    "state": "OR",
                    "postal_code": "97720",
                },
                "expected_version": 2,
            },
        )
        assert converted_response.status_code == 200

        estimate_response = await client.post(
            "/api/v1/estimates",
            json={
                "lead_id": lead["id"],
                "pricing_mode": "MARKUP",
                "pricing_rate": "0.20",
                "tax_rate": "0",
            },
        )
        assert estimate_response.status_code == 201
        estimate = estimate_response.json()
        line_response = await client.post(
            f"/api/v1/estimates/{estimate['id']}/lines",
            json={
                "section_title": "01 General Requirements",
                "description": "Mobilization",
                "quantity": "2",
                "unit": "EA",
                "unit_cost": "500",
                "category": "OTHER",
                "position": 1,
                "expected_version": 1,
            },
        )
        assert line_response.status_code == 200
        assert Decimal(line_response.json()["total"]) == Decimal("1200.00")
        approved_response = await client.post(
            f"/api/v1/estimates/{estimate['id']}/approve", headers={"If-Match": "2"}
        )
        assert approved_response.status_code == 200
        proposal_response = await client.post(f"/api/v1/estimates/{estimate['id']}/proposals")
        assert proposal_response.status_code == 200
        proposal = proposal_response.json()
        assert "direct_cost" not in proposal["price_snapshot"]
        assert len(proposal["document_checksum"]) == 64
        document_response = await client.get(
            f"/api/v1/proposals/{proposal['id']}/document"
        )
        assert document_response.status_code == 200
        assert document_response.content.startswith(b"%PDF")
        assert document_response.headers["etag"] == f'"{proposal["document_checksum"]}"'
        access_response = await client.post(
            f"/api/v1/proposals/{proposal['id']}/document-access"
        )
        assert access_response.status_code == 200
        assert access_response.json()["url"] is None
        assert access_response.json()["proxied"] is True
        accepted_response = await client.post(
            f"/api/v1/proposals/{proposal['id']}/accept",
            json={
                "accepted_by_name": "Ada Builder",
                "consent": True,
                "acceptance_statement": (
                    "I accept this proposal and authorize the described construction work."
                ),
                "expected_version": 1,
            },
        )
        assert accepted_response.status_code == 200
        project_response = await client.post(
            f"/api/v1/proposals/{proposal['id']}/create-project",
            json={
                "name": "Ada Builder Addition",
                "project_number": "PRJ-TEST-001",
                "contract_number": "CON-TEST-001",
            },
        )
        assert project_response.status_code == 200
        assert project_response.json()["budget_line_count"] == 1
        assert Decimal(project_response.json()["contract_value"]) == Decimal("1200.00")

    async with SessionFactory() as session:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_id)},
        )
        lead_created = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "LeadCreated",
            )
        )
        assert lead_created is not None
        assert lead_created.correlation_id == request_correlation_id

    await _clean_tenant(tenant_id)


async def _clean_tenant(tenant_id: uuid.UUID) -> None:
    tables = (
        BudgetLine,
        Project,
        Contract,
        InboxReceipt,
        Document,
        Proposal,
        EstimateLine,
        EstimateSection,
        Estimate,
        Lead,
        Property,
        Customer,
        OutboxEvent,
        AuditEvent,
        LoginSession,
    )
    async with SessionFactory() as session:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_id)},
        )
        for model in tables:
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Organization).where(Organization.id == tenant_id))
        await session.commit()


async def _seed_session(principal: Principal) -> None:
    async with SessionFactory() as session:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(principal.tenant_id)},
        )
        session.add(
            LoginSession(
                id=principal.session_id,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                refresh_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.add(
            Organization(
                id=principal.tenant_id,
                name="Benson Test Construction",
                slug=f"benson-test-{principal.tenant_id}",
                phone="458-723-0818",
            )
        )
        await session.commit()
