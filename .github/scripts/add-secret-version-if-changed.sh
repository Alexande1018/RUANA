#!/usr/bin/env bash
# Add a Secret Manager version only when stdin differs from the latest enabled version.
# Secret payloads are written only to a private temporary directory and never logged.
set -euo pipefail
umask 077

if [[ $# -ne 2 ]]; then
  echo "Usage: add-secret-version-if-changed.sh SECRET_NAME PROJECT_ID" >&2
  exit 2
fi

SECRET_NAME="$1"
PROJECT_ID="$2"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
NEW_VALUE="$TMP_DIR/new-value"
CURRENT_VALUE="$TMP_DIR/current-value"
cat > "$NEW_VALUE"

if gcloud secrets versions access latest \
  --secret="$SECRET_NAME" \
  --project="$PROJECT_ID" > "$CURRENT_VALUE" 2>/dev/null; then
  if cmp -s "$NEW_VALUE" "$CURRENT_VALUE"; then
    echo "Sin cambios: no se añade una versión a ${SECRET_NAME}."
    exit 0
  fi
else
  # Do not turn a transient IAM/API failure into another billable version.
  # Adding is allowed only when the secret exists but has no enabled version.
  if ! ENABLED_VERSIONS="$(gcloud secrets versions list "$SECRET_NAME" \
    --project="$PROJECT_ID" \
    --filter="state=ENABLED" \
    --limit=1 \
    --format="value(name)")"; then
    echo "No se pudo comprobar el estado de ${SECRET_NAME}; se cancela sin publicar." >&2
    exit 1
  fi
  if [[ -n "$ENABLED_VERSIONS" ]]; then
    echo "No se pudo leer la versión actual de ${SECRET_NAME}; se cancela sin publicar." >&2
    exit 1
  fi
fi

gcloud secrets versions add "$SECRET_NAME" \
  --data-file="$NEW_VALUE" \
  --project="$PROJECT_ID" >/dev/null
echo "Versión actualizada en Secret Manager: ${SECRET_NAME}."
