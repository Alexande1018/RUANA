#!/usr/bin/env bash
# Sincroniza RUANA_ADMIN_CREDENTIALS_JSON (GitHub Secret) → GCP Secret Manager.
# Invocado por deploy-firebase.yml; no requiere gcloud local.
#
# El secreto en GCP es la fuente de verdad en runtime: el panel puede añadir
# versiones al cambiar la contraseña. Por eso este script NO sobrescribe un
# secreto ya existente salvo FORCE_ADMIN_CREDENTIALS_SYNC=true.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT requerido}"
SECRET_NAME="${RUANA_ADMIN_GCP_SECRET_NAME:-ruana-admin-credentials}"
CREDENTIALS_JSON="${ADMIN_CREDENTIALS_JSON:-${RUANA_ADMIN_CREDENTIALS_JSON:-}}"
FORCE_SYNC="${FORCE_ADMIN_CREDENTIALS_SYNC:-false}"

grant_runtime_iam() {
  gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
    --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project "$PROJECT_ID" \
    --quiet >/dev/null

  gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
    --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretVersionAdder" \
    --project "$PROJECT_ID" \
    --quiet >/dev/null
}

if [[ -z "$CREDENTIALS_JSON" ]]; then
  echo "::warning::GitHub Secret RUANA_ADMIN_CREDENTIALS_JSON no configurado."
  echo "::warning::El panel /admin en producción no autenticará hasta añadirlo (ver docs/seguridad/credenciales-admin.md)."
  exit 0
fi

if ! printf '%s' "$CREDENTIALS_JSON" | jq -e '.version and (.admins | type == "object")' >/dev/null 2>&1; then
  echo "::error::RUANA_ADMIN_CREDENTIALS_JSON no es un JSON válido de credenciales admin."
  exit 1
fi

gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID" >/dev/null

secret_exists=false
if gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  secret_exists=true
fi

if [[ "$secret_exists" == false ]]; then
  gcloud secrets create "$SECRET_NAME" \
    --replication-policy=automatic \
    --project "$PROJECT_ID"
  echo "Secreto GCP creado: $SECRET_NAME"
  printf '%s' "$CREDENTIALS_JSON" | gcloud secrets versions add "$SECRET_NAME" \
    --data-file=- \
    --project "$PROJECT_ID"
  echo "Credenciales admin bootstrap en Secret Manager ($SECRET_NAME)."
elif [[ "$FORCE_SYNC" == "true" || "$FORCE_SYNC" == "1" ]]; then
  printf '%s' "$CREDENTIALS_JSON" | gcloud secrets versions add "$SECRET_NAME" \
    --data-file=- \
    --project "$PROJECT_ID"
  echo "Credenciales admin sobrescritas en Secret Manager ($SECRET_NAME) por FORCE_ADMIN_CREDENTIALS_SYNC."
else
  echo "Secreto $SECRET_NAME ya existe; no se sobrescribe (el panel puede haber rotado la contraseña)."
  echo "Para forzar el JSON de GitHub: FORCE_ADMIN_CREDENTIALS_SYNC=true"
fi

grant_runtime_iam
echo "IAM secretAccessor + secretVersionAdder concedido a ${RUNTIME_SERVICE_ACCOUNT} en ${SECRET_NAME}."
