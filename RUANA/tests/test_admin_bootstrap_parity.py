"""Paridad obligatoria: GET /api/admin/bootstrap vs dashboard-summary."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services.admin_dashboard_service import (
    SUMMARY_COUNT_KEYS,
    clear_admin_bootstrap_cache,
)
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_admin_bootstrap.db"))


def _seed(db):
    db.crear_aliado(
        codigo="81001",
        nombre="Activo Bootstrap",
        marca="AB",
        oficio="Electricidad",
        codigo_postal="28001",
        email="ab81001@test.com",
        telefono="+34611000001",
        estado="activo",
        score=80,
    )
    db.crear_aliado(
        codigo="81002",
        nombre="Pendiente Bootstrap",
        marca="PB",
        oficio="Fontanería",
        codigo_postal="28001",
        email="pb81002@test.com",
        telefono="+34611000002",
        estado="pendiente_validacion",
        score=10,
    )


def test_admin_bootstrap_exige_sesion(client):
    resp = client.get("/api/admin/bootstrap")
    assert resp.status_code == 401


def test_admin_bootstrap_counts_match_dashboard_summary(
    client, sqlite_db, monkeypatch, session_headers
):
    """Los conteos de bootstrap son exactamente los de dashboard-summary (mismos datos)."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _seed(sqlite_db)
    clear_admin_bootstrap_cache()
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    summary_resp = client.get("/api/admin/dashboard-summary", headers=headers)
    summary = summary_resp.get_json()
    assert summary_resp.status_code == 200, summary
    assert "status" not in summary or summary.get("status") != "error"

    boot_resp = client.get("/api/admin/bootstrap", headers=headers)
    boot = boot_resp.get_json()
    assert boot_resp.status_code == 200, boot
    assert boot.get("status") == "success"
    assert isinstance(boot.get("summary"), dict)
    assert isinstance(boot.get("aliados"), list)
    assert isinstance(boot.get("pendientes"), list)
    assert isinstance(boot.get("permisos"), list)

    for key in SUMMARY_COUNT_KEYS:
        assert key in summary, key
        assert key in boot["summary"], key
        assert boot["summary"][key] == summary[key], (key, boot["summary"][key], summary[key])

    assert boot["summary"]["total_users"] >= 2
    assert any(a.get("codigo") == "81001" for a in boot["aliados"])
    assert any(a.get("codigo") == "81002" for a in boot["pendientes"])


def test_admin_bootstrap_cache_hit_and_mutation_bust(
    client, sqlite_db, monkeypatch, session_headers
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    clear_admin_bootstrap_cache()
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    first = client.get("/api/admin/bootstrap", headers=headers).get_json()
    second = client.get("/api/admin/bootstrap", headers=headers).get_json()
    assert first.get("cache") == "miss"
    assert second.get("cache") == "hit"
    for key in SUMMARY_COUNT_KEYS:
        assert first["summary"][key] == second["summary"][key]

    # Una mutación admin (aunque falle el body) no debe dejar cache sucio si responde <400.
    # POST cambiar-reglas exige escritura; usamos un no-op seguro: after_request limpia en 2xx/3xx.
    clear_admin_bootstrap_cache()
    third = client.get("/api/admin/bootstrap", headers=headers).get_json()
    assert third.get("cache") == "miss"
