from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    CheckConstraint,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

LEAD_TRANSITIONS = {
    "new": {"contacted", "closed"},
    "contacted": {"qualified", "closed"},
    "qualified": {"scheduled", "closed"},
    "scheduled": {"closed"},
    "closed": set(),
}


class InvalidLeadTransition(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


class InvalidEmployeeInvite(ValueError):
    pass


class InvalidEmployeeTaskTransition(ValueError):
    pass


leads = Table(
    "leads",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("idempotency_key", String(200), nullable=False, unique=True),
    Column("status", String(40), nullable=False),
    Column("priority", String(40), nullable=False),
    Column("name", String(200), nullable=False),
    Column("phone", String(40), nullable=False),
    Column("email", String(320)),
    Column("service_type", String(120), nullable=False),
    Column("city", String(120), nullable=False),
    Column("assigned_to", String(320)),
    Column("source", String(200), nullable=False, default="Website"),
    Column("is_spam", Integer, nullable=False, default=0),
    Column("spam_reason", String(500)),
    Column("deleted_at", DateTime(timezone=True)),
    Column("payload", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

upload_sessions = Table(
    "upload_sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("uploaded_files", Integer, nullable=False, default=0),
    Column("uploaded_bytes", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

attachments = Table(
    "attachments",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("original_name", String(500), nullable=False),
    Column("storage_key", String(1_000), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

lead_notes = Table(
    "lead_notes",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("author", String(320), nullable=False),
    Column("body", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("event", String(120), nullable=False, index=True),
    Column("actor", String(320), nullable=False),
    Column("subject_type", String(80), nullable=False),
    Column("subject_id", String(80), nullable=False, index=True),
    Column("payload", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

ai_runs = Table(
    "ai_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("skill_id", String(120), nullable=False),
    Column("actor", String(320), nullable=False),
    Column("role", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("model", String(200), nullable=False),
    Column("context", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ai_proposals = Table(
    "ai_proposals",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("run_id", String(36), nullable=False, index=True),
    Column("status", String(40), nullable=False),
    Column("risk", String(40), nullable=False),
    Column("action", Text, nullable=False),
    Column("decided_by", String(320)),
    Column("decision_comment", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
)

notification_outbox = Table(
    "notification_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("lead_id", String(36), nullable=False, index=True),
    Column("channel", String(20), nullable=False),
    Column("destination", String(320), nullable=False),
    Column("payload", Text, nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("attempts", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False, index=True),
    Column("locked_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("provider_message_id", String(200)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True)),
)

operations_settings = Table(
    "operations_settings",
    metadata,
    Column("key", String(120), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_by", String(320), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

employees = Table(
    "employees",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("email", String(320), nullable=False, unique=True),
    Column("invite_delivery_email", String(320)),
    Column("start_date", Date, nullable=False),
    Column("work_location", String(200), nullable=False),
    Column("classification", String(40), nullable=False),
    Column("role", String(40), nullable=False),
    Column("federal_contract_applicability", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("workspace_account_status", String(40), nullable=False),
    Column("phone", String(20), nullable=False, default=""),
    Column("created_by", String(320), nullable=False),
    Column("google_subject", String(200), unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

customers = Table(
    "customers",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("company", String(200), nullable=False, default=""),
    Column("phone", String(40), nullable=False),
    Column("email", String(320)),
    Column("billing_address", String(500), nullable=False, default=""),
    Column("service_address", String(500), nullable=False, default=""),
    Column("city", String(120), nullable=False, default=""),
    Column("state", String(2), nullable=False, default="OR"),
    Column("zip_code", String(5), nullable=False, default=""),
    Column("notes", Text, nullable=False, default=""),
    Column("status", String(40), nullable=False, default="active"),
    Column("source_lead_id", String(36), unique=True),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

estimates = Table(
    "estimates",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("number", String(40), nullable=False, unique=True),
    Column("customer_id", String(36), nullable=False, index=True),
    Column("title", String(300), nullable=False),
    Column("scope_notes", Text, nullable=False, default=""),
    Column("valid_until", Date, nullable=False),
    Column("status", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("subtotal_cents", BigInteger, nullable=False),
    Column("total_cents", BigInteger, nullable=False),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

estimate_lines = Table(
    "estimate_lines",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("estimate_id", String(36), nullable=False, index=True),
    Column("position", Integer, nullable=False),
    Column("description", String(1_000), nullable=False),
    Column("quantity", String(40), nullable=False),
    Column("unit", String(40), nullable=False),
    Column("unit_price_cents", Integer, nullable=False),
    Column("line_total_cents", BigInteger, nullable=False),
    UniqueConstraint("estimate_id", "position", name="uq_estimate_line_position"),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("number", String(40), nullable=False, unique=True),
    Column(
        "estimate_id",
        String(36),
        ForeignKey("estimates.id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "customer_id",
        String(36),
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    ),
    Column("title", String(300), nullable=False),
    Column("scope_snapshot", Text, nullable=False),
    Column("contract_value_cents", BigInteger, nullable=False),
    Column("approved_change_order_cents", BigInteger, nullable=False, default=0),
    Column("billing_eligible_cents", BigInteger, nullable=False, default=0),
    Column("status", String(40), nullable=False),
    Column("target_start", Date),
    Column("target_completion", Date),
    Column("assigned_to", String(320)),
    Column("site_address", String(500), nullable=False, default=""),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("contract_value_cents >= 0", name="ck_jobs_contract_value"),
    CheckConstraint(
        "approved_change_order_cents >= 0", name="ck_jobs_approved_change_orders"
    ),
    CheckConstraint("billing_eligible_cents >= 0", name="ck_jobs_billing_eligible"),
    CheckConstraint(
        "status IN ('planned', 'active', 'on_hold', 'completed', 'cancelled')",
        name="ck_jobs_status",
    ),
    CheckConstraint(
        "target_start IS NULL OR target_completion IS NULL "
        "OR target_completion >= target_start",
        name="ck_jobs_dates",
    ),
)

schedule_entries = Table(
    "schedule_entries",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("job_id", String(36), ForeignKey("jobs.id"), nullable=False, index=True),
    Column("event_type", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("starts_at", DateTime(timezone=True), nullable=False, index=True),
    Column("ends_at", DateTime(timezone=True), nullable=False, index=True),
    Column("timezone", String(64), nullable=False),
    Column("assigned_to", String(320), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "event_type IN ('site_visit', 'work', 'inspection', 'delivery')",
        name="ck_schedule_entries_event_type",
    ),
    CheckConstraint(
        "status IN ('scheduled', 'in_progress', 'completed', 'cancelled')",
        name="ck_schedule_entries_status",
    ),
    CheckConstraint("ends_at > starts_at", name="ck_schedule_entries_interval"),
    CheckConstraint("version > 0", name="ck_schedule_entries_version"),
)

schedule_status_history = Table(
    "schedule_status_history",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "schedule_entry_id",
        String(36),
        ForeignKey("schedule_entries.id"),
        nullable=False,
        index=True,
    ),
    Column("from_status", String(40), nullable=False),
    Column("to_status", String(40), nullable=False),
    Column("note", Text, nullable=False),
    Column("actor", String(320), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

field_reports = Table(
    "field_reports",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("job_id", String(36), ForeignKey("jobs.id"), nullable=False, index=True),
    Column("service_date", Date, nullable=False, index=True),
    Column("revision", Integer, nullable=False),
    Column("previous_revision_id", String(36), ForeignKey("field_reports.id")),
    Column("status", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("workforce_total", Integer, nullable=False),
    Column("workforce_hours", String(40), nullable=False),
    Column("weather", Text, nullable=False),
    Column("completed_work", Text, nullable=False),
    Column("materials", Text, nullable=False),
    Column("equipment", Text, nullable=False),
    Column("delays", Text, nullable=False),
    Column("issues", Text, nullable=False),
    Column("safety_observations", Text, nullable=False),
    Column("created_by", String(320), nullable=False),
    Column("submitted_by", String(320)),
    Column("submitted_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("job_id", "service_date", "revision", name="uq_field_revision"),
    CheckConstraint("revision > 0", name="ck_field_reports_revision"),
    CheckConstraint("version > 0", name="ck_field_reports_version"),
    CheckConstraint("workforce_total >= 0", name="ck_field_reports_workforce"),
    CheckConstraint(
        "status IN ('draft', 'submitted', 'correction_required', 'corrected', 'superseded')",
        name="ck_field_reports_status",
    ),
)

field_report_corrections = Table(
    "field_report_corrections",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "field_report_id",
        String(36),
        ForeignKey("field_reports.id"),
        nullable=False,
        index=True,
    ),
    Column("reason", Text, nullable=False),
    Column("requested_by", String(320), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
)

field_report_photos = Table(
    "field_report_photos",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "field_report_id",
        String(36),
        ForeignKey("field_reports.id"),
        nullable=False,
        index=True,
    ),
    Column("stage", String(20), nullable=False),
    Column("original_name", String(500), nullable=False),
    Column("storage_key", String(1_000), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("uploaded_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "stage IN ('before', 'during', 'after')", name="ck_field_photo_stage"
    ),
)

employee_invites = Table(
    "employee_invites",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

employee_tasks = Table(
    "employee_tasks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
    Column("requirement_id", String(120), nullable=False),
    Column("label", String(300), nullable=False),
    Column("responsible_party", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("due_date", Date, nullable=False),
    Column("instructions", Text, nullable=False),
    Column("applicability_reason", Text, nullable=False),
    Column("evidence_required", Integer, nullable=False),
    Column("completion_method", String(40), nullable=False),
    Column("applicability_review_required", Integer, nullable=False),
    Column("applicability_status", String(40), nullable=False),
    Column("retention_rule", Text, nullable=False),
    Column("data_classification", String(40), nullable=False),
    Column("data_category", String(40), nullable=False),
    Column("official_source", Text, nullable=False),
    Column("legal_review_status", String(20), nullable=False),
    Column("signature_statement", Text),
    Column("applicability_decided_at", DateTime(timezone=True)),
    Column("applicability_decided_by", String(320)),
    Column("rule_version", String(120), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("completed_by", String(320)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "data_category IN ('identity_i9', 'tax', 'banking', "
        "'medical_disability', 'veteran', 'general')",
        name="ck_employee_tasks_data_category",
    ),
)

employee_signatures = Table(
    "employee_signatures",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
    Column("task_id", String(36), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("signer_email", String(320), nullable=False),
    Column("signer_subject_hash", String(64), nullable=False),
    Column("typed_name", String(200), nullable=False),
    Column("statement_version", String(120), nullable=False),
    Column("statement_text", Text, nullable=False),
    Column("statement_hash", String(64), nullable=False),
    Column("status", String(40), nullable=False),
    Column("signed_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("task_id", "version", name="uq_employee_signature_task_version"),
)

employee_documents = Table(
    "employee_documents",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
    Column("task_id", String(36), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("original_name", String(500), nullable=False),
    Column("storage_key", String(1_000), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("data_classification", String(40), nullable=False),
    Column("nonce_base64", String(40), nullable=False),
    Column("key_version", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("uploaded_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("task_id", "version", name="uq_employee_document_task_version"),
)

employee_notification_outbox = Table(
    "employee_notification_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("employee_id", String(36), nullable=False, index=True),
    Column("destination", String(320), nullable=False),
    Column("payload", Text, nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("attempts", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False, index=True),
    Column("locked_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("provider_message_id", String(200)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True)),
)
