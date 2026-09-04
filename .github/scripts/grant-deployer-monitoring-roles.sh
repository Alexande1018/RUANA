#!/usr/bin/env bash
# Otorga a ruana-firebase-deployer los roles para crear métricas/alertas de Monitoring.
# Tras conceder roles en IAM, el workflow security-ops crea la alerta automáticamente.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
DEPLOYER_SA="${DEPLOYER_SA:-ruana-firebase-deployer@${PROJECT_ID}.iam.gserviceaccount.com}"
MEMBER="serviceAccount:${DEPLOYER_SA}"

grant_role() {
  local role="$1"
  echo "Concediendo ${role} a ${DEPLOYER_SA}..."
  if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$MEMBER" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null 2>&1; then
    echo "OK: ${role}"
    return 0
  fi
  # Idempotente: si ya existe el binding, get-iam-policy lo confirma.
  if gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[].members" \
    --filter="bindings.members:${MEMBER} AND bindings.role:${role}" \
    --format="value(bindings.role)" 2>/dev/null | grep -q "$role"; then
    echo "OK: ${role} (ya presente)"
    return 0
  fi
  echo "::error::No se pudo conceder ${role} a ${DEPLOYER_SA}"
  return 1
}

grant_role "roles/logging.configWriter"
grant_role "roles/monitoring.alertPolicyEditor"
echo "Roles de observabilidad listos para ${DEPLOYER_SA}"
