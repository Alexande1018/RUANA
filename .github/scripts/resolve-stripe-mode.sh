#!/usr/bin/env bash
# Resuelve RUANA_STRIPE_MODE para despliegue Cloud Run (B5).
# Prioridad: workflow_dispatch input > repo variable > default test.
# Bloquea live en push automático salvo vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true.
set -euo pipefail

EVENT_NAME="${1:-}"
INPUT_MODE="${2:-}"
VARS_MODE="${3:-}"
ALLOW_LIVE_PUSH="${RUANA_STRIPE_ALLOW_LIVE_PUSH:-}"

MODE=""
if [[ "$EVENT_NAME" == "workflow_dispatch" && -n "$INPUT_MODE" ]]; then
  MODE="$INPUT_MODE"
elif [[ -n "$VARS_MODE" ]]; then
  MODE="$VARS_MODE"
else
  MODE="test"
fi

MODE="${MODE,,}"
if [[ "$MODE" != "test" && "$MODE" != "live" ]]; then
  echo "::error::RUANA_STRIPE_MODE inválido: ${MODE} (debe ser test o live)"
  exit 1
fi

if [[ "$MODE" == "live" && "$EVENT_NAME" == "push" ]]; then
  if [[ "$ALLOW_LIVE_PUSH" != "true" && "$ALLOW_LIVE_PUSH" != "1" ]]; then
    echo "::error::Deploy LIVE en push automático bloqueado. Usa workflow_dispatch o define vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true."
    exit 1
  fi
fi

if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
  echo "mode=${MODE}"
else
  echo "mode=${MODE}" >> "$GITHUB_OUTPUT"
fi

echo "RUANA_STRIPE_MODE resuelto: ${MODE} (event=${EVENT_NAME})"
