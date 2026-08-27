#!/usr/bin/env bash
# Provisiona (crea o actualiza) jobs HTTP de Cloud Scheduler para RUANA (FASE 11 / operaciones).
# Uso manual tras desplegar Cloud Run:
#   export PROJECT_ID=ruana-4293f
#   export CLOUD_RUN_URL=https://ruana-....run.app
#   export RUANA_CRON_SECRET=...
#   export SCHEDULER_OIDC_SERVICE_ACCOUNT=ruana-runner@....iam.gserviceaccount.com  # opcional
#   bash .github/scripts/provision-cloud-scheduler-jobs.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
REGION="${GOOGLE_CLOUD_REGION:-europe-west1}"
CLOUD_RUN_URL="${CLOUD_RUN_URL:?CLOUD_RUN_URL requerido (sin barra final)}"
CRON_SECRET="${RUANA_CRON_SECRET:?RUANA_CRON_SECRET requerido}"
OIDC_SA="${SCHEDULER_OIDC_SERVICE_ACCOUNT:-}"

CLOUD_RUN_URL="${CLOUD_RUN_URL%/}"
HEADER_ARGS=(--headers="X-Ruana-Cron-Secret=${CRON_SECRET}")
OIDC_ARGS=()
if [[ -n "$OIDC_SA" ]]; then
  OIDC_ARGS=(
    --oidc-service-account-email="$OIDC_SA"
    --oidc-token-audience="$CLOUD_RUN_URL"
  )
fi

upsert_http_job() {
  local name="$1"
  local schedule="$2"
  local uri="$3"
  local method="${4:-POST}"

  if gcloud scheduler jobs describe "$name" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$name" \
      --location="$REGION" \
      --project="$PROJECT_ID" \
      --schedule="$schedule" \
      --uri="$uri" \
      --http-method="$method" \
      "${HEADER_ARGS[@]}" \
      "${OIDC_ARGS[@]}"
    echo "Actualizado job: $name"
  else
    gcloud scheduler jobs create http "$name" \
      --location="$REGION" \
      --project="$PROJECT_ID" \
      --schedule="$schedule" \
      --uri="$uri" \
      --http-method="$method" \
      "${HEADER_ARGS[@]}" \
      "${OIDC_ARGS[@]}"
    echo "Creado job: $name"
  fi
}

upsert_http_job "ruana-finalizar-competencias-vencidas" "0 6 * * *" \
  "${CLOUD_RUN_URL}/api/competencia/finalizar-vencidas"

upsert_http_job "ruana-purga-mensual" "0 5 1 * *" \
  "${CLOUD_RUN_URL}/api/purga/mensual"

upsert_http_job "ruana-motor-evaluacion-periodico" "0 4 * * 1" \
  "${CLOUD_RUN_URL}/api/admin/motor/evaluar-periodico"

upsert_http_job "ruana-financial-automation-cycle" "0 */6 * * *" \
  "${CLOUD_RUN_URL}/api/admin/financial-automation/ejecutar-ciclo"

echo "Cloud Scheduler: 4 jobs sincronizados en ${REGION} (${PROJECT_ID})."
