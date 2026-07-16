from pathlib import Path


def test_customer_migration_is_additive_and_guarded() -> None:
    migration = (
        Path(__file__).resolve().parents[1] / "migrations" / "20260716_02_customers.sql"
    ).read_text()
    normalized = migration.lower()

    assert "create table if not exists customers" in normalized
    assert "source_lead_id varchar(36) unique" in normalized
    assert "check (status in ('active', 'archived'))" in normalized
    assert "created_by varchar(320) not null" in normalized
    assert "drop table" not in normalized
    assert "truncate" not in normalized
    assert "delete from" not in normalized
