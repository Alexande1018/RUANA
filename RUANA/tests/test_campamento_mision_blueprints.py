"""Misión Maestra: contratos de blueprints contactos_bp y auth_bp."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module
from web.blueprints.auth_bp import auth_bp
from web.blueprints.contactos_bp import contactos_bp


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_mision_bp.db"))


def test_contactos_bp_health(client):
    resp = client.get("/api/contactos/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "contactos"


def test_auth_bp_health(client):
    resp = client.get("/api/auth/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "auth"


def test_contactos_routes_exigen_sesion(client):
    for method, path in (
        ("post", "/api/contactos"),
        ("post", "/api/contactos/1/finalizar-chat"),
        ("post", "/api/contactos/1/finalizar_chat"),
        ("post", "/api/contactos/1/aceptar"),
        ("post", "/api/contactos/1/trabajo-en-progreso"),
        ("post", "/api/contactos/1/no-concretado"),
        ("post", "/api/contactos/1/en-conversacion"),
        ("post", "/api/contactos/1/declarar-importe"),
        ("get", "/api/contactos/abiertos/72001"),
        ("get", "/api/aliado/contactos-pago-pendiente"),
        ("get", "/api/contactos/1"),
        ("post", "/api/contactos/1/comprobante-apoyo"),
        ("post", "/api/contactos/1/impugnar-apoyo"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


def test_auth_sesion_exige_header(client):
    resp = client.get("/api/aliado/sesion")
    assert resp.status_code == 401


def test_blueprints_registrados_en_app(client):
    names = {bp.name for bp in client.application.blueprints.values()}
    assert contactos_bp.name in names
    assert auth_bp.name in names


def test_aliado_login_y_sesion_via_auth_bp(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(db_module, "get_db", lambda: sqlite_db)
    sqlite_db.crear_aliado(
        codigo="73001",
        nombre="Auth",
        marca="M",
        oficio="Fontanería",
        codigo_postal="28001",
        email="auth73001@test.com",
        telefono="+34613000001",
        estado="activo",
        score=50,
    )
    resp = client.post("/api/aliado/login", json={"codigo": "73001"})
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data.get("status") == "success"
    assert data.get("codigo") == "73001"
    assert data.get("session_id")

    headers = {app_module.RUANA_SESSION_HEADER: data["session_id"]}
    sesion = client.get("/api/aliado/sesion", headers=headers)
    assert sesion.status_code == 200
    assert sesion.get_json().get("codigo") == "73001"


def test_contactos_abiertos_con_sesion(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(db_module, "get_db", lambda: sqlite_db)
    sqlite_db.crear_aliado(
        codigo="74001",
        nombre="Cont",
        marca="M",
        oficio="Fontanería",
        codigo_postal="28001",
        email="cont74001@test.com",
        telefono="+34614000001",
        estado="activo",
        score=50,
    )
    headers = session_headers("aliado", "74001")
    resp = client.get("/api/contactos/abiertos/74001", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data.get("status") == "success"
    assert isinstance(data.get("contactos"), list)
