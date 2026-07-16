#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import create_engine, func, select, text

from app.domain import LeadIntake
from app.storage import audit_events, leads, metadata

EXPECTED_LEADS = 9
MIGRATION_NAMESPACE = UUID("f998428a-d8af-4b0a-b29f-0a751aa566e1")


def _stable_id(legacy_id: str) -> str:
    try:
        return str(UUID(legacy_id))
    except ValueError:
        return str(uuid5(MIGRATION_NAMESPACE, legacy_id))


def _load_source(source_url: str) -> list[dict[str, Any]]:
    engine = create_engine(source_url, pool_pre_ping=True)
    try:
        with engine.connect() as db:
            rows = (
                db.execute(
                    text(
                        """
                        SELECT lead.*, webhook.payload AS webhook_payload
                        FROM oe_crm_lead AS lead
                        JOIN oe_webhook_leads_log AS webhook
                          ON webhook.created_lead_id = lead.id
                        WHERE webhook.status = 'accepted' AND webhook.http_status = 201
                        ORDER BY lead.created_at, lead.id
                        """
                    )
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()
    return [dict(row) for row in rows]


def _canonical_values(row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = row["webhook_payload"]
    payload = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)
    canonical = LeadIntake.model_validate(payload).to_canonical()
    canonical.metadata = {
        "migration_source": "openconstructionerp",
        "legacy_lead_id": str(row["id"]),
        "legacy_payload": payload,
    }
    created_at = row["created_at"]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    updated_at = row["updated_at"] or created_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return {
        "id": _stable_id(str(row["id"])),
        "idempotency_key": f"legacy-openconstructionerp:{row['id']}",
        "status": str(row["status"]),
        "priority": "urgent" if canonical.urgency == "emergency" else "normal",
        "name": canonical.name,
        "phone": canonical.phone,
        "email": str(canonical.email) if canonical.email else None,
        "service_type": canonical.service_type,
        "city": canonical.city,
        "assigned_to": row["assigned_to"],
        "payload": canonical.model_dump_json(),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _fingerprint(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def _content_fingerprint(rows: list[dict[str, Any]]) -> str:
    fields = (
        "id",
        "idempotency_key",
        "status",
        "priority",
        "name",
        "phone",
        "email",
        "service_type",
        "city",
        "assigned_to",
        "payload",
        "created_at",
        "updated_at",
    )
    normalized = []
    for row in rows:
        item = {
            field: row[field].isoformat()
            if isinstance(row[field], datetime)
            else row[field]
            for field in fields
        }
        normalized.append(item)
    encoded = json.dumps(
        sorted(normalized, key=lambda item: item["id"]), sort_keys=True
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def migrate(source_url: str, target_url: str, *, apply: bool) -> dict[str, Any]:
    source_rows = _load_source(source_url)
    if len(source_rows) != EXPECTED_LEADS:
        raise RuntimeError(
            f"Migration refused: expected {EXPECTED_LEADS} accepted legacy leads, found {len(source_rows)}"
        )
    values = [_canonical_values(row) for row in source_rows]
    expected_ids = [item["id"] for item in values]
    expected_content_fingerprint = _content_fingerprint(values)
    target = create_engine(target_url, pool_pre_ping=True)
    try:
        metadata.create_all(target)
        with target.begin() as db:
            target_count = int(
                db.execute(select(func.count()).select_from(leads)).scalar_one()
            )
            existing_ids = set(
                db.execute(
                    select(leads.c.id).where(
                        leads.c.idempotency_key.like("legacy-openconstructionerp:%")
                    )
                ).scalars()
            )
            if target_count not in {0, EXPECTED_LEADS}:
                raise RuntimeError(
                    "Migration refused: target must be empty or contain only the reconciled nine leads"
                )
            if target_count == EXPECTED_LEADS:
                if existing_ids != set(expected_ids):
                    raise RuntimeError(
                        "Reconciliation failed: target legacy IDs do not match source"
                    )
            elif apply:
                now = datetime.now(UTC)
                for item in values:
                    db.execute(leads.insert().values(**item))
                    db.execute(
                        audit_events.insert().values(
                            id=str(uuid5(MIGRATION_NAMESPACE, f"audit:{item['id']}")),
                            event="lead.migrated",
                            actor="production-cutover",
                            subject_type="lead",
                            subject_id=item["id"],
                            payload=json.dumps(
                                {
                                    "source": "openconstructionerp",
                                    "legacy_id": item["id"],
                                },
                                sort_keys=True,
                            ),
                            occurred_at=now,
                        )
                    )
            final_count = (
                EXPECTED_LEADS if apply and target_count == 0 else target_count
            )
            target_rows = [
                dict(row)
                for row in db.execute(select(leads).where(leads.c.id.in_(expected_ids)))
                .mappings()
                .all()
            ]
            if final_count == EXPECTED_LEADS:
                actual_content_fingerprint = _content_fingerprint(target_rows)
                if actual_content_fingerprint != expected_content_fingerprint:
                    raise RuntimeError(
                        "Reconciliation failed: target lead content differs from source"
                    )
            else:
                actual_content_fingerprint = None
    finally:
        target.dispose()
    return {
        "mode": "apply" if apply else "dry-run",
        "source_count": len(values),
        "target_count_before": target_count,
        "target_count_after": final_count,
        "id_fingerprint": _fingerprint(expected_ids),
        "content_fingerprint": expected_content_fingerprint,
        "content_reconciled": actual_content_fingerprint
        == expected_content_fingerprint,
        "notifications_enqueued": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate the approved Benson legacy lead set"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write after all count guards pass"
    )
    args = parser.parse_args()
    source_url = os.environ.get("BENSON_LEGACY_DATABASE_URL", "")
    target_url = os.environ.get("BENSON_TARGET_DATABASE_URL", "")
    if not source_url or not target_url:
        raise SystemExit(
            "BENSON_LEGACY_DATABASE_URL and BENSON_TARGET_DATABASE_URL are required"
        )
    print(json.dumps(migrate(source_url, target_url, apply=args.apply), sort_keys=True))


if __name__ == "__main__":
    main()
