"""Tests for GitHub admin secret JSON generator."""

import json
import subprocess
import sys
from pathlib import Path


def test_generate_github_admin_secret_outputs_valid_json():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "generate_github_admin_secret.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--admin-id",
            "TESTADMIN",
            "--password",
            "TestPassword123",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(root.parent),
    )
    payload = json.loads(result.stdout.strip().split("\n")[0])
    assert payload["version"] == 1
    assert "TESTADMIN" in payload["admins"]
    assert "password_hash" in payload["admins"]["TESTADMIN"]
    assert "TestPassword123" not in result.stdout
