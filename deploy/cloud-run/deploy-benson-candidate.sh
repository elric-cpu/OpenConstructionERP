#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT_DIR"

PROJECT_ID=${PROJECT_ID:-civic-wall-494004-b3}
REGION=${REGION:-us-west1}
SERVICE=${SERVICE:-benson-operations}
RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SERVICE_ACCOUNT:-benson-operations@${PROJECT_ID}.iam.gserviceaccount.com}
CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE:-${PROJECT_ID}:${REGION}:benson-openconstructionerp-postgres}
DATABASE_SECRET=${DATABASE_SECRET:-benson-erp-v2-database-url}
JWT_SECRET=${JWT_SECRET:-openconstructionerp-secret-key}
RESEND_SECRET=${RESEND_SECRET:-resend-api-key}
REDIS_SECRET=${REDIS_SECRET:-benson-erp-redis-url}
GCS_BUCKET=${GCS_BUCKET:-benson-operations-private-uploads-1048944000089}
VPC_CONNECTOR=${VPC_CONNECTOR:-benson-serverless}
CANDIDATE_TAG=${CANDIDATE_TAG:-benson-candidate}
EMAIL_BACKEND=${EMAIL_BACKEND:-noop}
PARITY_REPORT=${PARITY_REPORT:-artifacts/benson-parity.json}
RELEASE_DIR=${RELEASE_DIR:-artifacts/releases}
BASELINE_COMMIT=19bd8e0856b549e40472e2b57a6c82b8a0722a73

: "${IMAGE_DIGEST:?Set IMAGE_DIGEST to an immutable Artifact Registry image ending in @sha256:<digest>}"
: "${CI_RUN_URL:?Set CI_RUN_URL to the green CI run for the exact commit}"

if [[ ! "$IMAGE_DIGEST" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "IMAGE_DIGEST must be an immutable image reference ending in @sha256:<64 lowercase hex characters>." >&2
  exit 2
fi
if [[ "$EMAIL_BACKEND" != "noop" && "$EMAIL_BACKEND" != "resend" ]]; then
  echo "EMAIL_BACKEND must be noop or resend." >&2
  exit 2
fi
if [[ -n $(git status --porcelain) ]]; then
  echo "Candidate deployment requires a clean worktree." >&2
  exit 2
fi
git merge-base --is-ancestor "$BASELINE_COMMIT" HEAD
jq -e '.status == "pass" and .tracked_paths.missing == 0 and (.failures | length) == 0' "$PARITY_REPORT" >/dev/null
python scripts/check_benson_artifact.py frontend/dist

for secret in "$DATABASE_SECRET" "$JWT_SECRET" "$RESEND_SECRET" "$REDIS_SECRET"; do
  gcloud secrets versions access latest --secret="$secret" --project="$PROJECT_ID" >/dev/null
done
gcloud artifacts docker images describe "$IMAGE_DIGEST" --project="$PROJECT_ID" >/dev/null

commit=$(git rev-parse HEAD)
short_commit=$(git rev-parse --short=10 HEAD)
revision_suffix=${REVISION_SUFFIX:-benson-${short_commit}}
rollback_revision=$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format=json |
    jq -r '.status.traffic[] | select(.percent == 100) | .revisionName' |
    head -n1
)

gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --platform=managed \
  --image="$IMAGE_DIGEST" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" \
  --set-secrets="DATABASE_URL=${DATABASE_SECRET}:latest,OE_JWT_SECRET=${JWT_SECRET}:latest,OE_RESEND_API_KEY=${RESEND_SECRET}:latest,OE_REDIS_URL=${REDIS_SECRET}:latest,OE_CELERY_BROKER_URL=${REDIS_SECRET}:latest,OE_CELERY_RESULT_BACKEND=${REDIS_SECRET}:latest" \
  --set-env-vars="APP_ENV=production,SERVE_FRONTEND=true,ALLOWED_ORIGINS=https://erp.bensonhomesolutions.com,OE_EDITION=benson,OE_SUPPORTED_LOCALES=en,OE_DEFAULT_LOCALE=en-US,OE_DEFAULT_REGION=benson_eastern_oregon,OE_PARTNER_PACK=benson-eastern-oregon,OE_STORAGE_BACKEND=gcs,OE_GCS_BUCKET=${GCS_BUCKET},OE_GCS_PROJECT=${PROJECT_ID},OE_EMAIL_BACKEND=${EMAIL_BACKEND},OE_RESEND_FROM=Benson Home Solutions <notifications@bensonhomesolutions.com>,OE_GOOGLE_DIRECTORY_ENABLED=false" \
  --revision-suffix="$revision_suffix" \
  --tag="$CANDIDATE_TAG" \
  --no-traffic \
  --vpc-connector="$VPC_CONNECTOR" \
  --vpc-egress=private-ranges-only \
  --port=8080 \
  --cpu=2 \
  --memory=4Gi \
  --concurrency=20 \
  --timeout=900 \
  --min=0 \
  --max=4 \
  --quiet

candidate_revision=$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format='value(status.latestCreatedRevisionName)'
)
candidate_url=$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format=json |
    jq -r --arg tag "$CANDIDATE_TAG" '.status.traffic[] | select(.tag == $tag) | .url'
)

mkdir -p "$RELEASE_DIR"
evidence="$RELEASE_DIR/${candidate_revision}.json"
jq -n \
  --arg status "candidate_deployed" \
  --arg commit "$commit" \
  --arg baseline_commit "$BASELINE_COMMIT" \
  --arg image_digest "$IMAGE_DIGEST" \
  --arg ci_run_url "$CI_RUN_URL" \
  --arg parity_report "$PARITY_REPORT" \
  --arg service "$SERVICE" \
  --arg region "$REGION" \
  --arg candidate_revision "$candidate_revision" \
  --arg candidate_url "$candidate_url" \
  --arg rollback_revision "$rollback_revision" \
  --arg email_backend "$EMAIL_BACKEND" \
  --arg redis_secret "$REDIS_SECRET" \
  --arg gcs_bucket "$GCS_BUCKET" \
  --arg deployed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{status: $status, commit: $commit, baseline_commit: $baseline_commit, image_digest: $image_digest, ci_run_url: $ci_run_url, parity_report: $parity_report, service: $service, region: $region, candidate_revision: $candidate_revision, candidate_url: $candidate_url, rollback_revision: $rollback_revision, email_backend: $email_backend, redis_secret: $redis_secret, gcs_bucket: $gcs_bucket, google_directory_enabled: false, traffic_percent: 0, deployed_at: $deployed_at}' \
  >"$evidence"

printf 'Candidate revision: %s\nCandidate URL: %s\nRollback revision: %s\nEvidence: %s\n' \
  "$candidate_revision" "$candidate_url" "$rollback_revision" "$evidence"
