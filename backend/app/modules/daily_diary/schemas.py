"""Daily Site Diary Pydantic schemas — request/response models (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Status enums (encoded as patterns) ───────────────────────────────────

_DIARY_STATUS_RE = r"^(open|closed|signed|archived)$"
_ENTRY_TYPE_RE = (
    r"^(visitor|event|delivery|completion|incident_summary|"
    r"inspection_summary|photo_note|general)$"
)
_WEATHER_SOURCE_RE = r"^(open_meteo|manual|sensor)$"
_CAPTURE_TYPE_RE = r"^(laser_scan|photogrammetry|mobile_scan)$"
_SIGNER_ROLE_RE = r"^(owner|supervisor|inspector|client)$"
# Photo MIME is client-declared (the file itself lives in object storage),
# so it MUST be constrained to the platform image allow-list — otherwise a
# caller could persist e.g. ``text/html`` and the UI would trust it. Mirrors
# documents.ALLOWED_IMAGE_TYPES (+ avif, which site cameras now emit).
_PHOTO_MIME_RE = (
    r"^image/(jpeg|png|gif|webp|heic|heif|avif|tiff)$"
)


# ── DailyDiary ───────────────────────────────────────────────────────────


class DailyDiaryCreate(BaseModel):
    """Create a new daily diary."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    diary_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    site_supervisor_id: UUID | None = None
    weather_summary: dict[str, Any] = Field(default_factory=dict)
    labour_count: int = Field(default=0, ge=0)
    equipment_count: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=20000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DailyDiaryUpdate(BaseModel):
    """Partial update for a daily diary."""

    model_config = ConfigDict(str_strip_whitespace=True)

    site_supervisor_id: UUID | None = None
    weather_summary: dict[str, Any] | None = None
    labour_count: int | None = Field(default=None, ge=0)
    equipment_count: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=20000)
    metadata: dict[str, Any] | None = None


class DailyDiaryResponse(BaseModel):
    """Daily diary returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    diary_date: str
    site_supervisor_id: UUID | None = None
    weather_summary: dict[str, Any] = Field(default_factory=dict)
    labour_count: int = 0
    equipment_count: int = 0
    status: str = "open"
    notes: str | None = None
    closed_at: datetime | None = None
    closed_by: UUID | None = None
    owner_signature_ref: str | None = None
    supervisor_signature_ref: str | None = None
    pdf_export_ref: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── WeatherRecord ────────────────────────────────────────────────────────


class WeatherRecordCreate(BaseModel):
    """Create a new weather record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    captured_at: datetime
    source: str = Field(default="manual", pattern=_WEATHER_SOURCE_RE)
    temperature_c: Decimal | None = None
    humidity_pct: Decimal | None = Field(default=None, ge=0, le=100)
    wind_speed_kmh: Decimal | None = Field(default=None, ge=0)
    precipitation_mm: Decimal | None = Field(default=None, ge=0)
    conditions_code: str | None = Field(default=None, max_length=32)
    conditions_text: str | None = Field(default=None, max_length=255)
    sunrise: str | None = Field(default=None, max_length=40)
    sunset: str | None = Field(default=None, max_length=40)
    location_lat: float | None = Field(default=None, ge=-90, le=90)
    location_lng: float | None = Field(default=None, ge=-180, le=180)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WeatherRecordUpdate(BaseModel):
    """Partial update for a weather record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    captured_at: datetime | None = None
    source: str | None = Field(default=None, pattern=_WEATHER_SOURCE_RE)
    temperature_c: Decimal | None = None
    humidity_pct: Decimal | None = Field(default=None, ge=0, le=100)
    wind_speed_kmh: Decimal | None = Field(default=None, ge=0)
    precipitation_mm: Decimal | None = Field(default=None, ge=0)
    conditions_code: str | None = Field(default=None, max_length=32)
    conditions_text: str | None = Field(default=None, max_length=255)
    sunrise: str | None = Field(default=None, max_length=40)
    sunset: str | None = Field(default=None, max_length=40)
    location_lat: float | None = Field(default=None, ge=-90, le=90)
    location_lng: float | None = Field(default=None, ge=-180, le=180)
    metadata: dict[str, Any] | None = None


class WeatherRecordResponse(BaseModel):
    """Weather record returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    captured_at: datetime
    source: str
    temperature_c: Decimal | None = None
    humidity_pct: Decimal | None = None
    wind_speed_kmh: Decimal | None = None
    precipitation_mm: Decimal | None = None
    conditions_code: str | None = None
    conditions_text: str | None = None
    sunrise: str | None = None
    sunset: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── DiaryEntry ───────────────────────────────────────────────────────────


class DiaryEntryCreate(BaseModel):
    """Create a new diary entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    diary_id: UUID
    entry_type: str = Field(..., pattern=_ENTRY_TYPE_RE)
    entry_time: datetime
    title: str = Field(default="", max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    source_module: str | None = Field(default=None, max_length=64)
    source_ref: UUID | None = None
    author_id: UUID | None = None
    photo_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiaryEntryBulkCreate(BaseModel):
    """Bulk-create payload for diary entries (excludes diary_id which comes from URL)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    entry_type: str = Field(..., pattern=_ENTRY_TYPE_RE)
    entry_time: datetime
    title: str = Field(default="", max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    source_module: str | None = Field(default=None, max_length=64)
    source_ref: UUID | None = None
    author_id: UUID | None = None
    photo_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiaryEntryUpdate(BaseModel):
    """Partial update for a diary entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    entry_type: str | None = Field(default=None, pattern=_ENTRY_TYPE_RE)
    entry_time: datetime | None = None
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    source_module: str | None = Field(default=None, max_length=64)
    source_ref: UUID | None = None
    author_id: UUID | None = None
    photo_ids: list[UUID] | None = None
    metadata: dict[str, Any] | None = None


class DiaryEntryResponse(BaseModel):
    """Diary entry returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    diary_id: UUID
    entry_type: str
    entry_time: datetime
    title: str = ""
    description: str | None = None
    source_module: str | None = None
    source_ref: UUID | None = None
    author_id: UUID | None = None
    photo_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── DiaryPhoto ───────────────────────────────────────────────────────────


class DiaryPhotoCreate(BaseModel):
    """Create a new diary photo."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    diary_id: UUID | None = None
    taken_at: datetime
    photographer_id: UUID | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    location_label: str | None = Field(default=None, max_length=255)
    file_url: str = Field(..., min_length=1, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    mime_type: str = Field(
        default="image/jpeg", max_length=80, pattern=_PHOTO_MIME_RE
    )
    file_size_bytes: int = Field(default=0, ge=0)
    description: str | None = Field(default=None, max_length=20000)
    tags: list[str] = Field(default_factory=list)
    is_360: bool = False
    is_drone: bool = False


class DiaryPhotoUpdate(BaseModel):
    """Partial update for a diary photo."""

    model_config = ConfigDict(str_strip_whitespace=True)

    diary_id: UUID | None = None
    photographer_id: UUID | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    location_label: str | None = Field(default=None, max_length=255)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = None
    is_360: bool | None = None
    is_drone: bool | None = None
    is_archived: bool | None = None


class DiaryPhotoResponse(BaseModel):
    """Diary photo returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    diary_id: UUID | None = None
    project_id: UUID
    taken_at: datetime
    photographer_id: UUID | None = None
    lat: float | None = None
    lng: float | None = None
    location_label: str | None = None
    file_url: str
    thumbnail_url: str | None = None
    mime_type: str
    file_size_bytes: int = 0
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_360: bool = False
    is_drone: bool = False
    is_archived: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── DiaryVideo ───────────────────────────────────────────────────────────


class DiaryVideoCreate(BaseModel):
    """Create a new diary video."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    diary_id: UUID | None = None
    recorded_at: datetime
    file_url: str = Field(..., min_length=1, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    duration_seconds: int = Field(default=0, ge=0)
    file_size_bytes: int = Field(default=0, ge=0)
    description: str | None = Field(default=None, max_length=20000)
    tags: list[str] = Field(default_factory=list)


class DiaryVideoUpdate(BaseModel):
    """Partial update for a diary video."""

    model_config = ConfigDict(str_strip_whitespace=True)

    diary_id: UUID | None = None
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    duration_seconds: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = None


class DiaryVideoResponse(BaseModel):
    """Diary video returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    diary_id: UUID | None = None
    project_id: UUID
    recorded_at: datetime
    file_url: str
    thumbnail_url: str | None = None
    duration_seconds: int = 0
    file_size_bytes: int = 0
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── DroneSurvey ──────────────────────────────────────────────────────────


class DroneSurveyCreate(BaseModel):
    """Create a new drone survey."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    flown_at: datetime
    pilot_name: str | None = Field(default=None, max_length=255)
    drone_model: str | None = Field(default=None, max_length=255)
    area_m2: Decimal | None = Field(default=None, ge=0)
    ortho_file_url: str | None = Field(default=None, max_length=2000)
    dsm_file_url: str | None = Field(default=None, max_length=2000)
    point_cloud_url: str | None = Field(default=None, max_length=2000)
    elevation_min_m: Decimal | None = None
    elevation_max_m: Decimal | None = None
    notes: str | None = Field(default=None, max_length=20000)


class DroneSurveyUpdate(BaseModel):
    """Partial update for a drone survey."""

    model_config = ConfigDict(str_strip_whitespace=True)

    flown_at: datetime | None = None
    pilot_name: str | None = Field(default=None, max_length=255)
    drone_model: str | None = Field(default=None, max_length=255)
    area_m2: Decimal | None = Field(default=None, ge=0)
    ortho_file_url: str | None = Field(default=None, max_length=2000)
    dsm_file_url: str | None = Field(default=None, max_length=2000)
    point_cloud_url: str | None = Field(default=None, max_length=2000)
    elevation_min_m: Decimal | None = None
    elevation_max_m: Decimal | None = None
    notes: str | None = Field(default=None, max_length=20000)


class DroneSurveyResponse(BaseModel):
    """Drone survey returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    flown_at: datetime
    pilot_name: str | None = None
    drone_model: str | None = None
    area_m2: Decimal | None = None
    ortho_file_url: str | None = None
    dsm_file_url: str | None = None
    point_cloud_url: str | None = None
    elevation_min_m: Decimal | None = None
    elevation_max_m: Decimal | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── RealityCaptureDataset ─────────────────────────────────────────────────


class RealityCaptureCreate(BaseModel):
    """Create a new reality-capture dataset."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    captured_at: datetime
    capture_type: str = Field(default="laser_scan", pattern=_CAPTURE_TYPE_RE)
    file_url: str = Field(..., min_length=1, max_length=2000)
    point_count_estimate: int | None = Field(default=None, ge=0)
    bbox_min: dict[str, float] | None = None
    bbox_max: dict[str, float] | None = None
    accuracy_mm: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=20000)
    linked_bim_model_ref: UUID | None = None


class RealityCaptureUpdate(BaseModel):
    """Partial update for a reality-capture dataset."""

    model_config = ConfigDict(str_strip_whitespace=True)

    captured_at: datetime | None = None
    capture_type: str | None = Field(default=None, pattern=_CAPTURE_TYPE_RE)
    point_count_estimate: int | None = Field(default=None, ge=0)
    bbox_min: dict[str, float] | None = None
    bbox_max: dict[str, float] | None = None
    accuracy_mm: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=20000)
    linked_bim_model_ref: UUID | None = None


class RealityCaptureResponse(BaseModel):
    """Reality-capture dataset returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    captured_at: datetime
    capture_type: str
    file_url: str
    point_count_estimate: int | None = None
    bbox_min: dict[str, float] | None = None
    bbox_max: dict[str, float] | None = None
    accuracy_mm: Decimal | None = None
    notes: str | None = None
    linked_bim_model_ref: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── DiaryArchiveSignature ─────────────────────────────────────────────────


class DiaryArchiveSignatureResponse(BaseModel):
    """A diary archive signature record (read-only over the API)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    diary_id: UUID
    content_sha256: str
    signed_at: datetime
    signed_by: UUID | None = None
    signature_payload: dict[str, Any] = Field(default_factory=dict)
    revision: int = 1
    created_at: datetime
    updated_at: datetime


# ── Aggregate / dashboard responses ───────────────────────────────────────


class DiaryDashboardResponse(BaseModel):
    """Aggregated daily-diary dashboard metrics."""

    total_diaries: int = 0
    open_count: int = 0
    closed_count: int = 0
    signed_count: int = 0
    archived_count: int = 0
    photos_total: int = 0
    drone_surveys_total: int = 0
    reality_captures_total: int = 0
    diaries_by_date: dict[str, int] = Field(default_factory=dict)


class PhotoTimelineBucket(BaseModel):
    """Photo-timeline bucket grouping photos by calendar day."""

    date: str = Field(description="ISO date YYYY-MM-DD")
    photo_count: int
    photo_ids: list[UUID] = Field(default_factory=list)


class PhotoTimelineResponse(BaseModel):
    """Photo-timeline response — one bucket per day."""

    project_id: UUID
    buckets: list[PhotoTimelineBucket] = Field(default_factory=list)


class PhotoPair(BaseModel):
    """A before/after photo pair matched by location proximity."""

    photo_a_id: UUID
    photo_b_id: UUID
    distance_m: float
    date_a: datetime
    date_b: datetime


class BeforeAfterResponse(BaseModel):
    """Response payload for before/after photo pairing."""

    project_id: UUID
    pairs: list[PhotoPair] = Field(default_factory=list)


class DiaryCompletenessResponse(BaseModel):
    """Diary completeness score 0-100%."""

    diary_id: UUID
    completeness: Decimal = Field(description="0.0 to 1.0")
    missing: list[str] = Field(default_factory=list)


class DiaryImmutablePayloadHashResponse(BaseModel):
    """SHA-256 hash of the immutable payload for a diary."""

    diary_id: UUID
    content_sha256: str
    payload_preview: dict[str, Any] = Field(default_factory=dict)


class DiaryPdfStubResponse(BaseModel):
    """Placeholder response for the PDF-renderer hook."""

    diary_id: UUID
    pdf_export_ref: UUID
    status: str = "stub"


# ── Sign / close / archive ────────────────────────────────────────────────


class DiarySignRequest(BaseModel):
    """Sign payload for a diary."""

    model_config = ConfigDict(str_strip_whitespace=True)

    signer_role: str = Field(..., pattern=_SIGNER_ROLE_RE)
    signer_name: str | None = Field(default=None, max_length=255)
    signature_data: str | None = Field(default=None, max_length=200000)
    algorithm: str = Field(default="sha256", max_length=32)


# ── Weather fetch + productivity ──────────────────────────────────────────


class WeatherFetchRequest(BaseModel):
    """Request body for the Open-Meteo weather-fetch endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    target_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    persist: bool = Field(
        default=True,
        description="If True, persist the result as a WeatherRecord row.",
    )


class WeatherFetchResponse(BaseModel):
    """Result of a weather-fetch operation."""

    project_id: UUID
    target_date: str
    fetched: bool
    record_id: UUID | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class ProductivityFactorRequest(BaseModel):
    """Compute productivity factor for a trade given weather inputs."""

    model_config = ConfigDict(str_strip_whitespace=True)

    trade: str = Field(..., min_length=1, max_length=64)
    rain_hours: int = Field(default=0, ge=0, le=24)
    precipitation_mm: float | None = Field(default=None, ge=0)
    temperature_c: float | None = None
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    working_hours: int = Field(default=8, ge=1, le=24)


class ProductivityFactorResponse(BaseModel):
    """Productivity factor result."""

    trade: str
    factor: float = Field(description="Remaining productivity, 0.0 to 1.0")
    stopped: bool
    reason: str
    lost_hours: float


# ── Workforce / cross-module signals ──────────────────────────────────────


class WorkforceSummary(BaseModel):
    """Aggregated daily-diary workforce block."""

    diary_id: UUID
    project_id: UUID
    diary_date: str
    labour_count: int = 0
    equipment_count: int = 0
    by_company: dict[str, int] = Field(default_factory=dict)


# ── SCL Protocol PDF bundle ───────────────────────────────────────────────


class SCLBundleRequest(BaseModel):
    """Request a SCL Protocol contemporary-record bundle for a date range."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    date_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class SCLBundleManifest(BaseModel):
    """Manifest of files comprising the SCL bundle."""

    project_id: UUID
    date_from: str
    date_to: str
    diary_count: int
    weather_record_count: int
    photo_count: int
    drone_survey_count: int
    bundle_sha256: str
    contents: list[dict[str, Any]] = Field(default_factory=list)


# ── EXIF GPS extraction ───────────────────────────────────────────────────


class ExifGPSRequest(BaseModel):
    """Base64-encoded image bytes for EXIF GPS extraction."""

    model_config = ConfigDict(str_strip_whitespace=True)

    image_base64: str = Field(..., min_length=1, max_length=20_000_000)


class ExifGPSResponse(BaseModel):
    """EXIF GPS extraction result."""

    found: bool
    lat: float | None = None
    lng: float | None = None
    altitude_m: float | None = None
    timestamp: str | None = None
