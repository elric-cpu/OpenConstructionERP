from pathlib import Path


def test_schedule_migration_is_additive_constrained_and_race_safe() -> None:
    migration = (
        Path(__file__).resolve().parents[1] / "migrations" / "20260716_05_schedule.sql"
    ).read_text()
    normalized = migration.lower()

    assert "create table if not exists schedule_entries" in normalized
    assert "job_id varchar(36) not null references jobs(id)" in normalized
    assert "starts_at timestamptz not null" in normalized
    assert "ends_at timestamptz not null" in normalized
    assert "check (ends_at > starts_at)" in normalized
    assert "exclude using gist" in normalized
    assert "tstzrange(starts_at, ends_at, '[)') with &&" in normalized
    assert "status in ('scheduled', 'in_progress')" in normalized
    assert "create table if not exists schedule_status_history" in normalized
    assert "drop table" not in normalized
    assert "truncate" not in normalized
