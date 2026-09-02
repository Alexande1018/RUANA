#!/usr/bin/env bash
# Métrica de log + alerta Cloud Monitoring para fallos de init Postgres.
# Se ejecuta en el deploy de producción (gcloud ya autenticado).
# Requiere en la SA de deploy (ruana-firebase-deployer):
#   roles/logging.configWriter
#   roles/monitoring.alertPolicyEditor
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

if gcloud logging metrics describe "$METRIC_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  if ! gcloud logging metrics update "$METRIC_NAME" \
    --project="$PROJECT_ID" \
    --description="Init de esquema Postgres abortado (sqlite_master / migraciones)." \
    --log-filter="$FILTER"; then
    iam_hint
    exit 1
  fi
  echo "Métrica de log actualizada: $METRIC_NAME"
else
  if ! gcloud logging metrics create "$METRIC_NAME" \
    --project="$PROJECT_ID" \
    --description="Init de esquema Postgres abortado (sqlite_master / migraciones)." \
    --log-filter="$FILTER"; then
    iam_hint
    exit 1
  fi
  echo "Métrica de log creada: $METRIC_NAME"
fi

EXISTING="$(gcloud alpha monitoring policies list \
  --project="$PROJECT_ID" \
  --filter="displayName=\"${DISPLAY_NAME}\"" \
  --format="value(name)" 2>/dev/null | head -n 1 || true)"

if [[ -n "$EXISTING" ]]; then
  if ! gcloud alpha monitoring policies update "$EXISTING" \
    --project="$PROJECT_ID" \
    --policy-from-file="$POLICY_FILE"; then
    iam_hint
    exit 1
  fi
  echo "Alerta actualizada: $EXISTING"
else
  if ! gcloud alpha monitoring policies create \
    --project="$PROJECT_ID" \
    --policy-from-file="$POLICY_FILE"; then
    iam_hint
    exit 1
  fi
  echo "Alerta creada: $DISPLAY_NAME"
fi
