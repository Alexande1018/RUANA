#!/usr/bin/env bash
# Mantiene caliente el servicio Cloud Run "ruana" con GET /api/health cada 10 min.
# No usa min-instances. /api/health no toca BD ni requiere secreto cron.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
REGION="${GOOGLE_CLOUD_REGION:-europe-west1}"
CLOUD_RUN_URL="${CLOUD_RUN_URL:?CLOUD_RUN_URL requerido (sin barra final)}"
JOB_NAME="${KEEPALIVE_JOB_NAME:-ruana-keepalive-health}"

CLOUD_RUN_URL="${CLOUD_RUN_URL%/}"
URI="${CLOUD_RUN_URL}/api/health"

if gcloud scheduler jobs describe "$JOB_NAME" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB_NAME" \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --schedule="*/10 * * * *" \
    --time-zone="Etc/UTC" \
    --uri="$URI" \
    --http-method=GET \
    --attempt-deadline=30s
  echo "Actualizado job: ${JOB_NAME} -> ${URI}"
else
  gcloud scheduler jobs create http "$JOB_NAME" \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --schedule="*/10 * * * *" \
    --time-zone="Etc/UTC" \
    --uri="$URI" \
    --http-method=GET \
    --attempt-deadline=30s
  echo "Creado job: ${JOB_NAME} -> ${URI}"
fi
