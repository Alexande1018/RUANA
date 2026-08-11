import time

import pytest

from RUANA.web import app as app_module


class Hito2BFakeDB:
    def __init__(self):
        self.calls = []

    def listar_aliados(self, codigo_postal=None):
        self.calls.append(("listar_aliados", codigo_postal))
        return [{"id": 1, "codigo": "A0001", "email": "a@example.com", "telefono": "600000001"}]

    def obtener_aliado_por_id(self, aliado_id):
        self.calls.append(("obtener_aliado_por_id", aliado_id))
        if aliado_id == 1:
            return {"id": 1, "codigo": "A0001", "email": "a@example.com", "telefono": "600000001"}
        return None

    def obtener_aliado_por_codigo(self, codigo):
        self.calls.append(("obtener_aliado_por_codigo", codigo))
        if codigo == "A0001":
            return {
                "id": 1,
                "codigo": "A0001",
                "email": "a@example.com",
                "telefono": "600000001",
                "estado": "activo",
                "score": 75,
                "codigo_postal": "08001",
            }
        return None

    def codigo_existe(self, codigo):
        self.calls.append(("codigo_existe", codigo))
        return codigo == "A0001"

    def obtener_solicitudes_grupo(self, codigo_postal):
        self.calls.append(("obtener_solicitudes_grupo", codigo_postal))
        return []

    def score_a_estado(self, score):
        return "ESTABLE"

    def contar_referidos_por_codigo(self, codigo):
        return 0

    def contar_solicitudes_enviadas_contestadas(self, codigo):
        return 0

    def obtener_contacto_resumen(self, contacto_id):
        self.calls.append(("obtener_contacto_resumen", contacto_id))
        if contacto_id == 10:
            return {"id": 10, "solicitante_codigo": "A0001", "profesional_codigo": "B0002"}
        return None

    def listar_mensajes_contacto(self, contacto_id):
        self.calls.append(("listar_mensajes_contacto", contacto_id))
        return []

    def obtener_negociacion_contacto(self, contacto_id, codigo_aliado):
        self.calls.append(("obtener_negociacion_contacto", contacto_id, codigo_aliado))
        resumen = self.obtener_contacto_resumen(contacto_id)
        if not resumen:
            return {"status": "error", "message": "Contacto no encontrado"}
        sol = resumen.get("solicitante_codigo")
        pro = resumen.get("profesional_codigo")
        if codigo_aliado not in (sol, pro):
            return {"status": "error", "message": "No autorizado"}
        return {
            "status": "success",
            "eventos": [],
            "paso_actual": "servicio",
            "rol": "contratante" if codigo_aliado == sol else "profesional",
        }

    def estado_chat_contacto(self, contacto_id, codigo):
        self.calls.append(("estado_chat_contacto", contacto_id, codigo))
        return {"puede_enviar": True, "mensajes_restantes": 5}

    def enviar_mensaje_chat(self, contacto_id, emisor_codigo, texto):
        self.calls.append(("enviar_mensaje_chat", contacto_id, emisor_codigo, texto))
        return {"status": "success"}

    def actualizar_aliado(self, codigo, **kwargs):
        self.calls.append(("actualizar_aliado", codigo, kwargs))
        return {"status": "success", "updated": kwargs}

    def listar_evaluaciones(self, estado=None):
        self.calls.append(("listar_evaluaciones", estado))
        return [{"codigo_aliado": "A0001", "estado": "verde", "score": 80}]

    def obtener_historico_evaluaciones(self, codigo_aliado):
        self.calls.append(("obtener_historico_evaluaciones", codigo_aliado))
        return [{"estado_anterior": "amarillo", "estado_nuevo": "verde"}]

    def obtener_estadisticas_evaluaciones(self):
        self.calls.append(("obtener_estadisticas_evaluaciones",))
        return {"total": 1}


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
    db = Hito2BFakeDB()
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


# ---------- Lectura pública de PII en /api/aliados* ----------


def test_get_aliados_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/aliados")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_get_aliados_rejects_aliado_session_without_touching_db(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

    response = client.get("/api/aliados", headers=headers)

    assert response.status_code == 401
    assert fake_db.calls == []


def test_get_aliados_allows_admin(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])

    response = client.get("/api/aliados", headers=headers)

    assert response.status_code == 200
    assert ("listar_aliados", None) in fake_db.calls


def test_get_aliado_by_id_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/aliados/1")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_get_aliado_by_id_allows_admin(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])

    response = client.get("/api/aliados/1", headers=headers)

    assert response.status_code == 200
    assert ("obtener_aliado_por_id", 1) in fake_db.calls


def test_obtener_por_codigo_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/aliados/obtener-por-codigo/A0001")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_obtener_por_codigo_rejects_other_aliado(client, fake_db, session_headers):
    headers = session_headers("aliado", "B0002")

    response = client.get("/api/aliados/obtener-por-codigo/A0001", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_obtener_por_codigo_allows_self(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

    response = client.get("/api/aliados/obtener-por-codigo/A0001", headers=headers)

    assert response.status_code == 200
    assert ("obtener_aliado_por_codigo", "A0001") in fake_db.calls


def test_verificar_codigo_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/aliados/verificar-codigo/A0001")

    assert response.status_code == 401
    assert fake_db.calls == []


# ---------- Chat legacy sin sesión ----------


def test_chat_mensajes_legacy_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/chat/mensajes?contacto_id=10&codigo=A0001")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_chat_mensajes_legacy_uses_session_codigo(client, fake_db, session_headers):
    """GET legacy redirige a negociación guiada usando el código de sesión."""
    headers = session_headers("aliado", "A0001")

    response = client.get("/api/chat/mensajes?contacto_id=10", headers=headers)

    assert response.status_code == 200
    assert ("obtener_negociacion_contacto", 10, "A0001") in fake_db.calls
    data = response.get_json()
    assert data["status"] == "success"
    assert "eventos" in data


def test_chat_mensajes_legacy_rejects_non_participant(client, fake_db, session_headers):
    headers = session_headers("aliado", "C0003")

    response = client.get("/api/chat/mensajes?contacto_id=10", headers=headers)

    assert response.status_code == 403
    assert ("obtener_negociacion_contacto", 10, "C0003") in fake_db.calls


def test_chat_enviar_legacy_rejects_anonymous_without_touching_db(client, fake_db):
    """POST de chat libre está deshabilitado (410), incluso sin sesión."""
    response = client.post(
        "/api/chat/enviar",
        json={"contacto_id": 10, "emisor_codigo": "A0001", "texto": "hola"},
    )

    assert response.status_code == 410
    assert fake_db.calls == []
    body = response.get_json()
    assert body["status"] == "error"
    assert "negociacion" in body["message"].lower()


def test_chat_enviar_legacy_uses_session_codigo(client, fake_db, session_headers):
    """POST legacy permanece deshabilitado: el envío libre no se restaura con sesión."""
    headers = session_headers("aliado", "A0001")

    response = client.post(
        "/api/chat/enviar",
        json={"contacto_id": 10, "texto": "hola"},
        headers=headers,
    )

    assert response.status_code == 410
    assert ("enviar_mensaje_chat", 10, "A0001", "hola") not in fake_db.calls
    assert "negociacion" in response.get_json()["message"].lower()


# ---------- Campos editables por aliado ----------


def test_actualizar_aliado_rejects_score_estado_grupo_id(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

    response = client.put(
        "/api/aliados/A0001",
        json={"score": 100, "estado": "activo", "grupo_id": 99, "nombre": "Nuevo nombre"},
        headers=headers,
    )

    assert response.status_code == 200
    update_calls = [call for call in fake_db.calls if call[0] == "actualizar_aliado"]
    assert len(update_calls) == 1
    updated_fields = update_calls[0][2]
    assert updated_fields == {"nombre": "Nuevo nombre"}
    assert "score" not in updated_fields
    assert "estado" not in updated_fields
    assert "grupo_id" not in updated_fields


# ---------- Evaluaciones públicas ----------


def test_listar_evaluaciones_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/evaluaciones")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_listar_evaluaciones_allows_admin(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])

    response = client.get("/api/evaluaciones", headers=headers)

    assert response.status_code == 200
    assert ("listar_evaluaciones", None) in fake_db.calls


def test_historico_evaluaciones_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/evaluaciones/A0001/historico")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_historico_evaluaciones_rejects_other_aliado(client, fake_db, session_headers):
    headers = session_headers("aliado", "B0002")

    response = client.get("/api/evaluaciones/A0001/historico", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_historico_evaluaciones_allows_self(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

    response = client.get("/api/evaluaciones/A0001/historico", headers=headers)

    assert response.status_code == 200
    assert ("obtener_historico_evaluaciones", "A0001") in fake_db.calls


def test_historico_evaluaciones_allows_admin(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])

    response = client.get("/api/evaluaciones/A0001/historico", headers=headers)

    assert response.status_code == 200
    assert ("obtener_historico_evaluaciones", "A0001") in fake_db.calls


def test_estadisticas_evaluaciones_rejects_anonymous_without_touching_db(client, fake_db):
    response = client.get("/api/evaluaciones/estadisticas")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_estadisticas_evaluaciones_allows_admin(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])

    response = client.get("/api/evaluaciones/estadisticas", headers=headers)

    assert response.status_code == 200
    assert ("obtener_estadisticas_evaluaciones",) in fake_db.calls
