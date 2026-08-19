#!/usr/bin/env bash
# Sube las credenciales admin (solo hashes) a Secret Manager y actualiza Cloud Run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CREDENTIALS_FILE="${RUANA_ADMIN_CREDENTIALS_PATH:-$ROOT/.local-secrets/admin_credentials.json}"
PROJECT_ID="${FIREBASE_PROJECT_ID:-ruana-4293f}"
REGION="${GOOGLE_CLOUD_REGION:-europe-west1}"
SERVICE="${RUANA_CLOUD_RUN_SERVICE:-ruana}"
SECRET_NAME="ruana-admin-credentials"
RUNTIME_SA="ruana-runner@${PROJECT_ID}.iam.gserviceaccount.com"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "Error: gcloud no está instalado. Instala Google Cloud SDK." >&2
  exit 1
fi

if [[ ! -f "$CREDENTIALS_FILE" ]]; then
  echo "Error: no se encontró $CREDENTIALS_FILE" >&2
  echo "Ejecuta antes: python RUANA/scripts/bootstrap_admin_credentials.py --legacy <archivo-legado.json>" >&2
  exit 1
fi

if ! jq -e '.admins | type == "object"' "$CREDENTIALS_FILE" >/dev/null 2>&1; then
  echo "Error: el archivo de credenciales no tiene el formato esperado." >&2
  exit 1
fi

echo "Proyecto: $PROJECT_ID"
gcloud config set project "$PROJECT_ID" >/dev/null

gcloud services enable secretmanager.googleapis.com run.googleapis.com --project "$PROJECT_ID" >/dev/null

if ! gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" \
    --replication-policy=automatic \
    --project "$PROJECT_ID"
  echo "Secreto creado: $SECRET_NAME"
fi

gcloud secrets versions add "$SECRET_NAME" \
  --data-file="$CREDENTIALS_FILE" \
  --project "$PROJECT_ID"

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretVersionAdder" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

echo "Secreto actualizado en Secret Manager."

if gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud run services update "$SERVICE" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --update-secrets "RUANA_ADMIN_CREDENTIALS_JSON=${SECRET_NAME}:latest"
  echo "Cloud Run actualizado: $SERVICE ($REGION)"
else
  echo "Aviso: el servicio $SERVICE no existe aún en $REGION."
  echo "En el próximo deploy se montará con --set-secrets RUANA_ADMIN_CREDENTIALS_JSON=${SECRET_NAME}:latest"
fi

echo "Listo. Login admin con identificador 7772735 y contraseña 7772735 (si no la cambiaste)."
