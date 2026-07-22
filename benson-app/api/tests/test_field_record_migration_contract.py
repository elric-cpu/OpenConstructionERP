from pathlib import Path


def test_field_record_migration_is_sequential_and_complete() -> None:
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    migration = migrations / "20260716_06_field_records.sql"
    assert migration.is_file()
    sql = migration.read_text()
    for table in (
        "field_reports",
        "field_report_corrections",
        "field_report_photos",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "previous_revision_id" in sql
    assert "REFERENCES jobs(id)" in sql
    assert "correction_required" in sql
