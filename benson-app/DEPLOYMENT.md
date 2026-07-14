# Benson Operations production deployment

The replacement ERP deploys as the `benson-operations` Cloud Run service. Do not point website traffic at the legacy `openconstructionerp` service.

## Required infrastructure

- Cloud SQL PostgreSQL database and a least-privilege application user
- private Google Cloud Storage bucket with uniform bucket-level access, public access prevention, retention/versioning appropriate for customer files, and no website CORS requirement
- Google Workspace OAuth web client for `erp.bensonhomesolutions.com`
- dedicated Cloud Run service account with Cloud SQL Client, access to only the required Secret Manager values, and object create/read permission on the one upload bucket
- Secret Manager values for `BENSON_DATABASE_URL`, `BENSON_WEBSITE_SIGNING_SECRET`, and `BENSON_FCC_AUTH_TOKEN`

Provision a new, empty Benson Operations database. `metadata.create_all()` bootstraps the first schema but does not migrate the legacy OpenConstructionERP or preview SQLite schema. Import legacy records only through a separately reviewed, reconciliation-tested ETL; never point this service at an old database in place.

Build from this directory:

```bash
gcloud builds submit --project civic-wall-494004-b3 --config cloudbuild.yaml .
```

Deploy a no-traffic revision first. Replace the resource names below with the provisioned values:

```bash
gcloud run deploy benson-operations \
  --image us-west1-docker.pkg.dev/civic-wall-494004-b3/cloud-run-source-deploy/benson-operations:latest \
  --region us-west1 \
  --project civic-wall-494004-b3 \
  --service-account benson-operations@civic-wall-494004-b3.iam.gserviceaccount.com \
  --add-cloudsql-instances civic-wall-494004-b3:us-west1:benson-operations-postgres \
  --set-secrets BENSON_DATABASE_URL=benson-operations-database-url:latest,BENSON_WEBSITE_SIGNING_SECRET=benson-erp-website-signing-secret:latest,BENSON_FCC_AUTH_TOKEN=benson-fcc-auth-token:latest \
  --set-env-vars BENSON_ENVIRONMENT=production,BENSON_STAFF_GOOGLE_AUDIENCE=REPLACE_ME.apps.googleusercontent.com,BENSON_STAFF_GOOGLE_DOMAIN=bensonhomesolutions.com,BENSON_OWNER_EMAILS=office@bensonhomesolutions.com,BENSON_UPLOAD_BUCKET=benson-operations-private-uploads,BENSON_UPLOAD_BASE_URL=https://erp.bensonhomesolutions.com,BENSON_FCC_BASE_URL=https://REPLACE_WITH_REACHABLE_FREE_CLAUDE_CODE_GATEWAY \
  --memory 1Gi --cpu 1 --timeout 300 --no-traffic
```

Before shifting traffic, verify `/api/health`, Google sign-in, a signed synthetic lead, idempotent replay, the lead queue, an image upload, and audit rows. Only then update the website secret/config, deploy the website, submit every public form once, and confirm each record in Benson Operations. Retain the legacy service for rollback without sending new leads to it.
