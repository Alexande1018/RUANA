#!/usr/bin/env bash
# Sincroniza RUANA_CRON_SECRET (GitHub Secret) → GCP Secret Manager + IAM runtime.
# Si falta en GitHub y en GCP, genera un valor bootstrap en Secret Manager.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT requerido}"
SECRET_NAME="ruana-cron-secret"
CRON_SECRET="${RUANA_CRON_SECRET:-}"

gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID" >/dev/null

secret_exists=false
if gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  secret_exists=true
fi

if [[ -n "$CRON_SECRET" ]]; then
  if [[ "$secret_exists" == false ]]; then
    gcloud secrets create "$SECRET_NAME" \
      --replication-policy=automatic \
      --project "$PROJECT_ID"
    secret_exists=true
    echo "Secreto GCP creado: $SECRET_NAME"
  fi
  printf '%s' "$CRON_SECRET" | gcloud secrets versions add "$SECRET_NAME" \
    --data-file=- \
    --project "$PROJECT_ID"
  echo "RUANA_CRON_SECRET sincronizado desde GitHub Secret."
elif [[ "$secret_exists" == false ]]; then
  CRON_SECRET="$(openssl rand -base64 32)"
  gcloud secrets create "$SECRET_NAME" \
    --replication-policy=automatic \
    --project "$PROJECT_ID"
  printf '%s' "$CRON_SECRET" | gcloud secrets versions add "$SECRET_NAME" \
    --data-file=- \
    --project "$PROJECT_ID"
  echo "::warning::RUANA_CRON_SECRET generado en GCP (bootstrap). Añade el mismo valor a GitHub Secrets y Cloud Scheduler."
else
  echo "::warning::GitHub Secret RUANA_CRON_SECRET no configurado; se reutiliza la versión existente en GCP."
fi

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

echo "IAM secretAccessor concedido a ${RUNTIME_SERVICE_ACCOUNT} en ${SECRET_NAME}."
