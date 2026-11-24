"""Admin: corregir CP, dar de baja (sin borrar) y reactivar un aliado."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import red_regional_service as rr
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module, "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "ruana_admin_estado.db"))
    conn = db._connect()
    for nombre, cp in (("G Val", "460003"), ("G Zar", "50010"), ("G Zar2", "50014")):
        conn.execute("INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, 'activo')", (nombre, cp))
    gids = [r[0] for r in conn.execute("SELECT id FROM grupos ORDER BY id").fetchall()]
    for cod, of, cp, gid in (("90860", "Manitas / Reparaciones generales", "460003", gids[0]),
                             ("88277", "Electricidad", "46009", gids[0]),
                             ("99692", "Electricidad", "50010", gids[1]),
                             ("77809", "Carpintería de madera e interior", "50014", gids[2])):
        conn.execute(
            "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado) "
            "VALUES (?, ?, ?, ?, ?, 'activo')", (cod, cod, of, cp, gid))
    conn.commit()
    conn.close()
    return db


def _miembros(db, slug):
    return rr.estado(db, rr.red_por_slug(slug))["miembros"]


def test_api_corregir_cp_entra_en_red(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    rr.activar(sqlite_db, "ADMIN", rr.red_por_slug("red_valencia"))
    assert "90860" not in _miembros(sqlite_db, "red_valencia")
    lectura = session_headers("admin", "ADMIN001", permisos=["leer"])
    esc = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])
    url = "/api/admin/aliados/90860/codigo-postal"
    assert client.post(url, json={"codigo_postal": "46003"}, headers=lectura).status_code == 403
    assert client.post(url, json={"codigo_postal": "460003"}, headers=esc).status_code == 400
    r = client.post(url, json={"codigo_postal": "46003"}, headers=esc)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["cp_anterior"] == "460003"
    assert "90860" in _miembros(sqlite_db, "red_valencia")


def test_api_baja_no_borra_saca_de_red_y_reactivar(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    zar = rr.red_por_slug("red_zaragoza")
    rr.activar(sqlite_db, "ADMIN", zar)
    assert set(_miembros(sqlite_db, "red_zaragoza")) == {"99692", "77809"}
    esc = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])
    r = client.post("/api/admin/aliados/99692/baja", json={"motivo": "pidió la baja"}, headers=esc)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["estado"] == "inactivo"
    conn = sqlite_db._connect()
    row = conn.execute("SELECT estado, grupo_id FROM aliados WHERE codigo = '99692'").fetchone()
    conn.close()
    assert row[0] == "inactivo" and row[1] is not None  # sigue existiendo, mismo grupo
    assert _miembros(sqlite_db, "red_zaragoza") == ["77809"]
    r2 = client.post("/api/admin/aliados/99692/reactivar", headers=esc)
    assert r2.status_code == 200
    assert "99692" in _miembros(sqlite_db, "red_zaragoza")
    assert client.post("/api/admin/aliados/77809/reactivar", headers=esc).status_code == 400
