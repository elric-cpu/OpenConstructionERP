import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Connection

from .finance_schema import accounting_outbox


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def enqueue_accounting_export(
    db: Connection,
    *,
    entity_type: str,
    entity_id: str,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> tuple[str, bool]:
    encoded = canonical_json(payload)
    existing = (
        db.execute(
            select(accounting_outbox).where(
                accounting_outbox.c.idempotency_key == idempotency_key
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if (
            existing["entity_type"] != entity_type
            or existing["entity_id"] != entity_id
            or existing["operation"] != operation
            or existing["payload"] != encoded
        ):
            raise ValueError("Accounting export idempotency key payload mismatch")
        return str(existing["id"]), False
    outbox_id = str(uuid4())
    now = datetime.now(UTC)
    db.execute(
        accounting_outbox.insert().values(
            id=outbox_id,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            idempotency_key=idempotency_key,
            payload=encoded,
            status="pending",
            attempts=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    return outbox_id, True
