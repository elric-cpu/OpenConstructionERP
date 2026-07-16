from pathlib import Path


def test_job_migration_is_additive_and_preserves_estimate_source() -> None:
    migration = (
        Path(__file__).resolve().parents[1] / "migrations" / "20260716_04_jobs.sql"
    ).read_text()
    normalized = migration.lower()

    assert "create table if not exists jobs" in normalized
    assert (
        "estimate_id varchar(36) not null unique references estimates(id)" in normalized
    )
    assert "contract_value_cents bigint not null" in normalized
    assert "target_completion >= target_start" in normalized
    assert "drop table" not in normalized
    assert "truncate" not in normalized
