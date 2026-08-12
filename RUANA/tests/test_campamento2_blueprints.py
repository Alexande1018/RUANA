"""Campamento Base #2: contratos de blueprints negociación / referidos."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module
from web.blueprints.negociacion_bp import negociacion_bp
from web.blueprints.referidos_bp import referidos_bp


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_camp2_bp.db"))


def test_negociacion_health_via_blueprint(client):
    resp = client.get("/api/negociacion/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "negociacion"


def test_negociacion_get_exige_sesion(client):
    resp = client.get("/api/contactos/1/negociacion")
    assert resp.status_code == 401


def test_referidos_aliado_exige_sesion(client):
    resp = client.get("/api/aliado/referidos")
    assert resp.status_code == 401


def test_referidos_admin_arbol_exige_sesion(client):
    resp = client.get("/api/admin/referidos/arbol")
    assert resp.status_code == 401


def test_blueprints_registrados_en_app(client):
    names = {bp.name for bp in client.application.blueprints.values()}
    assert negociacion_bp.name in names
    assert referidos_bp.name in names


def test_aliado_referidos_raiz_con_sesion(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(db_module, "get_db", lambda: sqlite_db)
    sqlite_db.crear_aliado(
        codigo="72001",
        nombre="Ref",
        marca="M",
        oficio="Fontanería",
        codigo_postal="28001",
        email="ref72001@test.com",
        telefono="+34612000001",
        estado="activo",
        score=50,
    )
    headers = session_headers("aliado", "72001")
    resp = client.get("/api/aliado/referidos/raiz", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data.get("status") == "success"
    assert data.get("modo") == "raiz"
    assert (data.get("nodo") or {}).get("codigo") == "72001"
