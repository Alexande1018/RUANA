#!/usr/bin/env bash
# Sincroniza claves Stripe (GitHub Secrets) → GCP Secret Manager.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID requerido}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT requerido}"

sync_one_secret() {
  local github_value="$1"
  local gcp_name="$2"
  local label="$3"

  if [[ -z "$github_value" ]]; then
    echo "::warning::GitHub Secret ${label} no configurado; Stripe puede quedar inactivo."
    return 0
  fi

  gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID" >/dev/null

  if ! gcloud secrets describe "$gcp_name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$gcp_name" \
      --replication-policy=automatic \
      --project "$PROJECT_ID"
    echo "Secreto GCP creado: $gcp_name"
  fi

  printf '%s' "$github_value" | gcloud secrets versions add "$gcp_name" \
    --data-file=- \
    --project "$PROJECT_ID"

  gcloud secrets add-iam-policy-binding "$gcp_name" \
    --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project "$PROJECT_ID" \
    --quiet >/dev/null

  echo "Stripe ${label} sincronizado en Secret Manager ($gcp_name)."
}

sync_one_secret "${STRIPE_SECRET_KEY:-}" "ruana-stripe-secret-key" "STRIPE_SECRET_KEY"
sync_one_secret "${STRIPE_PUBLISHABLE_KEY:-}" "ruana-stripe-publishable-key" "STRIPE_PUBLISHABLE_KEY"
sync_one_secret "${STRIPE_WEBHOOK_SECRET:-}" "ruana-stripe-webhook-secret" "STRIPE_WEBHOOK_SECRET"
