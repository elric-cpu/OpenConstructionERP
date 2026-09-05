BEGIN;

CREATE TABLE IF NOT EXISTS estimates (
    id VARCHAR(36) PRIMARY KEY,
    number VARCHAR(40) NOT NULL UNIQUE,
    customer_id VARCHAR(36) NOT NULL,
    title VARCHAR(300) NOT NULL,
    scope_notes TEXT NOT NULL DEFAULT '',
    valid_until DATE NOT NULL,
    status VARCHAR(40) NOT NULL
        CHECK (status IN ('draft', 'ready', 'sent', 'accepted', 'declined', 'void')),
    version INTEGER NOT NULL CHECK (version > 0),
    subtotal_cents BIGINT NOT NULL CHECK (subtotal_cents >= 0),
    total_cents BIGINT NOT NULL CHECK (total_cents >= 0),
    created_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_estimates_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS estimate_lines (
    id VARCHAR(36) PRIMARY KEY,
    estimate_id VARCHAR(36) NOT NULL,
    position INTEGER NOT NULL CHECK (position > 0),
    description VARCHAR(1000) NOT NULL,
    quantity VARCHAR(40) NOT NULL,
    unit VARCHAR(40) NOT NULL,
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    line_total_cents BIGINT NOT NULL CHECK (line_total_cents >= 0),
    CONSTRAINT fk_estimate_lines_estimate
        FOREIGN KEY (estimate_id) REFERENCES estimates(id) ON DELETE CASCADE,
    CONSTRAINT uq_estimate_line_position UNIQUE (estimate_id, position)
);

CREATE INDEX IF NOT EXISTS ix_estimates_customer_status
    ON estimates (customer_id, status);
CREATE INDEX IF NOT EXISTS ix_estimate_lines_estimate
    ON estimate_lines (estimate_id, position);

COMMIT;
