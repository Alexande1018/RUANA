"""
Asignación territorial directa por CP. Sustituye el antiguo flujo de Grupo Madre.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_territorio.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03001", estado="activo"):
    return db.crear_aliado(
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


def _set_activo(db, codigo):
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()


def _grupo_tipo(db, grupo_id):
    g = db.obtener_grupo_por_id(grupo_id)
    return (g or {}).get("tipo")


def test_cp_sin_territorial_crea_grupo_territorial(sqlite_db):
    r = _crear(sqlite_db, "50001", cp="03001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "50001")
    aliado = sqlite_db.obtener_aliado_por_codigo("50001")
    assert aliado.get("grupo_id") is not None
    assert _grupo_tipo(sqlite_db, aliado["grupo_id"]) == "territorial"
    assert sqlite_db.cp_en_modo_territorial("03001") is True
    assert sqlite_db.territorio_modo_aliado("03001", aliado["grupo_id"]) == "territorial"


def test_cp_con_territorial_mantiene_flujo_actual(sqlite_db):
    gid = sqlite_db.crear_grupo_en_cp("28001", "Madrid", "Madrid")
    assert isinstance(gid, dict) and gid.get("id")
    r = _crear(sqlite_db, "50002", cp="28001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "50002")
    aliado = sqlite_db.obtener_aliado_por_codigo("50002")
    assert aliado.get("grupo_id") is not None
    assert _grupo_tipo(sqlite_db, aliado["grupo_id"]) == "territorial"


def test_directorio_no_mezcla_cps_distintos(sqlite_db):
    _crear(sqlite_db, "52001", cp="03001")
    _crear(sqlite_db, "52002", oficio="Fontanería y fontanería-gas", cp="03003")
    _set_activo(sqlite_db, "52001")
    _set_activo(sqlite_db, "52002")

    directorio = sqlite_db.listar_aliados_directorio_grupo("52001")
    codigos = {a["codigo"] for a in directorio}
    assert "52002" not in codigos


def test_directorio_territorial_sigue_filtrando_por_cp(sqlite_db):
    gid = sqlite_db.crear_grupo_en_cp("28001", "Madrid", "Madrid")
    assert isinstance(gid, dict) and gid.get("id")
    grupo_id = gid["id"]
    _crear(sqlite_db, "53001", cp="28001")
    _crear(sqlite_db, "53002", oficio="Fontanería", cp="28002")
    _set_activo(sqlite_db, "53001")
    _set_activo(sqlite_db, "53002")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = '53002'", (grupo_id,))
    conn.commit()
    conn.close()

    directorio = sqlite_db.listar_aliados_directorio_grupo("53001")
    codigos = {a["codigo"] for a in directorio}
    assert "53002" not in codigos


def test_mismo_oficio_en_cp_sin_plaza_va_a_espera(sqlite_db):
    r1 = _crear(sqlite_db, "54001", oficio="Electricidad", cp="03001")
    assert r1["status"] == "success"
    _set_activo(sqlite_db, "54001")

    r2 = _crear(sqlite_db, "54006", oficio="Electricidad", cp="03001")
    assert r2["status"] == "success"
    aliado6 = sqlite_db.obtener_aliado_por_codigo("54006")
    assert aliado6["estado"] == "en_espera"


def test_resolver_cp_api(client):
    resp = client.get("/api/territorio/resolver-cp?cp=03001")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["resuelto"] is True
    assert data["ciudad"] == "Alicante"


def test_aviso_madre_endpoint_eliminado(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    r = _crear(sqlite_db, "56001", cp="03001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "56001")

    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo="56001",
        expires_at=9999999999,
    )
    headers = {app_module.RUANA_SESSION_HEADER: session_id}

    resp = client.post(
        "/api/aliado/grupo-madre/aviso-visto",
        json={"aviso_tipo": "grupo_madre_bienvenida"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_get_aliado_datos_carga_si_falta_columna_tipo(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    r = _crear(sqlite_db, "57009", cp="03001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "57009")

    conn = sqlite_db._connect()
    conn.execute("ALTER TABLE grupos DROP COLUMN tipo")
    conn.commit()
    conn.close()

    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo="57009",
        expires_at=9999999999,
    )
    headers = {app_module.RUANA_SESSION_HEADER: session_id}

    resp = client.get("/api/aliado/datos", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["aliado"]["codigo"] == "57009"
    assert data["aliado"].get("territorio_modo") == "territorial"
    assert data["aliado"].get("mostrar_aviso_madre") is False
