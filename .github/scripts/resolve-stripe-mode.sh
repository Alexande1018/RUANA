#!/usr/bin/env bash
# Resuelve RUANA_STRIPE_MODE para despliegue Cloud Run (B5).
# Prioridad: workflow_dispatch input > repo variable > prefijo de STRIPE_SECRET_KEY > default test.
# Live en push automático: permitido si vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true o la clave es sk_live_.
set -euo pipefail

EVENT_NAME="${1:-}"
INPUT_MODE="${2:-}"
VARS_MODE="${3:-}"
ALLOW_LIVE_PUSH="${RUANA_STRIPE_ALLOW_LIVE_PUSH:-}"
SECRET_KEY="${STRIPE_SECRET_KEY:-}"

infer_from_key() {
  local key="$1"
  if [[ "$key" == sk_live_* ]]; then
    echo "live"
  elif [[ "$key" == sk_test_* ]]; then
    echo "test"
  else
    echo ""
  fi
}

MODE=""
if [[ "$EVENT_NAME" == "workflow_dispatch" && -n "$INPUT_MODE" ]]; then
  MODE="$INPUT_MODE"
elif [[ -n "$VARS_MODE" ]]; then
  MODE="$VARS_MODE"
else
  MODE="$(infer_from_key "$SECRET_KEY")"
  if [[ -z "$MODE" ]]; then
    MODE="test"
  fi
fi

MODE="${MODE,,}"
if [[ "$MODE" != "test" && "$MODE" != "live" ]]; then
  echo "::error::RUANA_STRIPE_MODE inválido: ${MODE} (debe ser test o live)"
  exit 1
fi

if [[ "$MODE" == "live" && "$EVENT_NAME" == "push" ]]; then
  if [[ "$ALLOW_LIVE_PUSH" != "true" && "$ALLOW_LIVE_PUSH" != "1" && "$SECRET_KEY" != sk_live_* ]]; then
    echo "::error::Deploy LIVE en push automático bloqueado. Usa workflow_dispatch, vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true o una STRIPE_SECRET_KEY sk_live_."
    exit 1
  fi
fi

if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
  echo "mode=${MODE}"
else
  echo "mode=${MODE}" >> "$GITHUB_OUTPUT"
fi

echo "RUANA_STRIPE_MODE resuelto: ${MODE} (event=${EVENT_NAME})"
