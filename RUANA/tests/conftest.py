import os
import time
from pathlib import Path

import pytest

from RUANA.web import app as app_module

_QA_ADMIN_CREDENTIALS = Path(__file__).resolve().parents[1] / "config" / "admin_credentials.qa.json"


class Hito2AFakeDB:
    def __init__(self):
        self.calls = []
        self.aliado_estado = "activo"

    def codigo_existe(self, codigo):
        self.calls.append(("codigo_existe", codigo))
        return False

    def invitacion_codigo_existe(self, codigo):
        self.calls.append(("invitacion_codigo_existe", codigo))
        return False

    def codigo_disponible_para_asignar(self, codigo):
        self.calls.append(("codigo_disponible_para_asignar", codigo))
        return True

    def obtener_invitacion_pendiente(self, codigo):
        self.calls.append(("obtener_invitacion_pendiente", codigo))
        return None

    def eliminar_aliado_placeholder(self, codigo):
        self.calls.append(("eliminar_aliado_placeholder", codigo))
        return False

    def obtener_aliado_por_codigo(self, codigo):
        self.calls.append(("obtener_aliado_por_codigo", codigo))
        return {"id": 42, "codigo": codigo, "estado": self.aliado_estado}

    def crear_aliado(self, **kwargs):
        self.calls.append(("crear_aliado", kwargs))
        return {"status": "success"}

    def _registrar_invitacion(self, codigo, aliado_id, solicitud_id=None):
        self.calls.append(("_registrar_invitacion", codigo, aliado_id, solicitud_id))

    def validar_campana_invitacion(self, codigo):
        self.calls.append(("validar_campana_invitacion", codigo))
        return None

    def obtener_campana_invitacion(self, codigo):
        self.calls.append(("obtener_campana_invitacion", codigo))
        return None

    def consumir_campana_invitacion(self, codigo, nuevo_aliado_codigo):
        self.calls.append(("consumir_campana_invitacion", codigo, nuevo_aliado_codigo))
        return True

    def crear_campana_invitacion(self, **kwargs):
        self.calls.append(("crear_campana_invitacion", kwargs))
        campana = {
            "codigo": (kwargs.get("codigo") or "RUANA-TEST").upper(),
            "nombre": kwargs.get("nombre") or "Campana",
            "codigo_postal": kwargs.get("codigo_postal") or "",
            "max_usos": kwargs.get("max_usos") or 100,
            "usos_actuales": 0,
            "activo": 1,
        }
        return {"status": "success", "campana": campana}

    def listar_campanas_invitacion(self, limite=50):
        self.calls.append(("listar_campanas_invitacion", limite))
        return []

    def desactivar_campana_invitacion(self, codigo):
        self.calls.append(("desactivar_campana_invitacion", codigo))
        return {"status": "success", "codigo": codigo}

    def marcar_solicitud_contestada(self, solicitud_id, invitador_aliado_id=None):
        self.calls.append(("marcar_solicitud_contestada", solicitud_id, invitador_aliado_id))

    def atender_solicitud_por_id(self, solicitud_id, codigo):
        self.calls.append(("atender_solicitud_por_id", solicitud_id, codigo))
        return {"status": "success", "ok": True}

    def marcar_solicitud_candidato_pendiente(self, solicitud_id, codigo):
        self.calls.append(("marcar_solicitud_candidato_pendiente", solicitud_id, codigo))
        return {"status": "success", "ok": True, "estado": "candidato_pendiente"}

    def vincular_solicitud_a_aliado_incorporado(self, codigo_invitacion, nuevo_aliado_codigo):
        self.calls.append(("vincular_solicitud_a_aliado_incorporado", codigo_invitacion, nuevo_aliado_codigo))
        return {"status": "success", "ok": True, "vinculada": True}

    def finalizar_competencia_activas_vencidas(self):
        self.calls.append(("finalizar_competencia_activas_vencidas",))
        return [{"grupo_id": 1, "resultado": "finalizada"}]

    def purga_mensual(self):
        self.calls.append(("purga_mensual",))
        return {"status": "success", "procesados": 1}

    def obtener_o_crear_invitador_admin(self, admin_codigo, nombre=""):
        self.calls.append(("obtener_o_crear_invitador_admin", admin_codigo, nombre))
        return admin_codigo


@pytest.fixture(autouse=True)
def admin_test_credentials(tmp_path, monkeypatch):
    credentials = tmp_path / "admin_credentials.json"
    credentials.write_text(_QA_ADMIN_CREDENTIALS.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("RUANA_ADMIN_CREDENTIALS_PATH", str(credentials))


@pytest.fixture(autouse=True)
def clear_ruana_sessions():
    previous_testing = app_module.app.config.get("TESTING")
    with app_module._RUANA_SESSION_LOCK:
        app_module._RUANA_SESSION_STORE.clear()
        app_module._RUANA_SESSION_REVOKED.clear()
    app_module.app.config.update(TESTING=True)
    yield
    with app_module._RUANA_SESSION_LOCK:
        app_module._RUANA_SESSION_STORE.clear()
        app_module._RUANA_SESSION_REVOKED.clear()
    app_module.app.config.update(TESTING=previous_testing)


@pytest.fixture
def client():
    return app_module.app.test_client()


@pytest.fixture
def fake_db(monkeypatch):
    from tests.service_forwarders import install_service_db_forwarders

    db = Hito2AFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    install_service_db_forwarders(monkeypatch)
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
