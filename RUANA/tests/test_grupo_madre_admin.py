"""Panel admin: estado territorial y comprobación de migración (sin Grupo Madre)."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import territorio_migracion_service
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_madre_admin.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03020"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"A {codigo}",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@t.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()


def test_comprobar_migracion_sin_casos(sqlite_db):
    _crear(sqlite_db, "90001")
    check = territorio_migracion_service.comprobar_migracion(sqlite_db)
    assert check["status"] == "success"
    assert check["total"] == 0


def test_listar_estado_territorial(sqlite_db):
    _crear(sqlite_db, "90011", cp="03020")
    estado = territorio_migracion_service.listar_estado_territorial(sqlite_db)
    assert estado["status"] == "success"
    assert estado["total"] >= 1
    codigos = {a["codigo"] for a in estado["aliados"]}
    assert "90011" in codigos


def test_admin_territorio_endpoints(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])
    _crear(sqlite_db, "90021")

    resp_check = client.get("/api/admin/territorio/migracion-check", headers=headers)
    assert resp_check.status_code == 200
    data_check = resp_check.get_json()
    assert data_check["status"] == "success"
    assert "sin_grupo_territorial_valido" in data_check

    resp_est = client.get("/api/admin/territorio/estado", headers=headers)
    assert resp_est.status_code == 200
    data_est = resp_est.get_json()
    assert data_est["status"] == "success"
    assert "aliados" in data_est


def test_endpoints_madre_eliminados(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])
    for path in (
        "/api/admin/grupos-madre",
        "/api/admin/cp-madurez",
        "/api/admin/cp-independencia/pendientes",
    ):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 404, path
    for path in (
        "/api/admin/cp-independencia/aprobar",
        "/api/admin/cp-independencia/posponer",
    ):
        resp = client.post(path, json={"codigo_postal": "03001"}, headers=headers)
        assert resp.status_code == 404, path


def test_dashboard_summary_sin_kpis_madre(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])
    resp = client.get("/api/admin/dashboard-summary", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert "grupos_madre" not in data
    assert "cp_independencia_pendientes" not in data
    assert "aliados_sin_grupo_territorial" in data
