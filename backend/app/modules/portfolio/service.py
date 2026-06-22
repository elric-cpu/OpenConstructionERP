# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Portfolio tree service (T3.3).

Node CRUD, project membership, and the access-pruned tree. Every read
intersects with ``accessible_project_ids`` and every project write goes through
``verify_project_access`` - the tree is navigation only and never widens access.
All writes ``flush`` only; the request middleware owns the commit.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import accessible_project_ids, verify_project_access
from app.modules.portfolio.models import PortfolioMembership, PortfolioNode
from app.modules.portfolio.schemas import NodeCreate, NodePatch
from app.modules.portfolio.tree_logic import build_visible_tree


def _not_found(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


class PortfolioService:
    """Business logic for portfolio nodes + memberships."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _is_admin(self, user_id: str) -> bool:
        # accessible_project_ids returns None only for admins (no scope filter).
        return (await accessible_project_ids(self.session, user_id)) is None

    async def get_node(self, node_id: uuid.UUID) -> PortfolioNode:
        node = await self.session.get(PortfolioNode, node_id)
        if node is None:
            raise _not_found("Portfolio node not found")
        return node

    # ── Tree ─────────────────────────────────────────────────────────────────

    async def get_tree(self, user_id: str) -> list[dict]:
        scope = await accessible_project_ids(self.session, user_id)
        nodes = (await self.session.execute(select(PortfolioNode))).scalars().all()
        memberships = (await self.session.execute(select(PortfolioMembership))).scalars().all()

        node_rows = [
            {
                "id": str(n.id),
                "parent_id": str(n.parent_id) if n.parent_id else None,
                "node_type": n.node_type,
                "name": n.name,
                "code": n.code,
                "sort_order": n.sort_order,
            }
            for n in nodes
        ]
        membership_rows = [{"node_id": str(m.node_id), "project_id": str(m.project_id)} for m in memberships]
        accessible = None if scope is None else {str(p) for p in scope}
        return build_visible_tree(node_rows, membership_rows, accessible)

    # ── Node CRUD ────────────────────────────────────────────────────────────

    async def create_node(self, data: NodeCreate, user_id: str) -> PortfolioNode:
        if data.parent_id is not None:
            await self.get_node(data.parent_id)  # 404 if the parent is missing
        node = PortfolioNode(
            parent_id=data.parent_id,
            node_type=data.node_type,
            name=data.name,
            code=data.code,
            owner_id=uuid.UUID(str(user_id)),
            sort_order=data.sort_order,
            metadata_=data.metadata or {},
        )
        self.session.add(node)
        await self.session.flush()
        return node

    async def _require_manageable(self, node: PortfolioNode, user_id: str) -> None:
        if await self._is_admin(user_id):
            return
        if str(node.owner_id) != str(user_id):
            # Existence-oracle safe: a non-owner cannot tell the node exists.
            raise _not_found("Portfolio node not found")

    async def _assert_no_cycle(self, node_id: uuid.UUID, new_parent_id: uuid.UUID) -> None:
        if str(new_parent_id) == str(node_id):
            raise _unprocessable("A node cannot be its own parent")
        cur = await self.session.get(PortfolioNode, new_parent_id)
        seen: set[str] = set()
        while cur is not None:
            if str(cur.id) == str(node_id):
                raise _unprocessable("Reparenting would create a cycle")
            if str(cur.id) in seen:
                break
            seen.add(str(cur.id))
            cur = await self.session.get(PortfolioNode, cur.parent_id) if cur.parent_id else None

    async def patch_node(self, node_id: uuid.UUID, data: NodePatch, user_id: str) -> PortfolioNode:
        node = await self.get_node(node_id)
        await self._require_manageable(node, user_id)

        fields_set = data.model_fields_set
        if "parent_id" in fields_set:
            if data.parent_id is None:
                node.parent_id = None
            else:
                await self._assert_no_cycle(node_id, data.parent_id)
                await self.get_node(data.parent_id)  # 404 if the new parent is missing
                node.parent_id = data.parent_id
        if data.name is not None:
            node.name = data.name
        if data.node_type is not None:
            node.node_type = data.node_type
        if data.code is not None:
            node.code = data.code
        if data.sort_order is not None:
            node.sort_order = data.sort_order

        await self.session.flush()
        return node

    async def delete_node(self, node_id: uuid.UUID, user_id: str) -> None:
        node = await self.get_node(node_id)
        await self._require_manageable(node, user_id)
        await self.session.delete(node)  # memberships cascade; child nodes -> root
        await self.session.flush()

    # ── Membership ───────────────────────────────────────────────────────────

    async def attach_project(self, node_id: uuid.UUID, project_id: uuid.UUID, user_id: str) -> None:
        await self.get_node(node_id)
        # Cannot file a project the caller cannot reach (404 on deny).
        await verify_project_access(project_id, user_id, self.session)
        existing = (
            await self.session.execute(select(PortfolioMembership).where(PortfolioMembership.project_id == project_id))
        ).scalar_one_or_none()
        if existing is not None:
            existing.node_id = node_id  # a project sits in exactly one node -> move
        else:
            self.session.add(PortfolioMembership(node_id=node_id, project_id=project_id))
        await self.session.flush()

    async def detach_project(self, node_id: uuid.UUID, project_id: uuid.UUID, user_id: str) -> None:
        await self.get_node(node_id)
        await verify_project_access(project_id, user_id, self.session)
        await self.session.execute(
            sa_delete(PortfolioMembership).where(
                PortfolioMembership.node_id == node_id,
                PortfolioMembership.project_id == project_id,
            )
        )
        await self.session.flush()
