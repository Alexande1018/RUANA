"""Validación CI/CD de ruana-cron-secret (FASE 14)."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "sync-cron-secret-gcp.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-firebase.yml"


def test_sync_cron_secret_script_syntax():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_deploy_workflow_references_cron_secret_sync():
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "sync-cron-secret-gcp.sh" in content
    assert "ruana-cron-secret" in content
    assert "RUANA_CRON_SECRET" in content
    assert "RUANA_SCHEDULER_SA=ruana-scheduler-invoker@ruana-4293f.iam.gserviceaccount.com" in content
    assert "CLOUD_RUN_URL" in content
    assert "HTTP 429" in content
    assert "--retry 8" not in content


def test_deploy_mantiene_stripe_mode_live():
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "RUANA_STRIPE_MODE=live" in content
    assert "RUANA_STRIPE_MODE=test" not in content
    assert "sync-stripe-secrets-gcp.sh" in content
    assert "secrets.STRIPE_SECRET_KEY" in content
    assert "secrets.STRIPE_PUBLISHABLE_KEY" in content
    assert "secrets.STRIPE_WEBHOOK_SECRET" in content


def test_sync_cron_secret_script_creates_bootstrap_path():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "SECRET_NAME=\"ruana-cron-secret\"" in content
    assert "openssl rand" in content
    assert "secretAccessor" in content
    assert "state=ENABLED" in content
    assert "no existe tras la sincronización" in content
