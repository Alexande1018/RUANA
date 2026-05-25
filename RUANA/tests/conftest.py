import time

import pytest

from RUANA.web import app as app_module


class Hito2AFakeDB:
    def __init__(self):
        self.calls = []

    def codigo_existe(self, codigo):
        self.calls.append(("codigo_existe", codigo))
        return False

    def obtener_aliado_por_codigo(self, codigo):
        self.calls.append(("obtener_aliado_por_codigo", codigo))
        return {"id": 42, "codigo": codigo, "estado": "activo"}

    def crear_aliado(self, **kwargs):
        self.calls.append(("crear_aliado", kwargs))
        return {"status": "success"}

    def _registrar_invitacion(self, codigo, aliado_id):
        self.calls.append(("_registrar_invitacion", codigo, aliado_id))

    def marcar_solicitud_contestada(self, solicitud_id, invitador_aliado_id=None):
        self.calls.append(("marcar_solicitud_contestada", solicitud_id, invitador_aliado_id))

    def finalizar_competencia_activas_vencidas(self):
        self.calls.append(("finalizar_competencia_activas_vencidas",))
        return [{"grupo_id": 1, "resultado": "finalizada"}]

    def purga_mensual(self):
        self.calls.append(("purga_mensual",))
        return {"status": "success", "procesados": 1}


@pytest.fixture(autouse=True)
def clear_ruana_sessions():
    previous_testing = app_module.app.config.get("TESTING")
    with app_module._RUANA_SESSION_LOCK:
        app_module._RUANA_SESSION_STORE.clear()
    app_module.app.config.update(TESTING=True)
    yield
    with app_module._RUANA_SESSION_LOCK:
        app_module._RUANA_SESSION_STORE.clear()
    app_module.app.config.update(TESTING=previous_testing)


@pytest.fixture
def client():
    return app_module.app.test_client()


@pytest.fixture
def fake_db(monkeypatch):
    db = Hito2AFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    return db


def make_session_headers(tipo, codigo, permisos=None):
    session_id = app_module._ruana_session_create(
        tipo=tipo,
        codigo=codigo,
        expires_at=time.time() + 3600,
        permisos=permisos or [],
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


@pytest.fixture
def session_headers():
    return make_session_headers
