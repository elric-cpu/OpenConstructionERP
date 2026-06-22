# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the portfolio tree (T3.3).

Pure (pydantic + stdlib) so it imports and unit-tests on the local runner.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NodeType = Literal["portfolio", "programme", "subprogramme"]


class NodeCreate(BaseModel):
    """Create a portfolio / programme node."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    node_type: NodeType = "programme"
    code: str = Field(default="", max_length=50)
    parent_id: UUID | None = None
    sort_order: int = Field(default=0, ge=0)
    metadata: dict = Field(default_factory=dict)


class NodePatch(BaseModel):
    """Partial update of a node (rename / reparent / reorder).

    A supplied ``parent_id`` of ``null`` moves the node to the root; omitting
    ``parent_id`` leaves the parent unchanged (distinguished via
    ``model_fields_set`` in the service).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    node_type: NodeType | None = None
    code: str | None = Field(default=None, max_length=50)
    parent_id: UUID | None = None
    sort_order: int | None = Field(default=None, ge=0)


class NodeResponse(BaseModel):
    """A portfolio node as returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    parent_id: UUID | None
    node_type: str
    name: str
    code: str
    owner_id: UUID | None
    sort_order: int
    metadata: dict = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class AttachProjectRequest(BaseModel):
    """Attach a project to a node (the project must be accessible to the caller)."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID


class TreeNode(BaseModel):
    """A node in the access-pruned portfolio tree."""

    id: UUID
    parent_id: UUID | None = None
    node_type: str
    name: str
    code: str = ""
    sort_order: int = 0
    project_ids: list[UUID] = Field(default_factory=list)
    children: list[TreeNode] = Field(default_factory=list)


TreeNode.model_rebuild()
