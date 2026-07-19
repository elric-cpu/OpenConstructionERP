# Benson Operations release and production deployment

`erp.bensonhomesolutions.com` maps to the `benson-operations` Cloud Run
service. A successful build or zero-traffic deploy is not authorization to
change traffic, apply production migrations, enable Twilio, move money, or send
an employee invitation.

## Release invariants

- Build from a clean, merged commit and tag the image with its full 40-character
  Git SHA. Never build or deploy `latest`.
- Resolve the Artifact Registry tag to a `sha256:` digest and use the digest for
  every staging and production deploy.
- Run the same digest in isolated staging before creating the production
  candidate. Staging uses a separate PostgreSQL database, private buckets,
  Google test OU, payment-provider test mode, accounting-provider sandbox, and non-delivering
  notification providers.
- Deploy the production candidate to `benson-operations` with zero traffic.
  Preserve the current serving and rollback revisions.
- Keep Twilio disabled. Do not mount Twilio credentials or create SMS work for
  this release.
- Apply migrations only through the reviewed sequence and checksum procedure
  below. Application startup is not the migration mechanism.
- Change traffic only during the authorized 8–10 PM Pacific window after every
  G1–G8 prerequisite in `docs/production-cutover-evidence.md` is satisfied.

## Required infrastructure

- Regional, highly available PostgreSQL 16 with PITR, deletion protection, and
  a least-privilege application user.
- Private Google Cloud Storage buckets with uniform access, public-access
  prevention, versioning, and the approved retention rules.
- Google Workspace OAuth for `erp.bensonhomesolutions.com`, a no-paid-license
  onboarding test OU, and a separate invitation delivery address.
- Runtime identity
  `benson-operations@civic-wall-494004-b3.iam.gserviceaccount.com` with Cloud SQL
  Client, object access only to the required private buckets, and secret-level
  access only to its configured Secret Manager versions.
- Scheduler identity
  `benson-notification-scheduler@civic-wall-494004-b3.iam.gserviceaccount.com`
  with Cloud Run Invoker on `benson-operations` and no secret, database, bucket,
  or provider access.
- Numeric Secret Manager versions for the database URL, website signing,
  employee invitation signing, employee document encryption, FCC gateway, and
  Resend API key. Do not use `latest` in an immutable candidate.

## Build one commit-addressed image

Run from `benson-app/` in a clean checkout whose commit has passed the complete
local and GitHub gates:

```bash
RELEASE_SHA="$(git rev-parse HEAD)"
test "$(git status --porcelain)" = ""
test "${#RELEASE_SHA}" -eq 40

gcloud builds submit \
  --project civic-wall-494004-b3 \
  --config cloudbuild.yaml \
  --substitutions "_IMAGE_TAG=${RELEASE_SHA},_REVISION=${RELEASE_SHA}" \
  .
```

The Dockerfile pins every base image by multi-architecture digest, installs the
API from `uv.lock` with `uv sync --frozen`, and includes the SQL migration
bundle. Cloud Build rejects `latest`, the placeholder tag, and a revision that
is not a full Git SHA.

Resolve the pushed tag once and record the fully qualified digest in the
release evidence:

```bash
IMAGE_REPOSITORY="us-west1-docker.pkg.dev/civic-wall-494004-b3/cloud-run-source-deploy/benson-operations"
IMAGE_DIGEST="$(gcloud artifacts docker images describe \
  "${IMAGE_REPOSITORY}:${RELEASE_SHA}" \
  --project civic-wall-494004-b3 \
  --format='value(image_summary.digest)')"
test "${IMAGE_DIGEST#sha256:}" != "${IMAGE_DIGEST}"
IMAGE_REFERENCE="${IMAGE_REPOSITORY}@${IMAGE_DIGEST}"
```

Do not rebuild the release tag. If the digest or source-revision label differs
from the recorded value, discard the candidate and investigate.

## Migration checksums and history

The `Benson Rewrite Verify` workflow validates the numeric migration sequence,
rejects destructive SQL in the additive bundle, and publishes
`benson-migration-checksums-<git-sha>` as a 30-day CI artifact. Save that
artifact with the release record and compare it with the files inside the
candidate image:

```bash
docker run --rm --entrypoint sh "${IMAGE_REFERENCE}" -ceu '
  cd /app
  find migrations -maxdepth 1 -name "*.sql" -print0 \
    | sort -z \
    | xargs -0 sha256sum
'
```

Every database must have an operator-owned history table before a migration is
applied:

```sql
CREATE TABLE IF NOT EXISTS benson_schema_migrations (
    version varchar(160) PRIMARY KEY,
    sha256 char(64) NOT NULL,
    image_digest text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_by varchar(320) NOT NULL,
    CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    CHECK (image_digest ~ '^sha256:[a-f0-9]{64}$')
);
```

Use a short-lived operator connection through the Cloud SQL Auth Proxy. For
each file in lexical order:

1. Compare its SHA-256 with the CI artifact and image copy.
2. Refuse a recorded version with a different checksum or image digest.
3. Create a fresh backup and record database counts and ledger balances.
4. Run `psql -v ON_ERROR_STOP=1 -f <migration>` for a file that contains its
   own `BEGIN`/`COMMIT`; otherwise add `--single-transaction`. Apply it first in
   isolated staging.
5. Insert its version, checksum, image digest, and human operator into
   `benson_schema_migrations` immediately after successful application.
6. Query the new schema and rerun migration-contract, record-count, isolation,
   and application smoke tests.

The migrations are additive and do not provide destructive down scripts.
Application rollback means pausing workers and providers and restoring traffic
to the retained compatible revision. Database restore is a separate guarded
operation requiring reconciliation of any writes accepted after the backup. If
a migration succeeds but its history insert fails, stop and reconcile the
schema before recording or retrying it.

## Staging and zero-traffic production candidate

Deploy `IMAGE_REFERENCE` to isolated staging first and complete both required
UAT journeys, provider failures, backup restoration, accessibility/security
review, and HR/legal approval. No staging notification provider may deliver to
a real recipient and no staging payment may move real funds.

After staging passes, deploy the unchanged digest to the production service at
zero traffic. Replace every placeholder and numeric secret version with the
approved release record:

```bash
gcloud run deploy benson-operations \
  --image "${IMAGE_REFERENCE}" \
  --region us-west1 \
  --project civic-wall-494004-b3 \
  --service-account benson-operations@civic-wall-494004-b3.iam.gserviceaccount.com \
  --add-cloudsql-instances civic-wall-494004-b3:us-west1:benson-operations-postgres \
  --set-secrets BENSON_DATABASE_URL=benson-operations-database-url:REPLACE_NUMERIC_VERSION,BENSON_WEBSITE_SIGNING_SECRET=benson-erp-website-signing-secret:REPLACE_NUMERIC_VERSION,BENSON_EMPLOYEE_INVITE_SIGNING_SECRET=benson-employee-invite-signing-secret:REPLACE_NUMERIC_VERSION,BENSON_EMPLOYEE_DOCUMENT_ENCRYPTION_KEY=benson-employee-document-encryption-key:REPLACE_NUMERIC_VERSION,BENSON_FCC_AUTH_TOKEN=benson-fcc-auth-token:REPLACE_NUMERIC_VERSION,BENSON_RESEND_API_KEY=resend-api-key:REPLACE_NUMERIC_VERSION,BENSON_GOOGLE_DIRECTORY_CREDENTIALS_JSON=benson-google-directory-credentials:REPLACE_NUMERIC_VERSION \
  --set-env-vars BENSON_ENVIRONMENT=production,BENSON_STAFF_GOOGLE_AUDIENCE=REPLACE_GOOGLE_CLIENT_ID,BENSON_STAFF_GOOGLE_DOMAIN=bensonhomesolutions.com,BENSON_OWNER_EMAILS=REPLACE_APPROVED_OWNER_EMAILS,BENSON_UPLOAD_BUCKET=benson-operations-private-uploads-1048944000089,BENSON_UPLOAD_BASE_URL=https://erp.bensonhomesolutions.com,BENSON_FCC_BASE_URL=https://benson-fcc-gateway-ecdo5oua2a-uw.a.run.app,BENSON_NOTIFICATION_WORKER_AUDIENCE=https://benson-operations-1048944000089.us-west1.run.app,BENSON_NOTIFICATION_WORKER_EMAIL=benson-notification-scheduler@civic-wall-494004-b3.iam.gserviceaccount.com,BENSON_IDENTITY_WORKER_AUDIENCE=https://benson-operations-1048944000089.us-west1.run.app,BENSON_IDENTITY_WORKER_EMAIL=benson-identity-scheduler@civic-wall-494004-b3.iam.gserviceaccount.com,BENSON_GOOGLE_DIRECTORY_ADMIN=REPLACE_WORKSPACE_ADMIN_EMAIL,BENSON_GOOGLE_PAID_LICENSE_SKUS=REPLACE_REVIEWED_PAID_LICENSE_SKUS,BENSON_GOOGLE_PAID_LICENSE_SKUS_APPROVED=true,BENSON_NOTIFICATION_EMAIL_TO=REPLACE_INTERNAL_DELIVERY_EMAIL,BENSON_SMS_ENABLED_DEFAULT=false \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --no-traffic
```

Verify the candidate by its revision URL without sending invitations, sending
SMS, enabling external accounting writes, or creating payment sessions. Record
the revision, digest, migration history, authenticated role probes, monitoring,
backup, and rollback evidence before any cutover decision.

## Cutover and invitation stop conditions

During the authorized window, freeze legacy writes, create the final protected
exports, reconcile the guarded delta, switch website forms without dual-write,
and shift traffic only to the recorded digest. Pause and roll back on any
critical migration, health, authentication, upload, notification, audit, or
lead-to-cash smoke failure.

The single real employee invitation is a later G8 action. It is allowed only
after production smoke succeeds and Directory identity, no-paid-license state,
delivery address, HR/legal approval, and invitation audit controls are verified.
Twilio is not an invitation fallback and remains disabled.
