#!/usr/bin/env bash
# Métrica de log + alerta Cloud Monitoring para fallos de init Postgres.
# Se ejecuta en el deploy de producción (gcloud ya autenticado).
# Requiere en la SA de deploy (ruana-firebase-deployer):
#   roles/logging.configWriter
#   roles/monitoring.alertPolicyEditor
# Si faltan permisos IAM, el script avisa y termina en 0 para no bloquear el deploy.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
METRIC_NAME="ruana_postgres_schema_init_failed"
FILTER='resource.type="cloud_run_revision" AND resource.labels.service_name="ruana" AND (textPayload:"ruana_postgres_schema_init_failed" OR jsonPayload.event="ruana_postgres_schema_init_failed")'
POLICY_FILE="${POLICY_FILE:-infra/monitoring/ruana-postgres-schema-init-alert.json}"
DISPLAY_NAME="RUANA: fallo init esquema Postgres"

iam_hint() {
  echo "::error::Falta permiso GCP para crear métrica/alerta de init Postgres."
  echo "::error::Añadir a ruana-firebase-deployer@${PROJECT_ID}.iam.gserviceaccount.com:"
  echo "::error::  roles/logging.configWriter      (logging.logMetrics.create)"
  echo "::error::  roles/monitoring.alertPolicyEditor (monitoring.alertPolicies.create)"
}

is_iam_denied() {
  local err_file="$1"
  grep -qE 'IAM_PERMISSION_DENIED|Permission .+ denied' "$err_file"
}

run_gcloud_or_warn() {
  local err
  err="$(mktemp)"
  if ! "$@" 2>"$err"; then
    if is_iam_denied "$err"; then
      cat "$err" >&2
      iam_hint
      echo "::warning::Deploy continúa sin métrica/alerta de init Postgres hasta conceder los roles IAM anteriores."
      exit 0
    fi
    cat "$err" >&2
    return 1
  fi
  rm -f "$err"
}

if gcloud logging metrics describe "$METRIC_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  run_gcloud_or_warn gcloud logging metrics update "$METRIC_NAME" \
    --project="$PROJECT_ID" \
    --description="Init de esquema Postgres abortado (sqlite_master / migraciones)." \
    --log-filter="$FILTER"
  echo "Métrica de log actualizada: $METRIC_NAME"
else
  run_gcloud_or_warn gcloud logging metrics create "$METRIC_NAME" \
    --project="$PROJECT_ID" \
    --description="Init de esquema Postgres abortado (sqlite_master / migraciones)." \
    --log-filter="$FILTER"
  echo "Métrica de log creada: $METRIC_NAME"
fi

EXISTING="$(gcloud alpha monitoring policies list \
  --project="$PROJECT_ID" \
  --filter="displayName=\"${DISPLAY_NAME}\"" \
  --format="value(name)" 2>/dev/null | head -n 1 || true)"

if [[ -n "$EXISTING" ]]; then
  run_gcloud_or_warn gcloud alpha monitoring policies update "$EXISTING" \
    --project="$PROJECT_ID" \
    --policy-from-file="$POLICY_FILE"
  echo "Alerta actualizada: $EXISTING"
else
  run_gcloud_or_warn gcloud alpha monitoring policies create \
    --project="$PROJECT_ID" \
    --policy-from-file="$POLICY_FILE"
  echo "Alerta creada: $DISPLAY_NAME"
fi
