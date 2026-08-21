#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LANDING="$ROOT/scripts/landing"
DB_PATH="${RUANA_LANDING_DB:-/tmp/ruana-landing.db}"
PORT="${RUANA_PORT:-5000}"
BASE="http://127.0.0.1:${PORT}"

export PYTHONPATH="$ROOT/RUANA"
export RUANA_ENV=dev
export FLASK_SECRET_KEY="landing-screenshots-secret-key-24"
export RUANA_DB_PATH="$DB_PATH"
export DATABASE_URL=""
export SUPABASE_URL=""
export SUPABASE_SERVICE_ROLE_KEY=""
export RUANA_ADMIN_CREDENTIALS_PATH="$LANDING/admin_credentials.landing.json"
export RUANA_ALLOW_LOCAL_UPLOADS=1
export RUANA_STRIPE_PAYMENTS_ENABLED=0
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export RUANA_LANDING_DB="$DB_PATH"
export RUANA_BASE_URL="$BASE"

echo "[landing] sembrando datos de demostración…"
python3 "$LANDING/seed_landing_demo.py"

echo "[landing] arrancando Flask en :${PORT}…"
cd "$ROOT/RUANA"
python3 -m flask --app web.app run --host 127.0.0.1 --port "$PORT" >/tmp/ruana-landing-flask.log 2>&1 &
FLASK_PID=$!
trap 'kill "$FLASK_PID" 2>/dev/null || true' EXIT

for i in $(seq 1 40); do
  if curl -sf "$BASE/" >/dev/null; then
    break
  fi
  if ! kill -0 "$FLASK_PID" 2>/dev/null; then
    echo "[landing] Flask no arrancó:"
    cat /tmp/ruana-landing-flask.log
    exit 1
  fi
  sleep 0.4
done

curl -sf "$BASE/" >/dev/null
echo "[landing] capturando pantallas…"
cd "$ROOT"
node "$LANDING/capture_landing_screenshots.js"
echo "[landing] listo"
