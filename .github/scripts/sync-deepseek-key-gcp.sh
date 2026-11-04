#!/usr/bin/env bash
# Sincroniza la clave de DeepSeek del Copiloto RUANA (GitHub Secret) → GCP Secret
# Manager. Invocado por deploy-firebase.yml; no requiere gcloud local.
#
# Si el GitHub Secret no existe, avisa y sale con 0: el despliegue sigue igual y
# el copiloto queda en modo determinista (sin IA generativa).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT requerido}"
SECRET_NAME="${RUANA_AI_GCP_SECRET_NAME:-ruana-deepseek-api-key}"
API_KEY="${RUANA_DEEPSEEK_API_KEY:-${RUANA_AI_API_KEY:-}}"

if [[ -z "$API_KEY" ]]; then
  echo "::warning::GitHub Secret RUANA_DEEPSEEK_API_KEY no configurado."
  echo "::warning::El Copiloto funcionará en modo determinista (sin modelo de lenguaje)."
  exit 0
fi

gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID" >/dev/null

if ! gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" \
    --replication-policy=automatic \
    --project "$PROJECT_ID"
  echo "Secreto GCP creado: $SECRET_NAME"
fi

printf '%s' "$API_KEY" | bash .github/scripts/add-secret-version-if-changed.sh \
  "$SECRET_NAME" "$PROJECT_ID"

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

echo "Clave de DeepSeek sincronizada en Secret Manager ($SECRET_NAME)."
