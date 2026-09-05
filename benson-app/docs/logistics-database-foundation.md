# Logistics database foundation

The additive PostgreSQL migration at
`api/migrations/20260716_01_logistics_foundation.sql` establishes a holding and
operations contract without changing the current Benson lead or onboarding
tables. It is intentionally not imported by `storage_schema.py`, so existing
SQLite tests and `metadata.create_all()` behavior remain unchanged until an
application integration is separately reviewed.

## What it adds

- A public-inquiry holding queue retaining both immutable raw input and a
  normalized payload, with a digest and idempotency key.
- Contacts with exact uppercase alphanumeric UEI (12 characters) and CAGE (5
  characters) checks when those identifiers are supplied.
- Oregon-only route areas with county/locality, postal-code, frontier-authority,
  travel, service-tier, and route-day metadata. Fields is represented as an
  ordinary locality row (for example, route code `fields-or`), not hard-coded
  into the schema.
- Work orders and private photo-asset metadata, including content type, size,
  SHA-256 digest, and lifecycle state. The migration stores object keys, not
  public URLs or image bytes.
- An inbound-message media queue for verified provider webhooks. It records the
  provider message/media identity, a one-way sender-phone hash and optional
  encrypted secret-manager reference, inquiry or accepted-lead link, temporary
  provider media URL, and claim state. Webhooks enqueue; a separate worker must
  fetch, validate, scan, and privately store media asynchronously.
- A provider-neutral transactional outbox and marketing touch attribution.
- Actor/time audit columns and retention-friendly archived, hold, and purge
  fields. Foreign-key deletion behavior prevents accidental cascades through
  operational history.

JSON Schema payload contracts are under `api/contracts/`. Producers must
canonicalize normalized JSON before calculating lowercase hexadecimal SHA-256
digests. UEI and CAGE values must be trimmed and uppercased before validation;
the database rejects lowercase, punctuation, whitespace, and wrong lengths.

## Applying safely

1. Take a timestamped PostgreSQL backup and record its checksum.
2. Run the migration first against an empty or restored staging database using
   a role permitted to create tables and indexes.
3. Inspect every `logistics_*` table and constraint, then run representative
   valid and invalid UEI/CAGE inserts inside a transaction that is rolled back.
4. Apply the unchanged file once in production during an approved maintenance
   window. `IF NOT EXISTS` makes object creation rerunnable, but it is not a
   substitute for recording the migration checksum in deployment evidence.
5. Do not route inquiries or start an outbox worker until its application code,
   authorization, retention job, provider policy, and rollback steps have been
   reviewed separately.

There is no destructive down migration. Rollback means disabling new writers
and readers while retaining the additive tables for reconciliation. Dropping
tables requires a separate, explicitly approved retention review.

## Repository boundary

`app/logistics_store.py` exposes the PostgreSQL-only repository operations
without adding these tables to SQLAlchemy's bootstrap metadata:

- `create_or_get_public_inquiry(...)` checks the existing lead idempotency key,
  inserts or returns a held inquiry, and rejects same-key/different-payload use.
- `link_photo_asset_to_work_order(...)` links a private object by work order and
  digest without creating duplicates.
- `enqueue_inbound_message_media(...)` records verified webhook media for an
  asynchronous fetch worker; it does not download provider media.
- `record_logistics_integration_event(...)` appends an attributable event to the
  existing audit history.

Calling the first three methods before applying the PostgreSQL migration is an
operator error. SQLite bootstrap and tests deliberately do not create the
`logistics_*` tables.
