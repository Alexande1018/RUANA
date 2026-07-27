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
    return db_module.DBManager(str(tmp_path / "ruana_directorio_cp.db"))


def _crear_grupo(db, cp, nombre):
    gid = db.crear_grupo_en_cp(cp, "Ciudad", "Provincia")
    assert isinstance(gid, dict) and gid.get("id")
    return gid["id"]


def _crear_activo(db, codigo, nombre, cp, grupo_id):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Electricidad",
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert result["status"] == "success"
    if grupo_id is not None:
        _forzar_grupo_id(db, codigo, grupo_id, cp)
    return result


def _forzar_grupo_id(db, codigo, grupo_id, cp):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE aliados SET grupo_id = ?, codigo_postal = ? WHERE codigo = ?",
        (grupo_id, cp, codigo),
    )
    conn.commit()
    conn.close()


def test_directorio_excluye_aliados_de_otro_cp_aunque_compartan_grupo(sqlite_db):
    grupo_cp_a = _crear_grupo(sqlite_db, "28001", "Grupo A")
    grupo_cp_b = _crear_grupo(sqlite_db, "08001", "Grupo B")

    _crear_activo(sqlite_db, "91001", "Aliado CP A", "28001", grupo_cp_a)
    _crear_activo(sqlite_db, "91002", "Compañero CP A", "28001", grupo_cp_a)
    _crear_activo(sqlite_db, "91003", "Aliado CP B", "08001", grupo_cp_b)

    # Error de datos: aliado de otro CP asignado al grupo de 28001
    _forzar_grupo_id(sqlite_db, "91003", grupo_cp_a, "08001")

    directorio = sqlite_db.listar_aliados_directorio_grupo("91001")
    codigos = {a["codigo"] for a in directorio}

    assert "91002" in codigos
    assert "91003" not in codigos
    assert "91001" not in codigos


def test_directorio_api_respeta_filtro_cp(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    grupo_id = _crear_grupo(sqlite_db, "28001", "Grupo API")
    _crear_activo(sqlite_db, "92001", "Sesion CP A", "28001", grupo_id)
    _crear_activo(sqlite_db, "92002", "Otro CP", "08001", grupo_id)
    _forzar_grupo_id(sqlite_db, "92002", grupo_id, "08001")

    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo="92001",
        expires_at=9999999999,
    )
    headers = {app_module.RUANA_SESSION_HEADER: session_id}

    resp = client.get("/api/aliados/directorio", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    codigos = {a["codigo"] for a in data["aliados"]}
    assert "92002" not in codigos
