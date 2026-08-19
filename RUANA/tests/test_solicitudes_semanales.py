"""Tests solicitudes semanales — aislamiento por grupo, duplicados y autorización."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import solicitud_semanal_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_sol_sem.db"))


def _semana_actual():
    d = date.today()
    lunes = d - timedelta(days=d.weekday())
    return lunes.isoformat()


def _crear_grupo(db, nombre, cp, codigos_oficios):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        (nombre, cp, "activo"),
    )
    grupo_id = cursor.lastrowid
    for codigo, nombre_aliado, oficio in codigos_oficios:
        cursor.execute(
            """
            INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre_aliado, oficio, cp, grupo_id, "activo"),
        )
    conn.commit()
    conn.close()
    return grupo_id


def test_crear_solicitud_valida(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    r = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db,
        "JAIME",
        "Electricidad",
        "Necesito fotos de producto",
        es_oficio_personalizado=False,
    )
    assert r["status"] == "success"
    assert r["id"]


def test_panel_incluye_oficios_del_grupo_y_catalogo(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo oficios",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "JAIME")
    assert panel["status"] == "success"
    assert "Electricidad" in panel["oficios_grupo"]
    assert isinstance(panel["oficios_catalogo"], list)
    assert len(panel["oficios_catalogo"]) > 0


def test_no_duplicar_solicitud_misma_semana(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo dup",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    r1 = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "Primera", False
    )
    assert r1["status"] == "success"
    r2 = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Carpintería de madera e interior", "Segunda", False
    )
    assert r2["status"] == "success"
    assert r2.get("already_existed") is True
    assert r2["id"] == r1["id"]


def test_solicitud_vinculada_al_grupo_correcto(sqlite_db):
    gid = _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT grupo_id FROM solicitudes_semanales WHERE solicitante_codigo = ?", ("JAIME",))
    row = cursor.fetchone()
    conn.close()
    assert row[0] == gid


def test_mismo_grupo_ve_solicitud_otro_grupo_no(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 26",
        "03015",
        [("PEDRO", "Pedro", "Electricidad")],
    )
    solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )

    panel_marta = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "MARTA")
    assert panel_marta["status"] == "success"
    assert len(panel_marta["activas_grupo"]) == 1
    assert panel_marta["activas_grupo"][0]["solicitante_codigo"] == "JAIME"

    panel_pedro = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "PEDRO")
    assert panel_pedro["status"] == "success"
    assert panel_pedro["activas_grupo"] == []


def test_puedo_ayudar_y_listar_interesados(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo ayuda",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Electricidad"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    ayuda = solicitud_semanal_service.responder_puedo_ayudar(sqlite_db, sid, "MARTA")
    assert ayuda["status"] == "success"
    assert ayuda["contacto_id"]

    inter = solicitud_semanal_service.listar_interesados(sqlite_db, sid, "JAIME")
    assert inter["status"] == "success"
    assert inter["total"] == 1
    assert inter["interesados"][0]["aliado_codigo"] == "MARTA"

    denegado = solicitud_semanal_service.listar_interesados(sqlite_db, sid, "MARTA")
    assert denegado["status"] == "error"


def test_no_puedo_ayudar_otro_grupo_fallido(sqlite_db):
    gid25 = _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 26",
        "03015",
        [("PEDRO", "Pedro", "Electricidad")],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    r = solicitud_semanal_service.responder_no_puedo_ayudar(sqlite_db, sid, "PEDRO")
    assert r["status"] == "error"


def test_expirada_deja_de_estar_activa_conserva_historial(sqlite_db):
    gid = _crear_grupo(
        sqlite_db,
        "Grupo exp",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    semana_pasada = (date.today() - timedelta(days=7)).isoformat()
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    sqlite_db._migrar_solicitudes_semanales(conn, cursor)
    cursor.execute(
        """
        INSERT INTO solicitudes_semanales (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            es_oficio_personalizado, semana_inicio, estado, expira_at
        ) VALUES (?, ?, ?, ?, ?, 0, ?, 'activa', ?)
        """,
        (gid, "JAIME", "Jaime", "Electricidad", "vieja", semana_pasada, semana_pasada),
    )
    conn.commit()
    conn.close()

    solicitud_semanal_service.expirar_solicitudes_vencidas(sqlite_db)
    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "JAIME")
    assert panel["propia"] is None

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT estado FROM solicitudes_semanales WHERE semana_inicio = ?",
        (semana_pasada,),
    )
    estado = cursor.fetchone()[0]
    conn.close()
    assert estado == "expirada"


def test_oficio_personalizado_otro(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo otro",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    r = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db,
        "JAIME",
        "Fotógrafo especializado en producto",
        "",
        es_oficio_personalizado=True,
    )
    assert r["status"] == "success"
    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "JAIME")
    assert panel["propia"]["es_oficio_personalizado"] == 1


def test_api_crear_y_aislamiento(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    _crear_grupo(
        sqlite_db,
        "Grupo API 25",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo API 26",
        "03015",
        [("PEDRO", "Pedro", "Electricidad")],
    )
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    h_jaime = session_headers("aliado", "JAIME")
    h_marta = session_headers("aliado", "MARTA")
    h_pedro = session_headers("aliado", "PEDRO")

    create = client.post(
        "/api/solicitudes-semanales",
        json={"oficio": "Electricidad", "descripcion": "Producto"},
        headers=h_jaime,
    )
    assert create.status_code == 201

    get_marta = client.get("/api/solicitudes-semanales", headers=h_marta)
    assert get_marta.status_code == 200
    data_m = get_marta.get_json()
    assert len(data_m["activas_grupo"]) == 1

    get_pedro = client.get("/api/solicitudes-semanales", headers=h_pedro)
    assert get_pedro.status_code == 200
    assert get_pedro.get_json()["activas_grupo"] == []

    dup = client.post(
        "/api/solicitudes-semanales",
        json={"oficio": "Carpintería de madera e interior"},
        headers=h_jaime,
    )
    assert dup.status_code in (200, 201)
    assert dup.get_json().get("already_existed") is True


def test_manipulacion_id_otro_grupo(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    _crear_grupo(
        sqlite_db,
        "G1",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    _crear_grupo(
        sqlite_db,
        "G2",
        "03015",
        [("PEDRO", "Pedro", "Electricidad")],
    )
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    resp = client.post(
        f"/api/solicitudes-semanales/{sid}/puedo-ayudar",
        headers=session_headers("aliado", "PEDRO"),
    )
    assert resp.status_code == 400
