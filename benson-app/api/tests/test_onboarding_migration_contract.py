from pathlib import Path


def test_onboarding_completion_migration_is_sequential_and_protected() -> None:
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    migration = migrations / "20260716_08_onboarding_completion.sql"
    assert migration.is_file()
    sql = migration.read_text()
    for table in (
        "onboarding_employee_versions",
        "onboarding_task_versions",
        "onboarding_task_reviews",
        "onboarding_task_submissions",
        "onboarding_rule_versions",
        "identity_provisioning_commands",
        "identity_provisioning_attempts",
        "onboarding_admin_confirmations",
        "onboarding_retention_holds",
        "onboarding_offboarding_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "ON CONFLICT (employee_id) DO NOTHING" in sql
    assert "ON CONFLICT (task_id) DO NOTHING" in sql
    assert "fk_employee_documents_task" in sql
    assert "fk_employee_signatures_task" in sql
    assert "fk_employee_outbox_employee" in sql
    assert "restore the\n-- pre-migration database snapshot" in sql.lower()
