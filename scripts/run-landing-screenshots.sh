#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export FLASK_SECRET_KEY="${FLASK_SECRET_KEY:-ruana_landing_screenshot_secret_32}"
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export RUANA_DB_PATH="${RUANA_DB_PATH:-$ROOT/qa-artifacts/ruana-landing-demo.db}"
export RUANA_ADMIN_CREDENTIALS_PATH="${RUANA_ADMIN_CREDENTIALS_PATH:-$ROOT/RUANA/config/admin_credentials.qa.json}"
export RUANA_ALLOW_LOCAL_UPLOADS=1
export DATABASE_URL=""
export SUPABASE_URL=""
export SUPABASE_SERVICE_ROLE_KEY=""
export RUANA_BASE_URL="${RUANA_BASE_URL:-http://127.0.0.1:5000}"

mkdir -p qa-artifacts /opt/cursor/artifacts/screenshots/landing
rm -f "$RUANA_DB_PATH"

SESSION="ruana-landing-server"
TMUX=(tmux -f /exec-daemon/tmux.portal.conf)

if ! "${TMUX[@]}" has-session -t "=$SESSION" 2>/dev/null; then
  "${TMUX[@]}" new-session -d -s "$SESSION" -c "$ROOT" -- "${SHELL:-bash}" -l
fi

"${TMUX[@]}" send-keys -t "$SESSION:0.0" "cd $ROOT && python3 RUANA/web/run.py" C-m

echo "Esperando servidor..."
for i in $(seq 1 40); do
  if curl -sf "$RUANA_BASE_URL/api/health" >/dev/null 2>&1; then
    echo "Servidor listo."
    break
  fi
  sleep 1
  if [ "$i" -eq 40 ]; then
    echo "Timeout esperando servidor"
    exit 1
  fi
done

node scripts/seed-landing-demo.js
node scripts/capture-landing-screenshots.js

echo "Listo: /opt/cursor/artifacts/screenshots/landing"
