-- Additive Benson logistics and public-inquiry foundation for PostgreSQL.
-- Application code supplies UUID values; no extension is required.
BEGIN;

CREATE TABLE IF NOT EXISTS logistics_route_areas (
    id uuid PRIMARY KEY,
    route_code varchar(80) NOT NULL UNIQUE,
    name varchar(200) NOT NULL,
    state_code char(2) NOT NULL DEFAULT 'OR'
        CHECK (state_code = 'OR'),
    county_name varchar(120) NOT NULL,
    locality_name varchar(120),
    postal_codes jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(postal_codes) = 'array'),
    geography jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(geography) = 'object'),
    is_frontier boolean NOT NULL DEFAULT false,
    frontier_authority varchar(240),
    frontier_effective_on date,
    service_tier varchar(40) NOT NULL DEFAULT 'review_required'
        CHECK (service_tier IN ('primary', 'route_dependent', 'review_required', 'unserved')),
    route_days jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(route_days) = 'array'),
    travel_minutes integer CHECK (travel_minutes IS NULL OR travel_minutes >= 0),
    status varchar(24) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'archived')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    CHECK (NOT is_frontier OR frontier_authority IS NOT NULL),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS logistics_contacts (
    id uuid PRIMARY KEY,
    contact_type varchar(32) NOT NULL
        CHECK (contact_type IN ('person', 'business', 'government', 'nonprofit', 'unknown')),
    display_name varchar(240) NOT NULL,
    organization_name varchar(240),
    email varchar(320),
    phone varchar(40),
    street_address text,
    locality_name varchar(120),
    state_code char(2) CHECK (state_code IS NULL OR state_code = 'OR'),
    postal_code varchar(20),
    uei char(12) CHECK (uei IS NULL OR uei ~ '^[A-Z0-9]{12}$'),
    cage_code char(5) CHECK (cage_code IS NULL OR cage_code ~ '^[A-Z0-9]{5}$'),
    route_area_id uuid REFERENCES logistics_route_areas(id) ON DELETE SET NULL,
    source_key varchar(200),
    normalized_digest char(64) NOT NULL
        CHECK (normalized_digest ~ '^[a-f0-9]{64}$'),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object'),
    status varchar(24) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'merged', 'archived')),
    merged_into_id uuid REFERENCES logistics_contacts(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    CHECK (email IS NOT NULL OR phone IS NOT NULL OR organization_name IS NOT NULL),
    CHECK (status <> 'merged' OR merged_into_id IS NOT NULL),
    CHECK (merged_into_id IS NULL OR merged_into_id <> id),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS logistics_inquiry_holding_queue (
    id uuid PRIMARY KEY,
    idempotency_key varchar(240) NOT NULL UNIQUE,
    source varchar(120) NOT NULL,
    source_message_id varchar(240),
    payload_digest char(64) NOT NULL
        CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
    raw_payload jsonb NOT NULL CHECK (jsonb_typeof(raw_payload) = 'object'),
    normalized_payload jsonb NOT NULL CHECK (jsonb_typeof(normalized_payload) = 'object'),
    contact_id uuid REFERENCES logistics_contacts(id) ON DELETE SET NULL,
    route_area_id uuid REFERENCES logistics_route_areas(id) ON DELETE SET NULL,
    queue_state varchar(32) NOT NULL DEFAULT 'held'
        CHECK (queue_state IN ('held', 'ready', 'accepted', 'rejected', 'duplicate', 'archived')),
    hold_reason varchar(500),
    disposition_reason varchar(500),
    accepted_lead_id varchar(36),
    available_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    CHECK (queue_state <> 'accepted' OR accepted_lead_id IS NOT NULL),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS logistics_work_orders (
    id uuid PRIMARY KEY,
    work_order_number varchar(80) NOT NULL UNIQUE,
    idempotency_key varchar(240) NOT NULL UNIQUE,
    inquiry_id uuid REFERENCES logistics_inquiry_holding_queue(id) ON DELETE SET NULL,
    contact_id uuid NOT NULL REFERENCES logistics_contacts(id) ON DELETE RESTRICT,
    route_area_id uuid REFERENCES logistics_route_areas(id) ON DELETE SET NULL,
    source_lead_id varchar(36),
    title varchar(300) NOT NULL,
    description text NOT NULL,
    priority varchar(24) NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'urgent', 'emergency')),
    status varchar(32) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'ready', 'scheduled', 'in_progress', 'blocked', 'completed', 'cancelled', 'archived')),
    scheduled_start timestamptz,
    scheduled_end timestamptz,
    completed_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(raw_payload) = 'object'),
    normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(normalized_payload) = 'object'),
    payload_digest char(64) NOT NULL
        CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    CHECK (scheduled_end IS NULL OR scheduled_start IS NULL OR scheduled_end >= scheduled_start),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS logistics_work_order_photo_assets (
    id uuid PRIMARY KEY,
    work_order_id uuid NOT NULL REFERENCES logistics_work_orders(id) ON DELETE RESTRICT,
    asset_role varchar(24) NOT NULL
        CHECK (asset_role IN ('intake', 'before', 'during', 'after', 'document', 'other')),
    storage_key varchar(1000) NOT NULL UNIQUE,
    original_name varchar(500) NOT NULL,
    content_type varchar(120) NOT NULL CHECK (content_type LIKE 'image/%'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    captured_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(metadata) = 'object'),
    status varchar(24) NOT NULL DEFAULT 'active'
        CHECK (status IN ('pending', 'active', 'quarantined', 'archived', 'purged')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    UNIQUE (work_order_id, sha256),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS logistics_inbound_message_media (
    id uuid PRIMARY KEY,
    provider varchar(80) NOT NULL,
    provider_message_id varchar(240) NOT NULL,
    provider_media_key varchar(240) NOT NULL,
    inquiry_id uuid REFERENCES logistics_inquiry_holding_queue(id) ON DELETE SET NULL,
    accepted_lead_id varchar(36),
    sender_phone_hash char(64) NOT NULL
        CHECK (sender_phone_hash ~ '^[a-f0-9]{64}$'),
    sender_phone_encrypted_ref varchar(1000),
    media_url text NOT NULL,
    content_type varchar(120) NOT NULL CHECK (content_type LIKE 'image/%'),
    media_ordinal integer NOT NULL DEFAULT 0 CHECK (media_ordinal >= 0),
    status varchar(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'stored', 'rejected', 'failed', 'archived')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at timestamptz,
    stored_asset_id uuid REFERENCES logistics_work_order_photo_assets(id) ON DELETE SET NULL,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    UNIQUE (provider, provider_media_key),
    UNIQUE (provider, provider_message_id, media_ordinal),
    CHECK (inquiry_id IS NOT NULL OR accepted_lead_id IS NOT NULL),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS logistics_provider_outbox (
    id uuid PRIMARY KEY,
    idempotency_key varchar(240) NOT NULL UNIQUE,
    aggregate_type varchar(80) NOT NULL,
    aggregate_id uuid NOT NULL,
    provider varchar(80) NOT NULL,
    operation varchar(120) NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_digest char(64) NOT NULL CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
    status varchar(24) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'delivered', 'failed', 'disabled', 'archived')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    available_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at timestamptz,
    delivered_at timestamptz,
    provider_message_id varchar(240),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    CHECK (attempts <= max_attempts),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS logistics_marketing_attribution (
    id uuid PRIMARY KEY,
    inquiry_id uuid NOT NULL REFERENCES logistics_inquiry_holding_queue(id) ON DELETE RESTRICT,
    contact_id uuid REFERENCES logistics_contacts(id) ON DELETE SET NULL,
    work_order_id uuid REFERENCES logistics_work_orders(id) ON DELETE SET NULL,
    touch_position varchar(24) NOT NULL
        CHECK (touch_position IN ('first', 'assist', 'last', 'conversion')),
    channel varchar(120),
    source varchar(240),
    medium varchar(240),
    campaign varchar(240),
    term varchar(500),
    content varchar(500),
    referrer text,
    landing_page text,
    click_ids jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(click_ids) = 'object'),
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(raw_payload) = 'object'),
    attribution_digest char(64) NOT NULL
        CHECK (attribution_digest ~ '^[a-f0-9]{64}$'),
    occurred_at timestamptz NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'superseded', 'archived')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by varchar(320) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by varchar(320) NOT NULL,
    archived_at timestamptz,
    retention_hold_until timestamptz,
    purge_after timestamptz,
    UNIQUE (inquiry_id, attribution_digest),
    CHECK (purge_after IS NULL OR archived_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_logistics_route_areas_service
    ON logistics_route_areas (state_code, county_name, service_tier)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS ix_logistics_route_areas_postal_codes
    ON logistics_route_areas USING gin (postal_codes);
CREATE INDEX IF NOT EXISTS ix_logistics_contacts_lookup
    ON logistics_contacts (lower(display_name), status);
CREATE INDEX IF NOT EXISTS ix_logistics_contacts_route
    ON logistics_contacts (route_area_id) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_contacts_uei
    ON logistics_contacts (uei) WHERE uei IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_contacts_cage
    ON logistics_contacts (cage_code) WHERE cage_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_inquiry_claim
    ON logistics_inquiry_holding_queue (queue_state, available_at, created_at)
    WHERE archived_at IS NULL AND queue_state IN ('held', 'ready');
CREATE INDEX IF NOT EXISTS ix_logistics_inquiry_source_message
    ON logistics_inquiry_holding_queue (source, source_message_id)
    WHERE source_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_inquiry_payload_gin
    ON logistics_inquiry_holding_queue USING gin (normalized_payload);
CREATE INDEX IF NOT EXISTS ix_logistics_work_orders_schedule
    ON logistics_work_orders (status, scheduled_start)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_work_orders_contact
    ON logistics_work_orders (contact_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_logistics_photo_work_order
    ON logistics_work_order_photo_assets (work_order_id, asset_role, created_at);
CREATE INDEX IF NOT EXISTS ix_logistics_inbound_media_claim
    ON logistics_inbound_message_media (provider, status, available_at)
    WHERE archived_at IS NULL AND status IN ('queued', 'failed');
CREATE INDEX IF NOT EXISTS ix_logistics_inbound_media_message
    ON logistics_inbound_message_media (provider, provider_message_id);
CREATE INDEX IF NOT EXISTS ix_logistics_provider_outbox_claim
    ON logistics_provider_outbox (provider, status, available_at)
    WHERE archived_at IS NULL AND status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS ix_logistics_marketing_inquiry_time
    ON logistics_marketing_attribution (inquiry_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_logistics_marketing_campaign
    ON logistics_marketing_attribution (source, medium, campaign)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_retention_inquiries
    ON logistics_inquiry_holding_queue (purge_after)
    WHERE purge_after IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_retention_assets
    ON logistics_work_order_photo_assets (purge_after)
    WHERE purge_after IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_logistics_retention_inbound_media
    ON logistics_inbound_message_media (purge_after)
    WHERE purge_after IS NOT NULL;

COMMIT;
