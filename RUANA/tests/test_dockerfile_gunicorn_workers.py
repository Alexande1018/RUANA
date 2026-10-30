"""Workers de gunicorn: 2 por defecto (memoria 512 MiB en Cloud Run), override por env."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


def _cmd_script() -> str:
    line = next(l for l in DOCKERFILE.read_text(encoding="utf-8").splitlines() if l.startswith("CMD "))
    argv = json.loads(line[len("CMD "):])
    assert argv[:2] == ["sh", "-c"]
    return argv[2]


def test_dockerfile_workers_por_defecto_2_sin_nproc():
    script = _cmd_script()
    assert "--workers ${WEB_CONCURRENCY:-2}" in script
    assert "nproc" not in script
    assert not re.search(r"2 \* cpus", script)


@pytest.mark.skipif(shutil.which("sh") is None, reason="sin sh")
@pytest.mark.parametrize("env_value,esperado", [(None, "2"), ("", "2"), ("3", "3")])
def test_dockerfile_workers_respeta_override(env_value, esperado):
    script = _cmd_script().replace("exec gunicorn", "echo")
    env = {"PATH": "/usr/bin:/bin"}
    if env_value is not None:
        env["WEB_CONCURRENCY"] = env_value
    out = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, check=True).stdout
    assert f"--workers {esperado} " in out
