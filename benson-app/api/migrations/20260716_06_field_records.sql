CREATE TABLE IF NOT EXISTS field_reports (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES jobs(id),
    service_date DATE NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    previous_revision_id VARCHAR(36) REFERENCES field_reports(id),
    status VARCHAR(40) NOT NULL CHECK (status IN ('draft', 'submitted', 'correction_required', 'corrected', 'superseded')),
    version INTEGER NOT NULL CHECK (version > 0),
    workforce_total INTEGER NOT NULL CHECK (workforce_total >= 0),
    workforce_hours VARCHAR(40) NOT NULL,
    weather TEXT NOT NULL,
    completed_work TEXT NOT NULL,
    materials TEXT NOT NULL,
    equipment TEXT NOT NULL,
    delays TEXT NOT NULL,
    issues TEXT NOT NULL,
    safety_observations TEXT NOT NULL,
    created_by VARCHAR(320) NOT NULL,
    submitted_by VARCHAR(320),
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_field_revision UNIQUE (job_id, service_date, revision)
);
CREATE INDEX IF NOT EXISTS ix_field_reports_job_id ON field_reports(job_id);
CREATE INDEX IF NOT EXISTS ix_field_reports_service_date ON field_reports(service_date);

CREATE TABLE IF NOT EXISTS field_report_corrections (
    id VARCHAR(36) PRIMARY KEY,
    field_report_id VARCHAR(36) NOT NULL REFERENCES field_reports(id),
    reason TEXT NOT NULL,
    requested_by VARCHAR(320) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_field_report_corrections_report ON field_report_corrections(field_report_id);

CREATE TABLE IF NOT EXISTS field_report_photos (
    id VARCHAR(36) PRIMARY KEY,
    field_report_id VARCHAR(36) NOT NULL REFERENCES field_reports(id),
    stage VARCHAR(20) NOT NULL CHECK (stage IN ('before', 'during', 'after')),
    original_name VARCHAR(500) NOT NULL,
    storage_key VARCHAR(1000) NOT NULL,
    content_type VARCHAR(120) NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    uploaded_by VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_field_report_photos_report ON field_report_photos(field_report_id);
