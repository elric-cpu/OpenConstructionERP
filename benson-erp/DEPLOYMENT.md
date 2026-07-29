# Benson ERP v2 production release

The production service is `benson-operations` in project
`civic-wall-494004-b3`, region `us-west1`. The same immutable image digest runs
the web/API service, migration and bootstrap jobs, and the worker pools.

## Release invariants

- Build only a clean commit already pushed to `elric-cpu/OpenConstructionERP:main`.
- Tag the image with the full Git SHA, resolve it to a digest once, and deploy only the digest.
- Keep the current `benson-operations` revision and database unchanged for rollback.
- Apply Alembic only to the fresh `benson_erp_v2` database through the migration job.
- Deploy the API candidate with zero traffic and keep both worker pools at zero instances.
- Do not enable SMTP or Google Directory processing until candidate smoke checks pass.
- Traffic movement requires an authorization naming the candidate revision and digest.

## Resource names

| Resource | Name |
|---|---|
| Artifact image | `us-west1-docker.pkg.dev/civic-wall-494004-b3/cloud-run-source-deploy/benson-erp-v2` |
| Cloud Run service | `benson-operations` |
| Migration job | `benson-erp-v2-migrate` |
| Bootstrap job | `benson-erp-v2-bootstrap` |
| Worker pool | `benson-erp-worker` |
| Scheduler pool | `benson-erp-scheduler` |
| PostgreSQL database | `benson_erp_v2` |
| Runtime role | `benson_erp_v2_app` |
| Migration role | `benson_erp_v2_owner` |
| Memorystore | `benson-erp-redis` |
| Private bucket | `benson-erp-v2-private-uploads-1048944000089` |

The runtime identity is
`benson-operations@civic-wall-494004-b3.iam.gserviceaccount.com`. Use numeric
Secret Manager versions in every deployed revision.

## Build and resolve one image

From this directory in a clean checkout:

```bash
RELEASE_SHA="$(git rev-parse HEAD)"
test -z "$(git status --porcelain)"
test "${#RELEASE_SHA}" -eq 40

gcloud builds submit \
  --project civic-wall-494004-b3 \
  --config cloudbuild.yaml \
  --substitutions "_IMAGE_TAG=${RELEASE_SHA},_REVISION=${RELEASE_SHA}" \
  .

IMAGE_REPOSITORY="us-west1-docker.pkg.dev/civic-wall-494004-b3/cloud-run-source-deploy/benson-erp-v2"
IMAGE_DIGEST="$(gcloud artifacts docker images describe \
  "${IMAGE_REPOSITORY}:${RELEASE_SHA}" \
  --project civic-wall-494004-b3 \
  --format='value(image_summary.digest)')"
IMAGE_REFERENCE="${IMAGE_REPOSITORY}@${IMAGE_DIGEST}"
test "${IMAGE_DIGEST#sha256:}" != "${IMAGE_DIGEST}"
```

Record the previous serving revision, its digest, and its traffic allocation
before creating any resource or revision.

## Runtime configuration

All four runtimes use `ENVIRONMENT=production`, the v2 runtime database URL,
the Memorystore `REDIS_URL`, `STORAGE_BACKEND=gcs`, the private bucket/project,
same-origin `CORS_ORIGINS` and `FRONTEND_URL`, signing/encryption secrets,
metrics authentication, and structured logging. The image supplies
`WEB_DIST_PATH=/app/web-dist`.

The API and both worker pools attach to the Cloud SQL instance and use Direct
VPC egress to the Memorystore network. The migration and bootstrap jobs attach
to Cloud SQL but do not receive public ingress.

Production email uses Resend SMTP over STARTTLS. Google Directory uses the
existing delegated service-account secret and the approved no-paid-license test
OU. The worker pools remain scaled to zero until both configurations pass their
controlled checks.

## Database initialization

1. Back up the current production instance.
2. Create `benson_erp_v2`, `benson_erp_v2_owner`, and `benson_erp_v2_app` without altering the old database.
3. Apply the runtime grants from `infrastructure/docker/postgres/init-app-role.sql`, replacing development names with the v2 roles.
4. Deploy and execute `benson-erp-v2-migrate` using `MIGRATION_DATABASE_URL`; run `alembic upgrade head` and then `alembic check` against the same digest.
5. Deploy and execute `benson-erp-v2-bootstrap` with the bootstrap password mounted as a file, creating `Benson Enterprises`, slug `benson-enterprises`, and `elric@bensonhomesolutions.com`.
6. Destroy the bootstrap secret version after the first authenticated login is verified.

## Candidate and cutover

Deploy `IMAGE_REFERENCE` to `benson-operations` with zero traffic and tag it
`erp2-candidate`. Verify `/health/live`, `/health/ready`, `/login`, `/activate`,
authentication/MFA, every current business journey, GCS artifacts, correlation
logging, and queued outbox records.

After candidate checks, validate the approved Directory test OU and Resend test
recipient, then scale `benson-erp-worker` and `benson-erp-scheduler` to one.
Prove one idempotent Directory/activation delivery and an empty dead-letter
queue. Record authorization for the exact revision and digest, then assign 100%
traffic to it and repeat public-domain smoke checks.

On any critical failure, immediately restore 100% traffic to the recorded prior
revision and scale both v2 worker pools to zero. Retain the old revision and
database read-only for seven days; their removal is a separate approved action.
