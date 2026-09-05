# Proposal documents

Approved estimates can be issued as branded, client-visible proposal PDFs. The proposal stores
scope and price snapshots, while the generated `Document` record stores tenant and proposal
lineage, filename, MIME type, byte count, object key, and SHA-256 checksum.

## Integrity and acceptance

- Proposal PDFs are written with create-only storage semantics.
- Document downloads recompute and verify SHA-256 before returning content.
- Acceptance requires explicit consent and an acceptance statement.
- The signer name, timestamp, source IP, user agent, and accepted PDF checksum are retained.
- Accepted proposals are never edited. A changed scope or price requires a new proposal version.
- Client documents contain selling price, tax, and total; internal cost and margin are excluded.

## Branding

The renderer uses the tenant organization name, phone, primary color, and secondary color.
Branding values are organization settings rather than Benson-specific application constants.
The default color values are `#722F37` and `#F5F1E8`.

## Storage

Object keys begin with `tenants/{tenant_id}` and include the proposal ID, document version, and
checksum. Every backend rejects traversal and refuses to overwrite an existing artifact.

| Backend | Intended use | Immutable-create control | Temporary access |
|---|---|---|---|
| `local` | Host development and tests | Exclusive file creation | Authenticated API proxy |
| `s3` | MinIO or AWS S3 | `If-None-Match: *` | Provider-signed GET URL |
| `gcs` | Google Cloud production | Generation-match zero | V4 signed GET URL |

Docker Compose selects the `s3` adapter and creates the private `benson-erp` MinIO bucket before
the API starts. Production must use `s3` or `gcs`; startup rejects local storage and rejects HTTP
S3 endpoints. GCS uses Application Default Credentials, allowing Cloud Run workload identity
without service-account key files.

Signed URLs expire after `STORAGE_SIGNED_URL_SECONDS`, constrained to 30–3600 seconds. Authorization
is checked against the tenant and `proposals.read` permission before a signed URL is issued. The
ordinary PDF endpoint remains available as an authenticated, integrity-checking proxy.
