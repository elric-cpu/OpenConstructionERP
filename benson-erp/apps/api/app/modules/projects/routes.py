import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.projects.schemas import ProjectCreate, ProjectCreationRead, ProjectRead
from app.modules.projects.service import create_project_from_proposal, list_projects

router = APIRouter(tags=["projects"])


@router.post("/proposals/{proposal_id}/create-project", response_model=ProjectCreationRead)
async def create_project(
    proposal_id: uuid.UUID,
    data: ProjectCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ProjectCreationRead:
    return await create_project_from_proposal(session, principal, proposal_id, data)


@router.get("/projects", response_model=list[ProjectRead])
async def get_projects(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ProjectRead]:
    return [
        ProjectRead.model_validate(project)
        for project in await list_projects(session, principal)
    ]
