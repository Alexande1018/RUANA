#!/usr/bin/env bash
# Valida coherencia RUANA_STRIPE_MODE ↔ STRIPE_SECRET_KEY antes de desplegar (B5).
set -euo pipefail

MODE="${RUANA_STRIPE_MODE:-}"
KEY="${STRIPE_SECRET_KEY:-}"

MODE="${MODE,,}"
if [[ "$MODE" != "test" && "$MODE" != "live" ]]; then
  echo "::error::RUANA_STRIPE_MODE inválido: ${MODE:-<vacío>}"
  exit 1
fi

if [[ -z "$KEY" ]]; then
  echo "::error::STRIPE_SECRET_KEY no disponible; no se puede validar modo ${MODE}"
  exit 1
fi

if [[ "$MODE" == "test" && "$KEY" != sk_test_* ]]; then
  echo "::error::RUANA_STRIPE_MODE=test requiere STRIPE_SECRET_KEY con prefijo sk_test_"
  exit 1
fi

if [[ "$MODE" == "live" && "$KEY" != sk_live_* ]]; then
  echo "::error::RUANA_STRIPE_MODE=live requiere STRIPE_SECRET_KEY con prefijo sk_live_"
  exit 1
fi

echo "Validado: RUANA_STRIPE_MODE=${MODE} coherente con prefijo de STRIPE_SECRET_KEY."
