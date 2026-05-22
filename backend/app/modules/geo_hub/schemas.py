# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Geo Hub Pydantic schemas — request / response models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Regex patterns shared across create + update + response shapes.
_SOURCE_KIND_PATTERN = (
    r"^(bim_model|federation|development|upload|point_cloud|photogrammetry)$"
)
_TILESET_STATUS_PATTERN = r"^(draft|generating|ready|failed|obsolete)$"
_TILE_FORMAT_PATTERN = r"^(b3dm|i3dm|pnts|cmpt)$"
_JOB_STATE_PATTERN = r"^(queued|running|completed|failed|cancelled)$"
_IMAGERY_PROVIDER_PATTERN = r"^(osm|bing|wms|wmts|custom)$"
_TERRAIN_PROVIDER_PATTERN = r"^(cesium_world|quantized_mesh|ellipsoid)$"
_OVERLAY_KIND_PATTERN = (
    r"^(boundary|survey|contour|drone_photo|site_plan|easement|"
    r"flood_zone|clash_marker|incident|field_report|risk_zone)$"
)
_REGION_CODE_PATTERN = r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$"


# Common WGS84 latitude / longitude bounds.
_LAT_BOUND = (Decimal("-90"), Decimal("90"))
_LON_BOUND = (Decimal("-180"), Decimal("180"))


def _check_lat(v: Decimal) -> Decimal:
    lo, hi = _LAT_BOUND
    if not (lo <= v <= hi):
        raise ValueError(f"latitude must be in [{lo}, {hi}]")
    return v


def _check_lon(v: Decimal) -> Decimal:
    lo, hi = _LON_BOUND
    if not (lo <= v <= hi):
        raise ValueError(f"longitude must be in [{lo}, {hi}]")
    return v


# ── GeoAnchor ────────────────────────────────────────────────────────────


class GeoAnchorCreate(BaseModel):
    """Create the (unique) anchor for a project."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    lat: Decimal = Field(default=Decimal("0"))
    lon: Decimal = Field(default=Decimal("0"))
    alt: Decimal = Field(default=Decimal("0"))
    epsg_code: int = Field(default=4326, gt=0, le=999999)
    region_code: str | None = Field(default=None, pattern=_REGION_CODE_PATTERN)
    address: str | None = Field(default=None, max_length=500)
    accuracy_m: Decimal | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _v_lat = field_validator("lat")(lambda cls, v: _check_lat(v))  # type: ignore[arg-type, misc]
    _v_lon = field_validator("lon")(lambda cls, v: _check_lon(v))  # type: ignore[arg-type, misc]


class GeoAnchorUpdate(BaseModel):
    """Partial update of an anchor."""

    model_config = ConfigDict(str_strip_whitespace=True)

    lat: Decimal | None = None
    lon: Decimal | None = None
    alt: Decimal | None = None
    epsg_code: int | None = Field(default=None, gt=0, le=999999)
    region_code: str | None = Field(default=None, pattern=_REGION_CODE_PATTERN)
    address: str | None = Field(default=None, max_length=500)
    accuracy_m: Decimal | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None

    @field_validator("lat")
    @classmethod
    def _v_lat(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None else _check_lat(v)

    @field_validator("lon")
    @classmethod
    def _v_lon(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None else _check_lon(v)


class GeoAnchorResponse(BaseModel):
    """Anchor returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    lat: Decimal
    lon: Decimal
    alt: Decimal
    epsg_code: int
    region_code: str | None = None
    address: str | None = None
    accuracy_m: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Tileset ──────────────────────────────────────────────────────────────


class TilesetCreate(BaseModel):
    """Create a Tileset record (usually populated by the job, not the
    user — but exposing it is handy for tests and re-registrations)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    source_kind: str = Field(default="bim_model", pattern=_SOURCE_KIND_PATTERN)
    source_id: UUID
    name: str = Field(default="", max_length=255)
    bucket: str = Field(default="", max_length=100)
    prefix: str = Field(default="", max_length=500)
    tileset_json_uri: str | None = Field(default=None, max_length=2000)
    bounding_volume: dict[str, Any] | None = None
    geometric_error: Decimal = Field(default=Decimal("0"), ge=0)
    tile_format: str = Field(default="b3dm", pattern=_TILE_FORMAT_PATTERN)
    tile_count: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    status: str = Field(default="draft", pattern=_TILESET_STATUS_PATTERN)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TilesetUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    tileset_json_uri: str | None = Field(default=None, max_length=2000)
    bounding_volume: dict[str, Any] | None = None
    geometric_error: Decimal | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern=_TILESET_STATUS_PATTERN)
    metadata: dict[str, Any] | None = None


class TilesetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    source_kind: str
    source_id: UUID
    name: str = ""
    bucket: str = ""
    prefix: str = ""
    tileset_json_uri: str | None = None
    bounding_volume: dict[str, Any] | None = None
    geometric_error: Decimal = Decimal("0")
    tile_format: str = "b3dm"
    tile_count: int = 0
    total_bytes: int = 0
    status: str = "draft"
    generated_at: datetime | None = None
    generation_job_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class TileGenerateRequest(BaseModel):
    """Enqueue a tile-generation job."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    source_kind: str = Field(default="bim_model", pattern=_SOURCE_KIND_PATTERN)
    source_id: UUID
    # When True we re-tile even if a ``ready`` Tileset already exists
    # for the same (source_kind, source_id) pair.
    force: bool = False


class CanonicalToTilesetRequest(BaseModel):
    """Optional body for the canonical -> tileset packaging endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    heading_deg: Decimal = Field(default=Decimal("0"), ge=-360, le=720)
    name: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list)


# ── ImageryLayer ─────────────────────────────────────────────────────────


class ImageryLayerCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(default="", max_length=120)
    provider: str = Field(default="osm", pattern=_IMAGERY_PROVIDER_PATTERN)
    url_template: str = Field(default="", max_length=2000)
    attribution: str = Field(default="", max_length=500)
    requires_api_key: bool = False
    default_for_project: bool = False
    is_visible: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImageryLayerUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=120)
    provider: str | None = Field(default=None, pattern=_IMAGERY_PROVIDER_PATTERN)
    url_template: str | None = Field(default=None, max_length=2000)
    attribution: str | None = Field(default=None, max_length=500)
    requires_api_key: bool | None = None
    default_for_project: bool | None = None
    is_visible: bool | None = None
    metadata: dict[str, Any] | None = None


class ImageryLayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    name: str = ""
    provider: str = "osm"
    url_template: str = ""
    attribution: str = ""
    requires_api_key: bool = False
    default_for_project: bool = False
    is_visible: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── TerrainSource ────────────────────────────────────────────────────────


class TerrainSourceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=120)
    provider: str = Field(default="ellipsoid", pattern=_TERRAIN_PROVIDER_PATTERN)
    endpoint: str | None = Field(default=None, max_length=2000)
    ion_token: str | None = Field(default=None, max_length=500)
    is_default: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TerrainSourceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: str | None = Field(default=None, pattern=_TERRAIN_PROVIDER_PATTERN)
    endpoint: str | None = Field(default=None, max_length=2000)
    ion_token: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None
    metadata: dict[str, Any] | None = None


class TerrainSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    name: str
    provider: str = "ellipsoid"
    endpoint: str | None = None
    is_default: bool = False
    # ``ion_token`` is intentionally NEVER returned. The frontend uses
    # a separate short-lived token endpoint when ion is enabled.
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Viewpoint ────────────────────────────────────────────────────────────


class ViewpointCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    camera_lat: Decimal = Field(default=Decimal("0"))
    camera_lon: Decimal = Field(default=Decimal("0"))
    camera_alt: Decimal = Field(default=Decimal("0"))
    heading: Decimal = Field(default=Decimal("0"), ge=-360, le=720)
    pitch: Decimal = Field(default=Decimal("0"), ge=-180, le=180)
    roll: Decimal = Field(default=Decimal("0"), ge=-180, le=180)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _v_lat = field_validator("camera_lat")(lambda cls, v: _check_lat(v))  # type: ignore[arg-type, misc]
    _v_lon = field_validator("camera_lon")(lambda cls, v: _check_lon(v))  # type: ignore[arg-type, misc]


class ViewpointUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    camera_lat: Decimal | None = None
    camera_lon: Decimal | None = None
    camera_alt: Decimal | None = None
    heading: Decimal | None = Field(default=None, ge=-360, le=720)
    pitch: Decimal | None = Field(default=None, ge=-180, le=180)
    roll: Decimal | None = Field(default=None, ge=-180, le=180)
    metadata: dict[str, Any] | None = None


class ViewpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    camera_lat: Decimal
    camera_lon: Decimal
    camera_alt: Decimal
    heading: Decimal
    pitch: Decimal
    roll: Decimal
    created_by: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── GeoOverlay ───────────────────────────────────────────────────────────


class GeoOverlayCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(default="", max_length=255)
    kind: str = Field(default="boundary", pattern=_OVERLAY_KIND_PATTERN)
    geojson: dict[str, Any] = Field(default_factory=dict)
    source_file: str | None = Field(default=None, max_length=500)
    style: dict[str, Any] = Field(default_factory=dict)
    is_visible: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeoOverlayUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    kind: str | None = Field(default=None, pattern=_OVERLAY_KIND_PATTERN)
    geojson: dict[str, Any] | None = None
    style: dict[str, Any] | None = None
    is_visible: bool | None = None
    metadata: dict[str, Any] | None = None


class GeoOverlayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    name: str = ""
    kind: str = "boundary"
    geojson: dict[str, Any] = Field(default_factory=dict)
    source_file: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    is_visible: bool = True
    source_event_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class GeoJSONImportRequest(BaseModel):
    """Import a GeoJSON FeatureCollection as a new GeoOverlay."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(default="", max_length=255)
    kind: str = Field(default="boundary", pattern=_OVERLAY_KIND_PATTERN)
    geojson: dict[str, Any]
    style: dict[str, Any] = Field(default_factory=dict)


class KMLImportRequest(BaseModel):
    """Import KML as a new GeoOverlay (we parse to GeoJSON on the way in)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(default="", max_length=255)
    kind: str = Field(default="boundary", pattern=_OVERLAY_KIND_PATTERN)
    kml: str = Field(..., min_length=10, max_length=10_000_000)
    style: dict[str, Any] = Field(default_factory=dict)


# ── TileGenerationJob ────────────────────────────────────────────────────


class TileJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    tileset_id: UUID | None = None
    source_kind: str
    source_id: UUID
    requested_by: UUID | None = None
    state: str = "queued"
    progress_pct: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    output_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── MapConfig one-shot bundle ────────────────────────────────────────────


class MapConfigResponse(BaseModel):
    """Single round-trip bundle for the Cesium viewer boot path."""

    model_config = ConfigDict(populate_by_name=True)

    project_id: UUID
    anchor: GeoAnchorResponse | None = None
    imagery_layers: list[ImageryLayerResponse] = Field(default_factory=list)
    terrain_source: TerrainSourceResponse | None = None
    tilesets: list[TilesetResponse] = Field(default_factory=list)
    overlays: list[GeoOverlayResponse] = Field(default_factory=list)
    viewpoints: list[ViewpointResponse] = Field(default_factory=list)
    active_jobs: list[TileJobResponse] = Field(default_factory=list)


# ── Cross-module geo pins (HSE / Punchlist / Daily Diary) ───────────────


class HSEPinResponse(BaseModel):
    """A single HSE incident pinned on the project map."""

    model_config = ConfigDict(from_attributes=True)

    incident_id: UUID
    incident_number: str
    title: str | None = None
    incident_type: str
    severity: str
    status: str
    lat: float
    lon: float


class PunchlistPinResponse(BaseModel):
    """A single punch list item pinned on the project map."""

    model_config = ConfigDict(from_attributes=True)

    item_id: UUID
    title: str
    priority: str
    status: str
    category: str | None = None
    lat: float
    lon: float


class DiaryPhotoPinResponse(BaseModel):
    """A single geo-tagged Daily Diary photo on the project map."""

    model_config = ConfigDict(from_attributes=True)

    photo_id: UUID
    diary_id: UUID | None = None
    taken_at: datetime
    thumbnail_url: str | None = None
    file_url: str
    is_360: bool = False
    is_drone: bool = False
    lat: float
    lon: float


__all__ = [
    "CanonicalToTilesetRequest",
    "DiaryPhotoPinResponse",
    "GeoAnchorCreate",
    "GeoAnchorResponse",
    "GeoAnchorUpdate",
    "GeoJSONImportRequest",
    "GeoOverlayCreate",
    "GeoOverlayResponse",
    "GeoOverlayUpdate",
    "HSEPinResponse",
    "ImageryLayerCreate",
    "ImageryLayerResponse",
    "ImageryLayerUpdate",
    "KMLImportRequest",
    "MapConfigResponse",
    "PunchlistPinResponse",
    "TerrainSourceCreate",
    "TerrainSourceResponse",
    "TerrainSourceUpdate",
    "TileGenerateRequest",
    "TileJobResponse",
    "TilesetCreate",
    "TilesetResponse",
    "TilesetUpdate",
    "ViewpointCreate",
    "ViewpointResponse",
    "ViewpointUpdate",
]
