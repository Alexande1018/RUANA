"""Tests B6: FASE 11 + Cloud Scheduler (documentación y scripts de provisionamiento)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEDULER_DOC = ROOT / "docs" / "operaciones" / "cloud_scheduler_jobs.md"
PROVISION_SCRIPT = ROOT / ".github" / "scripts" / "provision-cloud-scheduler-jobs.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-firebase.yml"


def test_provision_scheduler_script_syntax():
    result = subprocess.run(["bash", "-n", str(PROVISION_SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_cloud_scheduler_doc_includes_five_jobs():
    content = SCHEDULER_DOC.read_text(encoding="utf-8")
    for needle in (
        "ruana-finalizar-competencias-vencidas",
        "ruana-purga-mensual",
        "ruana-motor-evaluacion-periodico",
        "ruana-financial-automation-cycle",
        "ruana-keepalive-health",
        "/api/admin/financial-automation/ejecutar-ciclo",
        "/api/health",
        "provision-cloud-scheduler-jobs.sh",
        "provision-keepalive-scheduler.sh",
    ):
        assert needle in content


def test_provision_script_defines_financial_automation_job():
    content = PROVISION_SCRIPT.read_text(encoding="utf-8")
    assert "ruana-financial-automation-cycle" in content
    assert "ejecutar-ciclo" in content
    assert "X-Ruana-Cron-Secret" in content
    assert "ruana-keepalive-health" in content
    assert "/api/health" in content


def test_keepalive_scheduler_script_syntax_and_contract():
    script = ROOT / ".github" / "scripts" / "provision-keepalive-scheduler.sh"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    content = script.read_text(encoding="utf-8")
    assert "ruana-keepalive-health" in content
    assert '*/10 * * * *' in content
    assert "/api/health" in content
    assert "--http-method=GET" in content
    assert "europe-west1" in content


def test_deploy_workflow_syncs_cron_secret_for_fase11():
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "sync-cron-secret-gcp.sh" in content
    assert "ruana-cron-secret" in content
    assert "RUANA_CRON_SECRET=ruana-cron-secret:latest" in content
