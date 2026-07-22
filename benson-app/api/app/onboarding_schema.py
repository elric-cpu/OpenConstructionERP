from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from .storage_schema import metadata


onboarding_employee_versions = Table(
    "onboarding_employee_versions",
    metadata,
    Column(
        "employee_id",
        String(36),
        ForeignKey("employees.id"),
        primary_key=True,
    ),
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version > 0", name="ck_onboarding_employee_version"),
)

onboarding_task_versions = Table(
    "onboarding_task_versions",
    metadata,
    Column(
        "task_id",
        String(36),
        ForeignKey("employee_tasks.id"),
        primary_key=True,
    ),
    Column(
        "employee_id",
        String(36),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    ),
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version > 0", name="ck_onboarding_task_version"),
)

onboarding_task_reviews = Table(
    "onboarding_task_reviews",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "employee_id",
        String(36),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    ),
    Column(
        "task_id",
        String(36),
        ForeignKey("employee_tasks.id"),
        nullable=False,
        index=True,
    ),
    Column("review_type", String(40), nullable=False),
    Column("from_status", String(40), nullable=False),
    Column("to_status", String(40), nullable=False),
    Column("decision", String(40), nullable=False),
    Column("comment", Text, nullable=False),
    Column("reviewer_email", String(320), nullable=False),
    Column("reviewer_name", String(200)),
    Column("reviewer_qualification", String(300)),
    Column("rule_version", String(120), nullable=False),
    Column("task_version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "review_type IN ('task_review', 'applicability')",
        name="ck_onboarding_review_type",
    ),
    CheckConstraint("task_version > 1", name="ck_onboarding_review_task_version"),
)

onboarding_task_submissions = Table(
    "onboarding_task_submissions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "employee_id",
        String(36),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    ),
    Column(
        "task_id",
        String(36),
        ForeignKey("employee_tasks.id"),
        nullable=False,
        index=True,
    ),
    Column("evidence_type", String(40), nullable=False),
    Column("evidence_id", String(36), nullable=False),
    Column("submission_version", Integer, nullable=False),
    Column("submitted_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "task_id",
        "submission_version",
        name="uq_onboarding_submission_version",
    ),
    CheckConstraint(
        "evidence_type IN ('document', 'signature', 'protected_response')",
        name="ck_onboarding_submission_evidence_type",
    ),
)

onboarding_rule_versions = Table(
    "onboarding_rule_versions",
    metadata,
    Column("id", String(120), primary_key=True),
    Column("status", String(40), nullable=False),
    Column("requirements_digest", String(64), nullable=False),
    Column("requirements_snapshot", Text, nullable=False),
    Column("approved_by", String(320)),
    Column("approved_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending_legal_review', 'approved', 'superseded')",
        name="ck_onboarding_rule_version_status",
    ),
)

identity_provisioning_commands = Table(
    "identity_provisioning_commands",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "employee_id",
        String(36),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    ),
    Column("kind", String(20), nullable=False),
    Column("status", String(40), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("idempotency_key", String(120), nullable=False, unique=True),
    Column("target_email", String(320), nullable=False),
    Column("target_org_unit", String(300), nullable=False),
    Column("external_user_id", String(200)),
    Column("requested_by", String(320), nullable=False),
    Column("approved_by", String(320)),
    Column("executed_by", String(320)),
    Column("failure_code", String(120)),
    Column("bootstrap_credential", Text),
    Column("available_at", DateTime(timezone=True), nullable=False, index=True),
    Column("locked_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("kind IN ('create', 'suspend')", name="ck_identity_command_kind"),
    CheckConstraint(
        "status IN ('pending_approval', 'manual_setup_required', 'approved', 'executing', 'verified', "
        "'admin_confirmation_required', 'admin_confirmed', 'failed', "
        "'manual_review_required', 'suspended')",
        name="ck_identity_command_status",
    ),
    CheckConstraint("version > 0", name="ck_identity_command_version"),
)

identity_provisioning_attempts = Table(
    "identity_provisioning_attempts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "command_id",
        String(36),
        ForeignKey("identity_provisioning_commands.id"),
        nullable=False,
        index=True,
    ),
    Column("attempt", Integer, nullable=False),
    Column("result", String(40), nullable=False),
    Column("provider_code", String(120)),
    Column("details", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("command_id", "attempt", name="uq_identity_provisioning_attempt"),
    CheckConstraint("attempt > 0", name="ck_identity_provisioning_attempt"),
)

onboarding_admin_confirmations = Table(
    "onboarding_admin_confirmations",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "command_id",
        String(36),
        ForeignKey("identity_provisioning_commands.id"),
        nullable=False,
        unique=True,
    ),
    Column("confirmed_by", String(320), nullable=False),
    Column("reason", Text, nullable=False),
    Column("evidence_reference", String(500), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
)

onboarding_retention_holds = Table(
    "onboarding_retention_holds",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "employee_id",
        String(36),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    ),
    Column("reason", Text, nullable=False),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("released_by", String(320)),
    Column("released_at", DateTime(timezone=True)),
    CheckConstraint(
        "(released_by IS NULL AND released_at IS NULL) OR "
        "(released_by IS NOT NULL AND released_at IS NOT NULL)",
        name="ck_onboarding_retention_hold_release_pair",
    ),
)

onboarding_offboarding_events = Table(
    "onboarding_offboarding_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "employee_id",
        String(36),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    ),
    Column("reason", Text, nullable=False),
    Column("previous_status", String(40), nullable=False),
    Column("session_revoked_at", DateTime(timezone=True), nullable=False),
    Column(
        "directory_command_id",
        String(36),
        ForeignKey("identity_provisioning_commands.id"),
    ),
    Column("actor", String(320), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)
