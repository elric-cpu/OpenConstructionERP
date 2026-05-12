"""‌⁠‍Document Management Pydantic schemas — request/response models.

Defines create, update, and response schemas for documents.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Document schemas ─────────────────────────────────────────────────────


class DocumentUpdate(BaseModel):
    """‌⁠‍Partial update for a document."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(
        default=None,
        pattern=r"^(drawing|contract|specification|photo|correspondence|other)$",
    )
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    # Phase 17: CDE / revision-chain fields
    cde_state: str | None = Field(
        default=None,
        pattern=r"^(wip|shared|published|archived)$",
    )
    suitability_code: str | None = Field(default=None, max_length=10)
    revision_code: str | None = Field(default=None, max_length=20)
    drawing_number: str | None = Field(default=None, max_length=100)
    is_current_revision: bool | None = None
    parent_document_id: UUID | None = None
    security_classification: str | None = Field(default=None, max_length=50)
    discipline: str | None = Field(
        default=None,
        pattern=r"^(architectural|structural|mechanical|electrical|plumbing|civil)$",
    )


class DocumentResponse(BaseModel):
    """‌⁠‍Document returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    name: str
    description: str
    category: str
    file_size: int = 0
    mime_type: str = ""
    version: int = 1
    uploaded_by: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    # Phase 17: CDE / revision-chain fields
    cde_state: str | None = None
    suitability_code: str | None = None
    revision_code: str | None = None
    drawing_number: str | None = None
    is_current_revision: bool | None = True
    parent_document_id: UUID | None = None
    security_classification: str | None = None
    discipline: str | None = None


# ── Summary schema ───────────────────────────────────────────────────────


class RecentUpload(BaseModel):
    """A recently uploaded document summary."""

    name: str
    uploaded_at: str
    size: int = 0


class DocumentSummary(BaseModel):
    """Aggregated document stats for a project."""

    total: int = 0
    total_documents: int = 0
    total_size_bytes: int = 0
    total_size_mb: float = 0.0
    by_category: dict[str, int] = Field(default_factory=dict)
    recent_uploads: list[RecentUpload] = Field(default_factory=list)


# ── Photo schemas ───────────────────────────────────────────────────────


class PhotoUpdate(BaseModel):
    """Partial update for a project photo."""

    model_config = ConfigDict(str_strip_whitespace=True)

    caption: str | None = None
    tags: list[str] | None = None
    category: str | None = Field(
        default=None,
        pattern=r"^(site|progress|defect|delivery|safety|other)$",
    )


class PhotoResponse(BaseModel):
    """Photo returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    document_id: str | None = None
    filename: str
    file_path: str = ""
    caption: str | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    tags: list[str] = Field(default_factory=list)
    taken_at: datetime | None = None
    category: str = "site"
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_by: str = ""
    created_at: datetime
    updated_at: datetime
    # True when a server-side thumbnail exists for this photo. Clients should
    # prefer the thumb endpoint for grid/timeline renders and only fall back
    # to the full file when this is false or the client needs the original.
    has_thumbnail: bool = False


class PhotoTimelineGroup(BaseModel):
    """Photos grouped by date for timeline view."""

    date: str
    photos: list[PhotoResponse]


# ── Sheet schemas ──────────────────────────────────────────────────────


class SheetUpdate(BaseModel):
    """Partial update for a drawing sheet."""

    model_config = ConfigDict(str_strip_whitespace=True)

    sheet_number: str | None = Field(default=None, max_length=100)
    sheet_title: str | None = Field(default=None, max_length=500)
    discipline: str | None = Field(default=None, max_length=100)
    revision: str | None = Field(default=None, max_length=50)
    revision_date: datetime | None = None
    scale: str | None = Field(default=None, max_length=50)
    is_current: bool | None = None
    metadata: dict[str, Any] | None = None


class SheetResponse(BaseModel):
    """Sheet returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    document_id: str = ""
    page_number: int
    sheet_number: str | None = None
    sheet_title: str | None = None
    discipline: str | None = None
    revision: str | None = None
    revision_date: datetime | None = None
    scale: str | None = None
    is_current: bool = True
    previous_version_id: UUID | None = None
    thumbnail_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_by: str = ""
    created_at: datetime
    updated_at: datetime


class SheetVersionHistory(BaseModel):
    """Version history for a sheet — list of all revisions."""

    current: SheetResponse
    history: list[SheetResponse] = Field(default_factory=list)


# ── DocumentBIMLink schemas ─────────────────────────────────────────────


class DocumentBIMLinkCreate(BaseModel):
    """Create a link between a Document and a BIM element."""

    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: UUID
    bim_element_id: UUID
    link_type: str = Field(default="manual", max_length=50)
    confidence: str | None = Field(default=None, max_length=10)
    region_bbox: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentBIMLinkResponse(BaseModel):
    """Full DocumentBIMLink row returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    document_id: UUID
    bim_element_id: UUID
    link_type: str
    confidence: str | None = None
    region_bbox: dict[str, Any] | None = None
    created_by: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class DocumentBIMLinkBrief(BaseModel):
    """Compact DocumentBIMLink for embedding inside BIMElementResponse.

    Contains just enough data for the viewer to render a link badge and
    navigate to the linked document without a second round trip.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    document_id: UUID
    document_name: str | None = None
    document_category: str | None = None
    link_type: str
    confidence: str | None = None


class DocumentBIMLinkListResponse(BaseModel):
    """List of DocumentBIMLink rows."""

    items: list[DocumentBIMLinkResponse] = Field(default_factory=list)
    total: int = 0


# ── BIMElementBrief ─────────────────────────────────────────────────────
#
# A compact BIM element shape that lives in the documents schemas module so
# DocumentResponse (and any future document-centric aggregate responses) can
# embed linked BIM elements without importing from bim_hub.schemas, which
# would introduce a circular dependency.


class BIMElementBrief(BaseModel):
    """Lightweight BIM element summary for embedding inside document responses."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    model_id: UUID
    element_type: str | None = None
    name: str | None = None
    storey: str | None = None
    discipline: str | None = None


# ── Activity log ─────────────────────────────────────────────────────────


class DocumentActivityResponse(BaseModel):
    """Single audit event from the per-document activity timeline."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    document_id: UUID
    user_id: str | None = None
    action: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ── Share links ──────────────────────────────────────────────────────────


class ShareLinkCreate(BaseModel):
    """Create a password-protected share link for a document.

    Both fields are optional:
        * ``password`` — when omitted (or empty), the link is open
          and any recipient who knows the URL can download.
        * ``expires_in_days`` — when omitted, the link never
          expires. ``0`` is rejected as a likely typo; callers
          wanting "immediately expire" should DELETE instead.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    password: str | None = Field(default=None, min_length=1, max_length=128)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ShareLinkResponse(BaseModel):
    """Newly minted share link, returned to the owner."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    token: str
    url: str
    document_id: UUID
    requires_password: bool = False
    expires_at: datetime | None = None
    created_at: datetime
    download_count: int = 0
    revoked: bool = False


class ShareLinkListItem(BaseModel):
    """Compact row in the owner-only "existing links" list."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    token: str
    url: str
    requires_password: bool = False
    expires_at: datetime | None = None
    created_at: datetime
    download_count: int = 0
    revoked: bool = False


class ShareLinkPublicInfo(BaseModel):
    """Public probe response — what the recipient sees before unlocking.

    Intentionally omits ``download_count`` and ``id``/``created_by`` so
    nothing about the owner or usage history leaks to recipients.
    """

    filename: str
    requires_password: bool = False
    expired: bool = False


class ShareLinkAccessRequest(BaseModel):
    """Recipient submits this with the optional password."""

    model_config = ConfigDict(str_strip_whitespace=True)

    password: str | None = Field(default=None, max_length=128)


class ShareLinkAccessResponse(BaseModel):
    """Successful unlock — recipient receives the authenticated download URL."""

    download_url: str
    filename: str


# ── Folder permissions ───────────────────────────────────────────────────


class FolderPermissionCreate(BaseModel):
    """Owner-supplied grant payload.

    ``scope_path`` is optional — when omitted the grant applies to
    every file of ``scope_kind`` in the project (a "kind-wide"
    grant).  Empty-string and explicit ``null`` are treated the same.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: UUID
    scope_kind: str = Field(min_length=1, max_length=50)
    scope_path: str | None = Field(default=None, max_length=500)
    role: str = Field(
        default="viewer",
        pattern=r"^(viewer|editor|owner)$",
    )


class FolderPermissionResponse(BaseModel):
    """Single grant row returned by the management endpoints."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    scope_kind: str
    scope_path: str | None = None
    role: str
    granted_by: UUID
    granted_at: datetime | None = None
    revoked: bool = False
    created_at: datetime
    updated_at: datetime
    # Pre-joined for the modal so it doesn't have to make N member lookups.
    user_email: str | None = None
    user_full_name: str | None = None
