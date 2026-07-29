# Object storage configuration

All file content is private. PostgreSQL stores tenant-scoped metadata and checksums; the selected
object provider stores bytes. Application records never store public object URLs.

## Local

Use `STORAGE_BACKEND=local` and `LOCAL_STORAGE_ROOT=.data/storage` for host development and unit
tests. Local storage is rejected when `ENVIRONMENT=production`.

## MinIO and S3

Set `STORAGE_BACKEND=s3`, `S3_BUCKET`, and `S3_REGION`. MinIO additionally needs
`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and path-style addressing. AWS workloads should
prefer an IAM role and omit static keys. When either static-key field is present, both are required.

When MinIO has different internal and browser-facing names, set `S3_ENDPOINT_URL` to the internal
service URL and `S3_PUBLIC_ENDPOINT_URL` to the browser-reachable URL. The signing client includes
the public host in the signature; rewriting a URL after signing would invalidate it.

Production custom endpoints must use HTTPS. Set `S3_SERVER_SIDE_ENCRYPTION=AES256` when the provider
does not enforce encryption through bucket policy.

## Google Cloud Storage

Set `STORAGE_BACKEND=gcs`, `GCS_BUCKET`, and `GCS_PROJECT`. Cloud Run should use a dedicated service
account with least-privilege object permissions and signBlob capability for V4 URLs. Do not mount or
store a JSON service-account key.

Recommended bucket controls:

- Uniform bucket-level access
- Public access prevention
- Google-managed encryption or a customer-managed key
- Object versioning and lifecycle rules matching retention policy
- Audit logs and alerting for policy changes
- CORS disabled unless a reviewed direct-upload workflow requires it

## Access behavior

Writes are create-only. Provider preconditions prevent an existing immutable artifact from being
replaced even during concurrent requests. Downloads through the API recompute SHA-256 before
returning bytes. Temporary URLs are issued only after API authorization and expire in at most one
hour.
