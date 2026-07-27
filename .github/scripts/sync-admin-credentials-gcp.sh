#!/usr/bin/env bash
# Sincroniza RUANA_ADMIN_CREDENTIALS_JSON (GitHub Secret) → GCP Secret Manager.
# Invocado por deploy-firebase.yml; no requiere gcloud local.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT requerido}"
SECRET_NAME="${RUANA_ADMIN_GCP_SECRET_NAME:-ruana-admin-credentials}"
CREDENTIALS_JSON="${ADMIN_CREDENTIALS_JSON:-${RUANA_ADMIN_CREDENTIALS_JSON:-}}"

if [[ -z "$CREDENTIALS_JSON" ]]; then
  echo "::warning::GitHub Secret RUANA_ADMIN_CREDENTIALS_JSON no configurado."
  echo "::warning::El panel /admin en producción no autenticará hasta añadirlo (ver docs/ADMIN_CREDENTIALS_SETUP.md)."
  exit 0
fi

if ! printf '%s' "$CREDENTIALS_JSON" | jq -e '.version and (.admins | type == "object")' >/dev/null 2>&1; then
  echo "::error::RUANA_ADMIN_CREDENTIALS_JSON no es un JSON válido de credenciales admin."
  exit 1
fi

gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID" >/dev/null

if ! gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" \
    --replication-policy=automatic \
    --project "$PROJECT_ID"
  echo "Secreto GCP creado: $SECRET_NAME"
fi

printf '%s' "$CREDENTIALS_JSON" | gcloud secrets versions add "$SECRET_NAME" \
  --data-file=- \
  --project "$PROJECT_ID"

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

echo "Credenciales admin sincronizadas en Secret Manager ($SECRET_NAME)."
