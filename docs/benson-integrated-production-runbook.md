# Benson Integrated Production Runbook

This runbook supersedes all separate-app Benson deployment instructions until
the integrated application has a green parity report and release authorization.
The production product is one immutable OpenConstructionERP image with additive
Benson edition modules.

## Release Inputs

Record all of the following before any candidate deployment:

- exact clean Git commit based on `19bd8e0856b549e40472e2b57a6c82b8a0722a73`;
- green upstream, Benson, security, browser, migration, and packaging CI run;
- passing `artifacts/benson-parity.json`;
- immutable container digest, never a mutable tag alone;
- existing production revision and database rollback identifiers.

## Provisioning

Provision a fresh PostgreSQL database named `benson_erp_v2`, a dedicated Redis
instance, a private GCS bucket with uniform bucket-level access, and Secret
Manager values for database, Redis, JWT, storage, email, and directory
credentials. Grant the runtime service account only object access to the Benson
bucket and secret access to the exact runtime secrets.

Run migrations and tenant bootstrap as one-shot jobs using the same image digest
as the application. Start separate web, worker, and scheduler pools. Never run a
migration from a developer checkout or a different image.

## Candidate

Deploy the exact digest with zero traffic and these runtime values:

```text
OE_EDITION=benson
OE_SUPPORTED_LOCALES=en
OE_DEFAULT_LOCALE=en-US
OE_DEFAULT_REGION=benson_eastern_oregon
```

Keep the current production revision at 100% traffic. Do not enable Resend or
Google Directory yet. Execute health, migration-head, module-loader, OpenAPI,
browser-route, role, storage, worker, and representative upstream module-family
smokes against the revision URL. Record results in an immutable smoke artifact.

The production resource defaults are project `civic-wall-494004-b3`, region
`us-west1`, Cloud Run service `benson-operations`, runtime service account
`benson-operations@civic-wall-494004-b3.iam.gserviceaccount.com`, and Cloud SQL
instance `benson-openconstructionerp-postgres`. The domain mapping remains on
the existing service while a tagged candidate receives zero traffic.

Use the same immutable image digest for migrations and deployment:

```bash
IMAGE_DIGEST='us-west1-docker.pkg.dev/.../image@sha256:...' \
  deploy/cloud-run/run-benson-migrations.sh

IMAGE_DIGEST='us-west1-docker.pkg.dev/.../image@sha256:...' \
CI_RUN_URL='https://github.com/.../actions/runs/...' \
  deploy/cloud-run/deploy-benson-candidate.sh

python scripts/smoke_benson_candidate.py \
  'https://benson-candidate---benson-operations-....run.app' \
  --report artifacts/releases/candidate-smoke.json

IMAGE_DIGEST='us-west1-docker.pkg.dev/.../image@sha256:...' \
SMOKE_REPORT='artifacts/releases/candidate-smoke.json' \
  deploy/cloud-run/deploy-benson-worker-pools.sh
```

The deployment script reads database, JWT, and Resend values from Secret
Manager and never prints them. Its default secret names are
`benson-erp-v2-database-url`, `openconstructionerp-secret-key`, and
`resend-api-key`. Google Directory stays fail-closed unless a separately
approved existing service-account secret is available.

The candidate uses native Google Cloud Storage through Application Default
Credentials (`OE_STORAGE_BACKEND=gcs`). The runtime service account receives
object access to the existing private bucket
`benson-operations-private-uploads-1048944000089`; no service-account key file
is stored in Secret Manager or the image.

Redis runs as authenticated Memorystore instance `benson-erp-redis` on the
private `default` VPC. Cloud Run reaches it through connector
`benson-serverless`; the URL is stored as `benson-erp-redis-url` and bound to
the cache, Celery broker, and Celery result-backend environment variables.
After the zero-traffic candidate passes smoke, deploy one Celery worker and one
Celery scheduler worker pool from the same image digest. The worker bootstrap
registers Benson handlers before consuming any queued job.

## Cutover Authorization

Cutover is blocked until an authorized operator names the exact candidate
revision, image digest, green CI run, parity report, smoke record, current
rollback revision, and rollback database. Resend and Google Directory may be
enabled only after candidate smoke tests pass.

Shift traffic only to the authorized revision. Immediately verify `/api/health`,
browser deep links, authentication, background jobs, object storage, and one
read/write journey for each Benson role.

## Rollback and Retention

Rollback moves traffic to the named prior revision and restores provider routing.
Database rollback uses the retained pre-cutover database rather than destructive
down-migrations. Retain the previous revision and database for seven full days;
deletion requires a separate post-retention approval.
