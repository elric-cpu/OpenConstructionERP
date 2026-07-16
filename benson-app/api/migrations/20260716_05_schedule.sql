CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS schedule_entries (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES jobs(id),
    event_type VARCHAR(40) NOT NULL CHECK (
        event_type IN ('site_visit', 'work', 'inspection', 'delivery')
    ),
    status VARCHAR(40) NOT NULL CHECK (
        status IN ('scheduled', 'in_progress', 'completed', 'cancelled')
    ),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    assigned_to VARCHAR(320) NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    created_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (ends_at > starts_at)
);

CREATE INDEX IF NOT EXISTS ix_schedule_entries_job_id
    ON schedule_entries(job_id);
CREATE INDEX IF NOT EXISTS ix_schedule_entries_starts_at
    ON schedule_entries(starts_at);
CREATE INDEX IF NOT EXISTS ix_schedule_entries_ends_at
    ON schedule_entries(ends_at);
CREATE INDEX IF NOT EXISTS ix_schedule_entries_assigned_to
    ON schedule_entries(assigned_to);

CREATE TABLE IF NOT EXISTS schedule_status_history (
    id VARCHAR(36) PRIMARY KEY,
    schedule_entry_id VARCHAR(36) NOT NULL REFERENCES schedule_entries(id),
    from_status VARCHAR(40) NOT NULL,
    to_status VARCHAR(40) NOT NULL,
    note TEXT NOT NULL,
    actor VARCHAR(320) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_schedule_status_history_entry_id
    ON schedule_status_history(schedule_entry_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'schedule_entries_no_overlap'
    ) THEN
        ALTER TABLE schedule_entries
            ADD CONSTRAINT schedule_entries_no_overlap
            EXCLUDE USING gist (
                assigned_to WITH =,
                tstzrange(starts_at, ends_at, '[)') WITH &&
            )
            WHERE (status IN ('scheduled', 'in_progress'));
    END IF;
END
$$;
