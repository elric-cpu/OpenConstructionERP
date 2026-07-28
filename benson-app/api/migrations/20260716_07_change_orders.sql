ALTER TABLE jobs ADD COLUMN IF NOT EXISTS approved_change_order_cents BIGINT NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS billing_eligible_cents BIGINT NOT NULL DEFAULT 0;
UPDATE jobs SET billing_eligible_cents = contract_value_cents WHERE billing_eligible_cents = 0;

CREATE TABLE IF NOT EXISTS change_orders (
    id VARCHAR(36) PRIMARY KEY,
    root_id VARCHAR(36) NOT NULL,
    previous_revision_id VARCHAR(36) REFERENCES change_orders(id),
    revision INTEGER NOT NULL CHECK (revision > 0),
    number VARCHAR(60) NOT NULL UNIQUE,
    job_id VARCHAR(36) NOT NULL REFERENCES jobs(id),
    estimate_id VARCHAR(36) NOT NULL REFERENCES estimates(id),
    customer_id VARCHAR(36) NOT NULL REFERENCES customers(id),
    originating_field_report_id VARCHAR(36) REFERENCES field_reports(id),
    status VARCHAR(40) NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'void')),
    version INTEGER NOT NULL CHECK (version > 0),
    title VARCHAR(300) NOT NULL,
    schedule_impact_days INTEGER NOT NULL,
    internal_notes TEXT NOT NULL,
    customer_explanation TEXT NOT NULL,
    subtotal_cents BIGINT NOT NULL CHECK (subtotal_cents >= 0),
    created_by VARCHAR(320) NOT NULL,
    submitted_by VARCHAR(320),
    submitted_at TIMESTAMPTZ,
    decided_by VARCHAR(320),
    decided_at TIMESTAMPTZ,
    decision_note TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_change_order_revision UNIQUE (root_id, revision)
);
CREATE INDEX IF NOT EXISTS ix_change_orders_root_id ON change_orders(root_id);
CREATE INDEX IF NOT EXISTS ix_change_orders_job_id ON change_orders(job_id);

CREATE TABLE IF NOT EXISTS change_order_lines (
    id VARCHAR(36) PRIMARY KEY,
    change_order_id VARCHAR(36) NOT NULL REFERENCES change_orders(id),
    position INTEGER NOT NULL,
    description VARCHAR(1000) NOT NULL,
    quantity VARCHAR(40) NOT NULL,
    unit VARCHAR(40) NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    line_total_cents BIGINT NOT NULL,
    CONSTRAINT uq_change_order_line_position UNIQUE (change_order_id, position)
);
CREATE INDEX IF NOT EXISTS ix_change_order_lines_order ON change_order_lines(change_order_id);

CREATE TABLE IF NOT EXISTS change_order_evidence (
    id VARCHAR(36) PRIMARY KEY,
    change_order_id VARCHAR(36) NOT NULL REFERENCES change_orders(id),
    original_name VARCHAR(500) NOT NULL,
    storage_key VARCHAR(1000) NOT NULL,
    content_type VARCHAR(120) NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    uploaded_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_change_order_evidence_order ON change_order_evidence(change_order_id);

CREATE TABLE IF NOT EXISTS change_order_approvals (
    id VARCHAR(36) PRIMARY KEY,
    change_order_id VARCHAR(36) NOT NULL UNIQUE REFERENCES change_orders(id),
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('approved', 'rejected')),
    note TEXT NOT NULL,
    actor VARCHAR(320) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);
