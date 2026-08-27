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


def test_cloud_scheduler_doc_includes_four_jobs():
    content = SCHEDULER_DOC.read_text(encoding="utf-8")
    for needle in (
        "ruana-finalizar-competencias-vencidas",
        "ruana-purga-mensual",
        "ruana-motor-evaluacion-periodico",
        "ruana-financial-automation-cycle",
        "/api/admin/financial-automation/ejecutar-ciclo",
        "provision-cloud-scheduler-jobs.sh",
    ):
        assert needle in content


def test_provision_script_defines_financial_automation_job():
    content = PROVISION_SCRIPT.read_text(encoding="utf-8")
    assert "ruana-financial-automation-cycle" in content
    assert "ejecutar-ciclo" in content
    assert "X-Ruana-Cron-Secret" in content


def test_deploy_workflow_syncs_cron_secret_for_fase11():
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "sync-cron-secret-gcp.sh" in content
    assert "ruana-cron-secret" in content
    assert "RUANA_CRON_SECRET=ruana-cron-secret:latest" in content
