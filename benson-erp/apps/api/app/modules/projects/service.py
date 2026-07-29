import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.crm.models import Lead, LeadStatus
from app.modules.estimating.models import Estimate, EstimateLine, Proposal, ProposalStatus
from app.modules.platform.audit import add_audit, add_outbox
from app.modules.projects.models import BudgetLine, Contract, Project
from app.modules.projects.schemas import ProjectCreate, ProjectCreationRead, ProjectRead


async def list_projects(
    session: AsyncSession,
    principal: Principal,
) -> list[Project]:
    principal.require("projects.read")
    return list(
        await session.scalars(
            select(Project)
            .where(Project.tenant_id == principal.tenant_id)
            .order_by(Project.project_number)
        )
    )


async def create_project_from_proposal(
    session: AsyncSession,
    principal: Principal,
    proposal_id: uuid.UUID,
    data: ProjectCreate,
) -> ProjectCreationRead:
    principal.require("projects.create")
    existing = await session.scalar(
        select(Project).where(
            Project.tenant_id == principal.tenant_id, Project.proposal_id == proposal_id
        )
    )
    if existing is not None:
        contract = await session.scalar(
            select(Contract).where(
                Contract.tenant_id == principal.tenant_id, Contract.id == existing.contract_id
            )
        )
        if contract is None:
            raise HTTPException(status_code=409, detail="Project contract lineage is incomplete")
        count = len(
            list(
                await session.scalars(
                    select(BudgetLine).where(
                        BudgetLine.tenant_id == principal.tenant_id,
                        BudgetLine.project_id == existing.id,
                    )
                )
            )
        )
        return ProjectCreationRead(
            project=ProjectRead.model_validate(existing),
            contract_value=contract.value,
            budget_line_count=count,
        )

    proposal = await session.scalar(
        select(Proposal).where(
            Proposal.tenant_id == principal.tenant_id, Proposal.id == proposal_id
        )
    )
    if proposal is None or proposal.status is not ProposalStatus.ACCEPTED:
        raise HTTPException(status_code=409, detail="Accepted proposal required")
    estimate = await session.scalar(
        select(Estimate).where(
            Estimate.tenant_id == principal.tenant_id, Estimate.id == proposal.estimate_id
        )
    )
    if estimate is None:
        raise HTTPException(status_code=409, detail="Proposal estimate lineage is incomplete")
    lead = await session.scalar(
        select(Lead).where(Lead.tenant_id == principal.tenant_id, Lead.id == estimate.lead_id)
    )
    if lead is None or lead.customer_id is None or lead.property_id is None:
        raise HTTPException(status_code=409, detail="Proposal lineage is incomplete")

    contract = Contract(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        proposal_id=proposal.id,
        contract_number=data.contract_number,
        value=estimate.total,
    )
    session.add(contract)
    await session.flush()
    project = Project(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        proposal_id=proposal.id,
        contract_id=contract.id,
        customer_id=lead.customer_id,
        property_id=lead.property_id,
        project_number=data.project_number,
        name=data.name,
    )
    session.add(project)
    await session.flush()
    lines = list(
        await session.scalars(
            select(EstimateLine).where(
                EstimateLine.tenant_id == principal.tenant_id,
                EstimateLine.estimate_id == estimate.id,
            )
        )
    )
    for line in lines:
        cost = Decimal(line.quantity * line.unit_cost).quantize(Decimal("0.01"))
        session.add(
            BudgetLine(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                updated_by=principal.user_id,
                project_id=project.id,
                source_estimate_line_id=line.id,
                description=line.description,
                original_cost=cost,
                revised_cost=cost,
            )
        )
    lead.status = LeadStatus.WON
    lead.version += 1
    lead.updated_by = principal.user_id
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "Project",
        project.id,
        "created_from_proposal",
        correlation_id,
        None,
        {"contract_id": str(contract.id), "proposal_id": str(proposal.id)},
    )
    add_outbox(
        session,
        principal,
        "ProjectCreated",
        "Project",
        project.id,
        correlation_id,
        f"project-created:proposal:{proposal.id}",
        {"project_id": str(project.id), "contract_id": str(contract.id)},
    )
    await session.commit()
    return ProjectCreationRead(
        project=ProjectRead.model_validate(project),
        contract_value=contract.value,
        budget_line_count=len(lines),
    )
