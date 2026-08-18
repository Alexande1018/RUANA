#!/usr/bin/env bash
# Sincroniza RUANA_CRON_SECRET (GitHub Secret) → GCP Secret Manager + IAM runtime.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT requerido}"
SECRET_NAME="ruana-cron-secret"
CRON_SECRET="${RUANA_CRON_SECRET:-}"

gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID" >/dev/null

if [[ -n "$CRON_SECRET" ]]; then
  if ! gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$SECRET_NAME" \
      --replication-policy=automatic \
      --project "$PROJECT_ID"
    echo "Secreto GCP creado: $SECRET_NAME"
  fi

  printf '%s' "$CRON_SECRET" | gcloud secrets versions add "$SECRET_NAME" \
    --data-file=- \
    --project "$PROJECT_ID"

  echo "RUANA_CRON_SECRET sincronizado en Secret Manager ($SECRET_NAME)."
elif ! gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "::error::GitHub Secret RUANA_CRON_SECRET no configurado y el secreto GCP no existe."
  exit 1
else
  echo "::warning::GitHub Secret RUANA_CRON_SECRET no configurado; se reutiliza la versión existente en GCP."
fi

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

echo "IAM secretAccessor concedido a ${RUNTIME_SERVICE_ACCOUNT} en ${SECRET_NAME}."
