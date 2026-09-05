from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SyncDirection(StrEnum):
    TO_PROVIDER = "to_provider"
    FROM_PROVIDER = "from_provider"


class SyncEnvelope(BaseModel):
    entity_type: str
    entity_id: str
    direction: SyncDirection
    idempotency_key: str = Field(min_length=16)
    payload: dict[str, Any]


SYNC_OWNERSHIP = {
    "customer": "erp_approved_then_provider",
    "invoice": "erp_approved_then_provider",
    "payment": "provider_then_erp",
    "expense": "provider_then_erp",
    "estimate": "erp_only",
    "job_cost": "erp_operational_rollup",
}
