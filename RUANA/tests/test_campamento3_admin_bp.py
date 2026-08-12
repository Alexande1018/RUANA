"""Campamento Base #3: contratos del blueprint admin (bloque dashboard)."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module
from web.blueprints.admin_bp import admin_bp


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_camp3_admin.db"))


def test_admin_bp_health(client):
    resp = client.get("/api/admin/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "admin"


def test_admin_dashboard_routes_exigen_sesion(client):
    for path in (
        "/api/admin/me",
        "/api/admin/health-metrics",
        "/api/admin/stats-24h",
        "/api/admin/invitaciones-recientes",
        "/api/admin/dashboard-summary",
        "/api/admin/suplentes-espera",
        "/api/admin/aliados-pendientes",
        "/api/admin/pending-users",
        "/api/admin/conversations",
        "/api/admin/competencias-activas",
        "/api/admin/negociaciones",
        "/api/admin/pagos-en-revision",
        "/api/admin/aliados-eliminados",
        "/api/admin/metodos-pago",
    ):
        resp = client.get(path)
        assert resp.status_code == 401, path


def test_admin_bp_registrado(client):
    names = {bp.name for bp in client.application.blueprints.values()}
    assert admin_bp.name in names


def test_admin_me_y_dashboard_summary_con_sesion(
    client, sqlite_db, monkeypatch, session_headers
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    resp_me = client.get("/api/admin/me", headers=headers)
    assert resp_me.status_code == 200
    assert isinstance(resp_me.get_json().get("permisos"), list)

    resp = client.get("/api/admin/dashboard-summary", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    for key in (
        "total_users",
        "active_users",
        "retadores",
        "suplentes",
        "en_riesgo",
        "solicitudes_activas",
        "oficios_ocupados",
        "grupos",
        "estado_sistema",
    ):
        assert key in data, key


def test_admin_suplentes_espera_y_pendientes_con_sesion(
    client, sqlite_db, monkeypatch, session_headers
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ADMIN001", permisos=["leer"])

    resp_s = client.get("/api/admin/suplentes-espera", headers=headers)
    data_s = resp_s.get_json()
    assert resp_s.status_code == 200, data_s
    assert data_s.get("status") == "success"
    assert "aliados" in data_s

    resp_p = client.get("/api/admin/aliados-pendientes", headers=headers)
    data_p = resp_p.get_json()
    assert resp_p.status_code == 200, data_p
    assert data_p.get("status") == "success"
    assert "aliados" in data_p
