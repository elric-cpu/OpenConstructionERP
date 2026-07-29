#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT_DIR"

PROJECT_ID=${PROJECT_ID:-civic-wall-494004-b3}
REGION=${REGION:-us-west1}
WORKER_POOL=${WORKER_POOL:-benson-erp-worker}
SCHEDULER_POOL=${SCHEDULER_POOL:-benson-erp-scheduler}
RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SERVICE_ACCOUNT:-benson-operations@${PROJECT_ID}.iam.gserviceaccount.com}
CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE:-${PROJECT_ID}:${REGION}:benson-openconstructionerp-postgres}
DATABASE_SECRET=${DATABASE_SECRET:-benson-erp-v2-database-url}
JWT_SECRET=${JWT_SECRET:-openconstructionerp-secret-key}
RESEND_SECRET=${RESEND_SECRET:-resend-api-key}
REDIS_SECRET=${REDIS_SECRET:-benson-erp-redis-url}
GCS_BUCKET=${GCS_BUCKET:-benson-operations-private-uploads-1048944000089}
EMAIL_BACKEND=${EMAIL_BACKEND:-noop}

: "${IMAGE_DIGEST:?Set IMAGE_DIGEST to the exact candidate image digest}"
: "${SMOKE_REPORT:?Set SMOKE_REPORT to a passing candidate smoke JSON file}"
if [[ ! "$IMAGE_DIGEST" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "IMAGE_DIGEST must end in @sha256:<64 lowercase hex characters>." >&2
  exit 2
fi
if [[ "$EMAIL_BACKEND" != "noop" && "$EMAIL_BACKEND" != "resend" ]]; then
  echo "EMAIL_BACKEND must be noop or resend." >&2
  exit 2
fi
jq -e '.status == "pass"' "$SMOKE_REPORT" >/dev/null

for secret in "$DATABASE_SECRET" "$JWT_SECRET" "$RESEND_SECRET" "$REDIS_SECRET"; do
  gcloud secrets versions access latest --secret="$secret" --project="$PROJECT_ID" >/dev/null
done

common_env="APP_ENV=production,PYTHONPATH=/app/backend,OE_EDITION=benson,OE_SUPPORTED_LOCALES=en,OE_DEFAULT_LOCALE=en-US,OE_DEFAULT_REGION=benson_eastern_oregon,OE_PARTNER_PACK=benson-eastern-oregon,OE_STORAGE_BACKEND=gcs,OE_GCS_BUCKET=${GCS_BUCKET},OE_GCS_PROJECT=${PROJECT_ID},OE_EMAIL_BACKEND=${EMAIL_BACKEND},OE_RESEND_FROM=Benson Home Solutions <notifications@bensonhomesolutions.com>,OE_GOOGLE_DIRECTORY_ENABLED=false"
common_secrets="DATABASE_URL=${DATABASE_SECRET}:latest,OE_JWT_SECRET=${JWT_SECRET}:latest,OE_RESEND_API_KEY=${RESEND_SECRET}:latest,OE_REDIS_URL=${REDIS_SECRET}:latest,OE_CELERY_BROKER_URL=${REDIS_SECRET}:latest,OE_CELERY_RESULT_BACKEND=${REDIS_SECRET}:latest"
revision_suffix=${REVISION_SUFFIX:-benson-$(git rev-parse --short=10 HEAD)}

gcloud run worker-pools deploy "$WORKER_POOL" \
  --project="$PROJECT_ID" --region="$REGION" \
  --image="$IMAGE_DIGEST" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" \
  --network=default --subnet=default --vpc-egress=private-ranges-only \
  --set-secrets="$common_secrets" \
  --set-env-vars="$common_env" \
  --command=celery \
  --args=-A,app.modules.benson_workers.celery_app:celery_app,worker,--loglevel=info,--concurrency=2 \
  --cpu=2 --memory=2Gi --instances=1 \
  --revision-suffix="$revision_suffix" \
  --quiet

gcloud run worker-pools deploy "$SCHEDULER_POOL" \
  --project="$PROJECT_ID" --region="$REGION" \
  --image="$IMAGE_DIGEST" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" \
  --network=default --subnet=default --vpc-egress=private-ranges-only \
  --set-secrets="$common_secrets" \
  --set-env-vars="$common_env" \
  --command=celery \
  --args=-A,app.modules.benson_workers.celery_app:celery_app,beat,--loglevel=info \
  --cpu=1 --memory=1Gi --instances=1 \
  --revision-suffix="$revision_suffix" \
  --quiet

printf 'Worker pool: %s\nScheduler pool: %s\nImage: %s\nEmail backend: %s\n' \
  "$WORKER_POOL" "$SCHEDULER_POOL" "$IMAGE_DIGEST" "$EMAIL_BACKEND"
