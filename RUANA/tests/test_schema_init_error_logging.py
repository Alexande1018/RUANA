"""Fallo de init Postgres: log ERROR con marcador para Cloud Monitoring."""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from core.services import schema_service


def test_init_postgres_schema_logs_error_marker(caplog):
    db = MagicMock()
    db._connect.side_effect = RuntimeError('relation "sqlite_master" does not exist')
    caplog.set_level(logging.ERROR, logger="ruana.db.schema")

    schema_service._init_postgres_schema(db)

    assert schema_service.SCHEMA_INIT_FAIL_MARKER in caplog.text
    assert "sqlite_master" in caplog.text
    assert '"component":"postgres_schema"' in caplog.text


def test_deploy_workflow_upserts_schema_init_alert():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github" / "workflows" / "deploy-firebase.yml").read_text(encoding="utf-8")
    script = (root / ".github" / "scripts" / "upsert-postgres-schema-init-alert.sh").read_text(encoding="utf-8")
    policy = (root / "infra" / "monitoring" / "ruana-postgres-schema-init-alert.json").read_text(encoding="utf-8")
    assert "upsert-postgres-schema-init-alert.sh" in workflow
    assert "ruana_postgres_schema_init_failed" in script
    assert "logging.googleapis.com/user/ruana_postgres_schema_init_failed" in policy

    import subprocess
    syntax = subprocess.run(
        ["bash", "-n", str(root / ".github" / "scripts" / "upsert-postgres-schema-init-alert.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
