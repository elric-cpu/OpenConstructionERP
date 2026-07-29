#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:-civic-wall-494004-b3}
REGION=${REGION:-us-west1}
JOB=${JOB:-benson-erp-v2-migrate}
RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SERVICE_ACCOUNT:-benson-operations@${PROJECT_ID}.iam.gserviceaccount.com}
CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE:-${PROJECT_ID}:${REGION}:benson-openconstructionerp-postgres}
DATABASE_SECRET=${DATABASE_SECRET:-benson-erp-v2-database-url}

: "${IMAGE_DIGEST:?Set IMAGE_DIGEST to the exact candidate image digest}"
if [[ ! "$IMAGE_DIGEST" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "IMAGE_DIGEST must end in @sha256:<64 lowercase hex characters>." >&2
  exit 2
fi

gcloud secrets versions access latest --secret="$DATABASE_SECRET" --project="$PROJECT_ID" >/dev/null
gcloud run jobs deploy "$JOB" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE_DIGEST" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" \
  --set-secrets="DATABASE_URL=${DATABASE_SECRET}:latest" \
  --set-env-vars="PYTHONPATH=/app/backend,APP_ENV=production" \
  --command=alembic \
  --args=-c,/app/backend/alembic.ini,upgrade,head \
  --max-retries=0 \
  --task-timeout=30m \
  --quiet

gcloud run jobs execute "$JOB" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --wait
