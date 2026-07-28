from pathlib import Path


def test_change_order_migration_is_sequential_atomic_and_billing_safe() -> None:
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    migration = migrations / "20260716_07_change_orders.sql"
    assert migration.is_file()
    sql = migration.read_text()
    for table in (
        "change_orders",
        "change_order_lines",
        "change_order_evidence",
        "change_order_approvals",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "approved_change_order_cents" in sql
    assert "billing_eligible_cents" in sql
    assert "previous_revision_id" in sql
    assert "originating_field_report_id" in sql
    assert "status IN ('draft', 'submitted', 'approved', 'rejected', 'void')" in sql
