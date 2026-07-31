#!/usr/bin/env bash
# Sincroniza RUANA_SMTP_PASSWORD (GitHub Secret) → GCP Secret Manager.
# Invocado por deploy-firebase.yml; no requiere gcloud local.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT requerido}"
SECRET_NAME="${RUANA_SMTP_GCP_SECRET_NAME:-ruana-smtp-password}"
SMTP_PASSWORD="${SMTP_PASSWORD:-${RUANA_SMTP_PASSWORD:-}}"

if [[ -z "$SMTP_PASSWORD" ]]; then
  echo "::warning::GitHub Secret RUANA_SMTP_PASSWORD no configurado."
  echo "::warning::El correo de bienvenida al registrarse no se enviará en producción hasta añadirlo."
  exit 0
fi

gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID" >/dev/null

if ! gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" \
    --replication-policy=automatic \
    --project "$PROJECT_ID"
  echo "Secreto GCP creado: $SECRET_NAME"
fi

printf '%s' "$SMTP_PASSWORD" | gcloud secrets versions add "$SECRET_NAME" \
  --data-file=- \
  --project "$PROJECT_ID"

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

echo "Contraseña SMTP sincronizada en Secret Manager ($SECRET_NAME)."
