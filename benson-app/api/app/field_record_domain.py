from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

FieldReportStatus = Literal[
    "draft", "submitted", "correction_required", "corrected", "superseded"
]
PhotoStage = Literal["before", "during", "after"]


class FieldReportContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workforce_total: int = Field(default=0, ge=0, le=500)
    workforce_hours: str = Field(default="", max_length=2_000)
    weather: str = Field(default="", max_length=2_000)
    completed_work: str = Field(default="", max_length=20_000)
    materials: str = Field(default="", max_length=10_000)
    equipment: str = Field(default="", max_length=10_000)
    delays: str = Field(default="", max_length=10_000)
    issues: str = Field(default="", max_length=10_000)
    safety_observations: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("safety_observations")
    @classmethod
    def observations_are_bounded(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if any(len(item) > 2_000 for item in cleaned):
            raise ValueError("Safety observations cannot exceed 2000 characters")
        return cleaned


class FieldReportCreate(FieldReportContent):
    job_id: UUID
    service_date: date


class FieldReportUpdate(FieldReportContent):
    expected_version: int = Field(ge=1)


class FieldReportCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=5_000)


class FieldReportSummary(FieldReportContent):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    job_id: UUID
    job_number: str
    job_title: str
    service_date: date
    revision: int
    previous_revision_id: UUID | None
    status: FieldReportStatus
    version: int
    created_by: EmailStr
    submitted_by: EmailStr | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FieldPhotoSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    field_report_id: UUID
    stage: PhotoStage
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: EmailStr
    created_at: datetime
