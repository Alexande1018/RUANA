import logging
import os

import pytest
from google.cloud.logging_v2.handlers import StructuredLogHandler

from RUANA.web import app as app_module


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
    root.setLevel(level)
    app_module.configure_app_logging()


def test_app_arranca_en_test_con_stdout(restore_root_logging):
    assert os.environ.get("RUANA_ENV", "").strip().lower() == "test"
    modo = app_module.configure_app_logging()
    assert modo == "stdout"
    assert app_module.app is not None
    assert app_module.app.blueprints
    resp = app_module.app.test_client().get("/api/admin/bp-health")
    assert resp.status_code == 200
    root = logging.getLogger()
    ruana = [h for h in root.handlers if getattr(h, app_module._RUANA_LOG_HANDLER_MARK, False)]
    assert ruana
    assert not any(isinstance(h, StructuredLogHandler) for h in ruana)


def test_app_arranca_con_structured_log_handler(monkeypatch, restore_root_logging):
    monkeypatch.setenv("RUANA_ENV", "development")
    modo = app_module.configure_app_logging()
    assert modo == "structured"
    assert app_module.app is not None
    resp = app_module.app.test_client().get("/api/admin/bp-health")
    assert resp.status_code == 200
    root = logging.getLogger()
    assert any(
        isinstance(h, StructuredLogHandler) and getattr(h, app_module._RUANA_LOG_HANDLER_MARK, False)
        for h in root.handlers
    )


def test_app_arranca_si_structured_handler_falla(monkeypatch, restore_root_logging):
    monkeypatch.setenv("RUANA_ENV", "development")

    def boom(*_args, **_kwargs):
        raise RuntimeError("structured handler unavailable")

    monkeypatch.setattr(
        "google.cloud.logging_v2.handlers.StructuredLogHandler",
        boom,
    )
    modo = app_module.configure_app_logging()
    assert modo == "stdout"
    resp = app_module.app.test_client().get("/api/admin/bp-health")
    assert resp.status_code == 200
    root = logging.getLogger()
    ruana = [h for h in root.handlers if getattr(h, app_module._RUANA_LOG_HANDLER_MARK, False)]
    assert ruana
    assert not any(isinstance(h, StructuredLogHandler) for h in ruana)
