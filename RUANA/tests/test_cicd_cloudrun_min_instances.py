"""Producción Cloud Run: 1 instancia caliente en el deploy que publica `ruana`."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-firebase.yml"
PREVIEW_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-firebase-preview.yml"
DEPLOY_PS1 = ROOT / "scripts" / "deploy_cloudrun.ps1"
DOCKERFILE = ROOT / "Dockerfile"


def _deploy_step(content: str) -> str:
    idx = content.index("gcloud run deploy")
    return content[idx : idx + 900]


def test_production_workflow_keeps_one_warm_instance():
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "SERVICE: ruana" in content
    step = _deploy_step(content)
    assert "--min-instances 1" in step
    assert "--max-instances 3" in step
    assert "--no-cpu-throttling" not in step


def test_manual_cloudrun_script_keeps_one_warm_instance():
    content = DEPLOY_PS1.read_text(encoding="utf-8")
    assert '"--min-instances", "1"' in content
    assert '"--max-instances", "3"' in content
    assert "--no-cpu-throttling" not in content
    assert '$service = "ruana"' in content


def test_preview_workflow_does_not_pay_for_min_instances():
    """Preview puede escalar a cero; el coste fijo solo aplica a producción `ruana`."""
    content = PREVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert "SERVICE: ruana-preview" in content
    step = _deploy_step(content)
    assert "--min-instances" not in step
    assert "--no-cpu-throttling" not in step
    assert "--max-instances 3" in step


def test_gunicorn_timeout_covers_cold_aliado_datos():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "GUNICORN_TIMEOUT:-60" in dockerfile
    assert "GUNICORN_TIMEOUT:-30" not in dockerfile
