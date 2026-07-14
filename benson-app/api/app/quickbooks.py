from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SyncDirection(StrEnum):
    TO_QUICKBOOKS = "to_quickbooks"
    FROM_QUICKBOOKS = "from_quickbooks"


class SyncEnvelope(BaseModel):
    entity_type: str
    entity_id: str
    direction: SyncDirection
    idempotency_key: str = Field(min_length=16)
    payload: dict[str, Any]


SYNC_OWNERSHIP = {
    "customer": "erp_approved_then_quickbooks",
    "invoice": "erp_approved_then_quickbooks",
    "payment": "quickbooks_then_erp",
    "expense": "quickbooks_then_erp",
    "estimate": "erp_only",
    "job_cost": "erp_operational_rollup",
}
