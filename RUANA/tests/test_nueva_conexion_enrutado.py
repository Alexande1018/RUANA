"""Nueva conexión: oficio en grupo, cercano o buscando ayuda. Nunca a todos los aliados."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import notificacion_service, solicitud_service
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_nueva_conexion.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03001", estado="activo"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado=estado,
        score=50,
    )
    assert r.get("status") == "success", r
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = ? WHERE codigo = ?", (estado, codigo))
    conn.commit()
    conn.close()
    return r


def _tipos(db, codigo):
    return {n.get("tipo") for n in notificacion_service.listar_notificaciones_aliado(db, codigo)}


def _ids_entrantes(db, codigo):
    return {s.get("id") for s in solicitud_service.listar_solicitudes_activas_por_codigo(db, codigo)}


def test_oficio_disponible_en_grupo_solo_ese_profesional(sqlite_db):
    _crear(sqlite_db, "91001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "91002", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "91003", oficio="Fontanería y fontanería-gas", cp="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "91001", "Fontanería", "Fuga urgente en cocina"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "profesional_grupo"
    assert creada["profesional"]["codigo"] == "91003"
    assert creada.get("proximidad_notificado") is False
    assert "todos los aliados" not in (creada.get("mensaje") or "").lower()

    assert sid in _ids_entrantes(sqlite_db, "91003")
    assert sid not in _ids_entrantes(sqlite_db, "91002")
    assert sid not in _ids_entrantes(sqlite_db, "91001")

    assert "solicitud_asignada" in _tipos(sqlite_db, "91003")
    assert "solicitud_nueva" not in _tipos(sqlite_db, "91002")
    assert "solicitud_buscando_ayuda" not in _tipos(sqlite_db, "91002")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "91002")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "91003")


def test_oficio_ausente_con_profesional_cercano_requiere_aprobacion(sqlite_db):
    _crear(sqlite_db, "92001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "92002", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "92003", oficio="Fontanería y fontanería-gas", cp="03003")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "92001", "Fontanería", "Necesito fontanero"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] == "92003"
    assert creada["requiere_aprobacion_proximidad"] is True
    assert creada["proximidad_notificado"] is False
    assert "No hay fontanero en tu grupo" in creada["mensaje"]
    assert "Aliado 92003" in creada["mensaje"]

    assert sid not in _ids_entrantes(sqlite_db, "92002")
    assert sid not in _ids_entrantes(sqlite_db, "92003")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "92003")
    assert "solicitud_buscando_ayuda" not in _tipos(sqlite_db, "92002")
    assert "solicitud_nueva" not in _tipos(sqlite_db, "92002")

    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, "92001")
    assert propias[0]["requiere_aprobacion_proximidad"] is True

    aceptada = solicitud_service.aceptar_proximidad_solicitud(sqlite_db, sid, "92001")
    assert aceptada["status"] == "success"
    assert aceptada.get("proximidad_notificado") is True

    assert sid in _ids_entrantes(sqlite_db, "92003")
    assert sid not in _ids_entrantes(sqlite_db, "92002")
    assert "proximidad_solicitud" in _tipos(sqlite_db, "92003")
    assert "proximidad_contactada" in _tipos(sqlite_db, "92002")
    assert "solicitud_nueva" not in _tipos(sqlite_db, "92002")


def test_pedir_recomendacion_al_grupo_tras_cercano(sqlite_db):
    _crear(sqlite_db, "92101", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "92102", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "92103", oficio="Fontanería y fontanería-gas", cp="03003")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "92101", "Fontanería", "Fuga en baño"
    )
    sid = creada["id"]
    pedida = solicitud_service.pedir_recomendacion_grupo_solicitud(sqlite_db, sid, "92101")
    assert pedida["status"] == "success"
    assert pedida["enrutamiento"] == "buscando_ayuda"

    assert sid in _ids_entrantes(sqlite_db, "92102")
    assert sid not in _ids_entrantes(sqlite_db, "92103")
    assert "solicitud_buscando_ayuda" in _tipos(sqlite_db, "92102")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "92103")


def test_oficio_sin_profesional_cercano_queda_buscando_ayuda(sqlite_db):
    _crear(sqlite_db, "93001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "93002", oficio="Cerrajería", cp="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "93001", "Fontanería", "No hay nadie cerca"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "buscando_ayuda"
    assert creada.get("proximidad") is None
    assert "Buscando ayuda" in (creada.get("mensaje") or "")

    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, "93001")
    assert propias[0]["destino"] == "buscando_ayuda"
    assert propias[0]["etiqueta_busqueda"] == "Buscando ayuda"

    assert sid in _ids_entrantes(sqlite_db, "93002")
    assert "solicitud_buscando_ayuda" in _tipos(sqlite_db, "93002")
    assert "solicitud_asignada" not in _tipos(sqlite_db, "93002")


def test_nunca_se_envia_la_solicitud_a_todos_los_aliados(sqlite_db):
    _crear(sqlite_db, "94001", oficio="Electricidad", cp="04001")
    _crear(sqlite_db, "94002", oficio="Cerrajería", cp="04001")
    _crear(sqlite_db, "94003", oficio="Pintura y decoración", cp="04001")
    _crear(sqlite_db, "94004", oficio="Fontanería y fontanería-gas", cp="04001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "94001", "Fontanería", "Solo el fontanero"
    )
    sid = creada["id"]
    assert creada["enrutamiento"] == "profesional_grupo"

    for codigo in ("94002", "94003"):
        assert sid not in _ids_entrantes(sqlite_db, codigo)
        tipos = _tipos(sqlite_db, codigo)
        assert "solicitud_nueva" not in tipos
        assert "solicitud_asignada" not in tipos
        assert "solicitud_buscando_ayuda" not in tipos

    assert sid in _ids_entrantes(sqlite_db, "94004")
    assert "solicitud_asignada" in _tipos(sqlite_db, "94004")


def test_api_nueva_conexion_enruta_y_acepta_proximidad(
    client, sqlite_db, monkeypatch, session_headers
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear(sqlite_db, "95001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "95002", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "95003", oficio="Fontanería y fontanería-gas", cp="03003")

    headers = session_headers("aliado", "95001")
    created = client.post(
        "/api/solicitudes",
        json={"oficio": "Fontanería", "descripcion": "Fuga en la cocina de casa"},
        headers=headers,
    )
    assert created.status_code == 200
    body = created.get_json()
    assert body["ok"] is True
    assert body["enrutamiento"] == "proximidad"
    assert "No hay fontanero en tu grupo" in body["mensaje"]
    sid = body["id"]

    acepta = client.post(
        f"/api/solicitudes/{sid}/aceptar-proximidad",
        headers=headers,
    )
    assert acepta.status_code == 200
    assert acepta.get_json()["ok"] is True
    assert sid in _ids_entrantes(sqlite_db, "95003")
    assert "proximidad_contactada" in _tipos(sqlite_db, "95002")
