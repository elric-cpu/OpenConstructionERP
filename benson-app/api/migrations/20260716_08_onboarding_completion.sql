ALTER TABLE employee_tasks
    ADD COLUMN IF NOT EXISTS data_category VARCHAR(40);

UPDATE employee_tasks
SET data_category = CASE
    WHEN requirement_id IN ('form-i9', 'form-i9-employer-review', 'e-verify')
        THEN 'identity_i9'
    WHEN requirement_id IN (
        'federal-w4', 'oregon-w4', 'oregon-new-hire-report',
        'payroll-enrollment', 'davis-bacon', 'contractor-w9'
    ) THEN 'tax'
    WHEN requirement_id = 'payment-election' THEN 'banking'
    WHEN requirement_id = 'section-503-self-id' THEN 'medical_disability'
    WHEN requirement_id = 'vevraa-self-id' THEN 'veteran'
    ELSE 'general'
END
WHERE data_category IS NULL;

ALTER TABLE employee_tasks
    ALTER COLUMN data_category SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_employee_tasks_data_category'
    ) THEN
        ALTER TABLE employee_tasks
            ADD CONSTRAINT ck_employee_tasks_data_category CHECK (
                data_category IN (
                    'general', 'identity_i9', 'tax', 'banking',
                    'medical_disability', 'veteran'
                )
            );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS onboarding_employee_versions (
    employee_id VARCHAR(36) PRIMARY KEY REFERENCES employees(id),
    version INTEGER NOT NULL CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS onboarding_task_versions (
    task_id VARCHAR(36) PRIMARY KEY REFERENCES employee_tasks(id),
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id),
    version INTEGER NOT NULL CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_onboarding_task_versions_employee
    ON onboarding_task_versions(employee_id);

CREATE TABLE IF NOT EXISTS onboarding_task_reviews (
    id VARCHAR(36) PRIMARY KEY,
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id),
    task_id VARCHAR(36) NOT NULL REFERENCES employee_tasks(id),
    review_type VARCHAR(40) NOT NULL
        CHECK (review_type IN ('task_review', 'applicability')),
    from_status VARCHAR(40) NOT NULL,
    to_status VARCHAR(40) NOT NULL,
    decision VARCHAR(40) NOT NULL,
    comment TEXT NOT NULL,
    reviewer_email VARCHAR(320) NOT NULL,
    reviewer_name VARCHAR(200),
    reviewer_qualification VARCHAR(300),
    rule_version VARCHAR(120) NOT NULL,
    task_version INTEGER NOT NULL CHECK (task_version > 1),
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_onboarding_task_reviews_employee
    ON onboarding_task_reviews(employee_id);
CREATE INDEX IF NOT EXISTS ix_onboarding_task_reviews_task
    ON onboarding_task_reviews(task_id);

CREATE TABLE IF NOT EXISTS onboarding_task_submissions (
    id VARCHAR(36) PRIMARY KEY,
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id),
    task_id VARCHAR(36) NOT NULL REFERENCES employee_tasks(id),
    evidence_type VARCHAR(40) NOT NULL
        CHECK (evidence_type IN ('document', 'signature', 'protected_response')),
    evidence_id VARCHAR(36) NOT NULL,
    submission_version INTEGER NOT NULL CHECK (submission_version > 0),
    submitted_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_onboarding_submission_version
        UNIQUE (task_id, submission_version)
);
CREATE INDEX IF NOT EXISTS ix_onboarding_task_submissions_employee
    ON onboarding_task_submissions(employee_id);

CREATE TABLE IF NOT EXISTS onboarding_rule_versions (
    id VARCHAR(120) PRIMARY KEY,
    status VARCHAR(40) NOT NULL
        CHECK (status IN ('pending_legal_review', 'approved', 'superseded')),
    requirements_digest VARCHAR(64) NOT NULL,
    requirements_snapshot TEXT NOT NULL,
    approved_by VARCHAR(320),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_provisioning_commands (
    id VARCHAR(36) PRIMARY KEY,
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id),
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('create', 'suspend')),
    status VARCHAR(40) NOT NULL CHECK (
        status IN (
            'pending_approval', 'approved', 'executing', 'verified',
            'admin_confirmation_required', 'admin_confirmed', 'failed',
            'manual_review_required', 'suspended'
        )
    ),
    version INTEGER NOT NULL CHECK (version > 0),
    idempotency_key VARCHAR(120) NOT NULL UNIQUE,
    target_email VARCHAR(320) NOT NULL,
    target_org_unit VARCHAR(300) NOT NULL,
    external_user_id VARCHAR(200),
    requested_by VARCHAR(320) NOT NULL,
    approved_by VARCHAR(320),
    executed_by VARCHAR(320),
    failure_code VARCHAR(120),
    bootstrap_credential TEXT,
    available_at TIMESTAMPTZ NOT NULL,
    locked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_identity_commands_employee
    ON identity_provisioning_commands(employee_id);
CREATE INDEX IF NOT EXISTS ix_identity_commands_status
    ON identity_provisioning_commands(status);
CREATE INDEX IF NOT EXISTS ix_identity_commands_available
    ON identity_provisioning_commands(available_at);

CREATE TABLE IF NOT EXISTS identity_provisioning_attempts (
    id VARCHAR(36) PRIMARY KEY,
    command_id VARCHAR(36) NOT NULL REFERENCES identity_provisioning_commands(id),
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    result VARCHAR(40) NOT NULL,
    provider_code VARCHAR(120),
    details TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_identity_provisioning_attempt UNIQUE (command_id, attempt)
);
CREATE INDEX IF NOT EXISTS ix_identity_attempts_command
    ON identity_provisioning_attempts(command_id);

CREATE TABLE IF NOT EXISTS onboarding_admin_confirmations (
    id VARCHAR(36) PRIMARY KEY,
    command_id VARCHAR(36) NOT NULL UNIQUE
        REFERENCES identity_provisioning_commands(id),
    confirmed_by VARCHAR(320) NOT NULL,
    reason TEXT NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS onboarding_retention_holds (
    id VARCHAR(36) PRIMARY KEY,
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id),
    reason TEXT NOT NULL,
    created_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    released_by VARCHAR(320),
    released_at TIMESTAMPTZ,
    CONSTRAINT ck_onboarding_retention_hold_release_pair CHECK (
        (released_by IS NULL AND released_at IS NULL)
        OR (released_by IS NOT NULL AND released_at IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_onboarding_retention_holds_employee
    ON onboarding_retention_holds(employee_id);

CREATE TABLE IF NOT EXISTS onboarding_offboarding_events (
    id VARCHAR(36) PRIMARY KEY,
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id),
    reason TEXT NOT NULL,
    previous_status VARCHAR(40) NOT NULL,
    session_revoked_at TIMESTAMPTZ NOT NULL,
    directory_command_id VARCHAR(36) REFERENCES identity_provisioning_commands(id),
    actor VARCHAR(320) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_onboarding_offboarding_employee
    ON onboarding_offboarding_events(employee_id);

INSERT INTO onboarding_employee_versions (employee_id, version, updated_at)
SELECT id, 1, updated_at FROM employees
ON CONFLICT (employee_id) DO NOTHING;

INSERT INTO onboarding_task_versions (task_id, employee_id, version, updated_at)
SELECT id, employee_id, 1, updated_at FROM employee_tasks
ON CONFLICT (task_id) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_employee_invites_employee'
    ) THEN
        ALTER TABLE employee_invites
            ADD CONSTRAINT fk_employee_invites_employee
            FOREIGN KEY (employee_id) REFERENCES employees(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_employee_tasks_employee'
    ) THEN
        ALTER TABLE employee_tasks
            ADD CONSTRAINT fk_employee_tasks_employee
            FOREIGN KEY (employee_id) REFERENCES employees(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_employee_documents_employee'
    ) THEN
        ALTER TABLE employee_documents
            ADD CONSTRAINT fk_employee_documents_employee
            FOREIGN KEY (employee_id) REFERENCES employees(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_employee_documents_task'
    ) THEN
        ALTER TABLE employee_documents
            ADD CONSTRAINT fk_employee_documents_task
            FOREIGN KEY (task_id) REFERENCES employee_tasks(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_employee_signatures_employee'
    ) THEN
        ALTER TABLE employee_signatures
            ADD CONSTRAINT fk_employee_signatures_employee
            FOREIGN KEY (employee_id) REFERENCES employees(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_employee_signatures_task'
    ) THEN
        ALTER TABLE employee_signatures
            ADD CONSTRAINT fk_employee_signatures_task
            FOREIGN KEY (task_id) REFERENCES employee_tasks(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_employee_outbox_employee'
    ) THEN
        ALTER TABLE employee_notification_outbox
            ADD CONSTRAINT fk_employee_outbox_employee
            FOREIGN KEY (employee_id) REFERENCES employees(id);
    END IF;
END $$;

-- Rollback contract: rollback is permitted only before any onboarding command,
-- evidence, review, signature, hold, or offboarding event exists. Restore the
-- pre-migration database snapshot instead of dropping regulated employee data.
