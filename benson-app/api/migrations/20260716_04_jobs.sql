CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(36) PRIMARY KEY,
    number VARCHAR(40) NOT NULL UNIQUE,
    estimate_id VARCHAR(36) NOT NULL UNIQUE REFERENCES estimates(id),
    customer_id VARCHAR(36) NOT NULL REFERENCES customers(id),
    title VARCHAR(300) NOT NULL,
    scope_snapshot TEXT NOT NULL,
    contract_value_cents BIGINT NOT NULL CHECK (contract_value_cents >= 0),
    status VARCHAR(40) NOT NULL CHECK (
        status IN ('planned', 'active', 'on_hold', 'completed', 'cancelled')
    ),
    target_start DATE,
    target_completion DATE,
    assigned_to VARCHAR(320),
    site_address VARCHAR(500) NOT NULL DEFAULT '',
    created_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (
        target_start IS NULL OR target_completion IS NULL
        OR target_completion >= target_start
    )
);

CREATE INDEX IF NOT EXISTS ix_jobs_customer_id ON jobs(customer_id);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status);
