import json
import re
from pathlib import Path
from typing import Any, cast

API_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = API_ROOT / "migrations" / "20260716_01_logistics_foundation.sql"
CONTRACTS = API_ROOT / "contracts"


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def contract(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((CONTRACTS / name).read_text(encoding="utf-8")),
    )


def test_migration_is_additive_and_transactional() -> None:
    sql = migration_sql()
    assert sql.startswith("-- Additive")
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
    assert "ALTER TABLE" not in sql.upper()


def test_migration_defines_logistics_tables_and_indexes() -> None:
    sql = migration_sql()
    tables = {
        "logistics_route_areas",
        "logistics_contacts",
        "logistics_inquiry_holding_queue",
        "logistics_work_orders",
        "logistics_work_order_photo_assets",
        "logistics_inbound_message_media",
        "logistics_provider_outbox",
        "logistics_marketing_attribution",
    }
    for table in tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
        assert re.search(rf"CREATE INDEX IF NOT EXISTS .*\n\s+ON {table}", sql)


def test_migration_enforces_identifiers_and_digests() -> None:
    sql = migration_sql()
    assert "uei ~ '^[A-Z0-9]{12}$'" in sql
    assert "cage_code ~ '^[A-Z0-9]{5}$'" in sql
    assert sql.count("~ '^[a-f0-9]{64}$'") >= 5
    assert sql.count("idempotency_key") >= 3


def test_migration_preserves_raw_normalized_and_retention_states() -> None:
    sql = migration_sql()
    assert sql.count("raw_payload jsonb") >= 3
    assert sql.count("normalized_payload jsonb") >= 2
    for field in ("created_at", "created_by", "updated_at", "updated_by"):
        assert sql.count(field) >= 8
    assert sql.count("retention_hold_until") == 8
    assert sql.count("purge_after") >= 18
    assert (
        "queue_state IN ('held', 'ready', 'accepted', 'rejected', 'duplicate', 'archived')"
        in sql
    )


def test_payload_contracts_are_strict_json_schema() -> None:
    names = {
        "public-inquiry.raw.schema.json",
        "public-inquiry.normalized.schema.json",
        "marketing-attribution.schema.json",
        "provider-outbox.schema.json",
    }
    for name in names:
        schema = contract(name)
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False


def test_normalized_identifiers_match_database_contract() -> None:
    contact_properties = contract("public-inquiry.normalized.schema.json")[
        "properties"
    ]["contact"]["properties"]
    assert contact_properties["uei"]["pattern"] == "^[A-Z0-9]{12}$"
    assert contact_properties["cage_code"]["pattern"] == "^[A-Z0-9]{5}$"


def test_inbound_media_is_queued_without_storing_plain_sender_phone() -> None:
    sql = migration_sql()
    assert "CREATE TABLE IF NOT EXISTS logistics_inbound_message_media" in sql
    assert "sender_phone_hash char(64) NOT NULL" in sql
    assert "sender_phone_encrypted_ref varchar(1000)" in sql
    assert "sender_phone varchar" not in sql
    assert "UNIQUE (provider, provider_media_key)" in sql
    assert "status varchar(24) NOT NULL DEFAULT 'queued'" in sql
