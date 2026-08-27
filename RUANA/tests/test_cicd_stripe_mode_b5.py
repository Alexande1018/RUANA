"""Tests CI/CD B5: resolución y validación de RUANA_STRIPE_MODE sin hardcode."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-firebase.yml"
PREVIEW_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-firebase-preview.yml"
RESOLVE_SCRIPT = ROOT / ".github" / "scripts" / "resolve-stripe-mode.sh"
VALIDATE_SCRIPT = ROOT / ".github" / "scripts" / "validate-stripe-deploy-mode.sh"


def _run_resolve(event: str, input_mode: str = "", vars_mode: str = "", *, allow_live_push: str = ""):
    env = os.environ.copy()
    env["GITHUB_OUTPUT"] = str(ROOT / ".pytest-tmp-stripe-mode-out")
    env["RUANA_STRIPE_ALLOW_LIVE_PUSH"] = allow_live_push
    env_path = Path(env["GITHUB_OUTPUT"])
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(RESOLVE_SCRIPT), event, input_mode, vars_mode],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=ROOT,
    )
    mode = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("mode="):
                mode = line.split("=", 1)[1]
    return result, mode


def test_resolve_script_syntax():
    result = subprocess.run(["bash", "-n", str(RESOLVE_SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_validate_script_syntax():
    result = subprocess.run(["bash", "-n", str(VALIDATE_SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_deploy_workflow_no_hardcoded_stripe_mode_test():
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "RUANA_STRIPE_MODE=test" not in content
    assert "resolve-stripe-mode.sh" in content
    assert "validate-stripe-deploy-mode.sh" in content
    assert "steps.stripe_mode.outputs.mode" in content
    assert "ruana_stripe_mode" in content


def test_preview_workflow_fija_test_y_valida():
    content = PREVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert "RUANA_STRIPE_MODE=test" in content
    assert "validate-stripe-deploy-mode.sh" in content
    assert "sync-cron-secret-gcp.sh" in content


def test_resolve_default_test_on_push():
    result, mode = _run_resolve("push", "", "")
    assert result.returncode == 0, result.stderr
    assert mode == "test"


def test_resolve_workflow_dispatch_input_live():
    result, mode = _run_resolve("workflow_dispatch", "live", "test")
    assert result.returncode == 0
    assert mode == "live"


def test_resolve_repo_var_when_no_dispatch_input():
    result, mode = _run_resolve("push", "", "live", allow_live_push="true")
    assert result.returncode == 0
    assert mode == "live"


def test_resolve_blocks_live_on_push_without_opt_in():
    result, mode = _run_resolve("push", "", "live", allow_live_push="")
    assert result.returncode != 0
    assert mode == ""


@pytest.mark.parametrize(
    "mode,key,ok",
    [
        ("test", "sk_test_abc", True),
        ("live", "sk_live_abc", True),
        ("test", "sk_live_abc", False),
        ("live", "sk_test_abc", False),
    ],
)
def test_validate_stripe_deploy_mode(mode, key, ok):
    result = subprocess.run(
        ["bash", str(VALIDATE_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "RUANA_STRIPE_MODE": mode, "STRIPE_SECRET_KEY": key},
        cwd=ROOT,
    )
    assert (result.returncode == 0) is ok, result.stderr or result.stdout
