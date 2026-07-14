import time

from RUANA.web import app as app_module


def test_aliado_session_jwt_survives_empty_memory_store():
    expires_at = time.time() + 3600
    token = app_module._ruana_session_create("aliado", "A0001", expires_at)

    with app_module._RUANA_SESSION_LOCK:
        app_module._RUANA_SESSION_STORE.clear()

    with app_module.app.test_request_context(
        headers={app_module.RUANA_SESSION_HEADER: token}
    ):
        assert app_module._aliado_session_valid() is True
        assert app_module._aliado_codigo() == "A0001"


def test_aliado_session_jwt_rejected_after_logout():
    expires_at = time.time() + 3600
    token = app_module._ruana_session_create("aliado", "A0001", expires_at)
    app_module._ruana_session_invalidate(token)

    with app_module.app.test_request_context(
        headers={app_module.RUANA_SESSION_HEADER: token}
    ):
        assert app_module._aliado_session_valid() is False
