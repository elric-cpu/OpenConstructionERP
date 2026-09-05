BEGIN;

CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    company VARCHAR(200) NOT NULL DEFAULT '',
    phone VARCHAR(40) NOT NULL,
    email VARCHAR(320),
    billing_address VARCHAR(500) NOT NULL DEFAULT '',
    service_address VARCHAR(500) NOT NULL DEFAULT '',
    city VARCHAR(120) NOT NULL DEFAULT '',
    state VARCHAR(2) NOT NULL DEFAULT 'OR',
    zip_code VARCHAR(5) NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    status VARCHAR(40) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    source_lead_id VARCHAR(36) UNIQUE,
    created_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_customers_status_name
    ON customers (status, name);
CREATE INDEX IF NOT EXISTS ix_customers_email
    ON customers (email);
CREATE INDEX IF NOT EXISTS ix_customers_phone
    ON customers (phone);

COMMIT;
