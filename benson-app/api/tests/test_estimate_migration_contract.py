from pathlib import Path


def test_estimate_migration_uses_integer_money_and_additive_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[1] / "migrations" / "20260716_03_estimates.sql"
    ).read_text()
    normalized = migration.lower()

    assert "create table if not exists estimates" in normalized
    assert "create table if not exists estimate_lines" in normalized
    assert "total_cents bigint not null" in normalized
    assert "foreign key (customer_id) references customers(id)" in normalized
    assert "drop table" not in normalized
    assert "truncate" not in normalized
