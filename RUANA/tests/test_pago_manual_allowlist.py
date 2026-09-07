from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module

_IBAN_FAKE = "ES0000000000000000000000"
_BIZUM_FAKE = "600000000"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "pago_manual_allowlist.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    conn = db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)",
        ("A0001", "Aliado Uno", "a1@test.com"),
    )
    conn.commit()
    conn.close()
    return db


def _admin_headers(session_headers, escritura=True):
    permisos = ["leer", "configurar"] if escritura else ["leer"]
    return session_headers("admin", "ADMIN001", permisos=permisos)


def test_metodos_pago_aliado_no_habilitado_oculta_datos(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    resp = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert resp.status_code == 200
    metodos = resp.get_json()["metodos"]
    assert metodos["habilitado"] is False
    assert metodos["bizum_num"] is None
    assert metodos["iban"] is None
    assert metodos["qr_revolut_path"] is None


def test_metodos_pago_aliado_habilitado_devuelve_datos(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    ok = sqlite_db.habilitar_pago_manual_aliado("A0001", "ADMIN001")
    assert ok.get("status") == "success"
    resp = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert resp.status_code == 200
    metodos = resp.get_json()["metodos"]
    assert metodos["habilitado"] is True
    assert metodos["bizum_num"] == _BIZUM_FAKE
    assert metodos["iban"] == _IBAN_FAKE


def test_habilitar_deshabilitar_sin_admin_es_401(client):
    r1 = client.post("/api/admin/metodos-pago/aliados/A0001/habilitar")
    r2 = client.post("/api/admin/metodos-pago/aliados/A0001/deshabilitar")
    assert r1.status_code == 401
    assert r2.status_code == 401


def test_habilitar_sin_iban_ni_bizum_es_400(client, sqlite_db, session_headers):
    resp = client.post(
        "/api/admin/metodos-pago/aliados/A0001/habilitar",
        headers=_admin_headers(session_headers),
        json={},
    )
    assert resp.status_code == 400
    assert resp.get_json().get("status") == "error"


def test_habilitar_listar_y_deshabilitar_allowlist(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    headers = _admin_headers(session_headers)
    hab = client.post(
        "/api/admin/metodos-pago/aliados/A0001/habilitar",
        headers=headers,
        json={},
    )
    assert hab.status_code == 200
    listed = client.get("/api/admin/metodos-pago/aliados", headers=headers)
    assert listed.status_code == 200
    aliados = listed.get_json()["aliados"]
    assert any(a["aliado_codigo"] == "A0001" for a in aliados)

    des = client.post(
        "/api/admin/metodos-pago/aliados/A0001/deshabilitar",
        headers=headers,
        json={},
    )
    assert des.status_code == 200
    listed2 = client.get("/api/admin/metodos-pago/aliados", headers=headers)
    aliados2 = listed2.get_json()["aliados"]
    assert all(a["aliado_codigo"] != "A0001" for a in aliados2)

    resp = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert resp.get_json()["metodos"]["habilitado"] is False
    assert resp.get_json()["metodos"]["iban"] is None
