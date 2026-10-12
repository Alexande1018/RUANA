"""Admin sin lista de permisos no hereda el conjunto completo.

El admin principal conserva el acceso porque su ficha trae
leer, escribir, eliminar y configurar de forma explícita
(el mismo mecanismo que el código histórico 7772735). Una lista
vacía, o la ausencia de lista, no concede ningún permiso.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core import db_manager as db_module
from core.admin_auth import hash_password
from RUANA.web import app as app_module

WEB = Path(__file__).resolve().parents[1] / "web"
PERMISOS_COMPLETOS = ["leer", "escribir", "eliminar", "configurar"]


def _sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(
            postgres_configured=False,
            database_url="",
            public_app_url="http://localhost:5000",
            stripe_secret_key="sk_test_x",
            stripe_webhook_secret="whsec_test",
        ),
    )
    return db_module.DBManager(str(tmp_path / "ruana_permisos_admin.db"))


def _ficha(tmp_path, monkeypatch, admins):
    path = tmp_path / "admin_permisos.json"
    path.write_text(
        json.dumps({"version": 1, "admins": admins}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUANA_ADMIN_USE_SECRET_MANAGER", "0")
    monkeypatch.setenv("RUANA_ADMIN_CREDENTIALS_PATH", str(path))
    monkeypatch.delenv("RUANA_ADMIN_CREDENTIALS_JSON", raising=False)


def test_admin_sin_permisos_no_accede_y_principal_si(client, tmp_path, monkeypatch, session_headers):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _ficha(
        tmp_path,
        monkeypatch,
        {
            "SINLISTA": {
                "nombre": "Admin sin lista",
                "activo": True,
                "permisos": [],
                "password_hash": "x",
            },
            "PRINCIPAL": {
                "nombre": "Admin principal",
                "activo": True,
                "permisos": PERMISOS_COMPLETOS,
                "password_hash": hash_password("clave-principal-1"),
            },
        },
    )

    vacio = session_headers("admin", "SINLISTA", permisos=[])
    me_vacio = client.get("/api/admin/me", headers=vacio)
    assert me_vacio.status_code == 200
    assert me_vacio.get_json()["permisos"] == []
    dash_vacio = client.get("/api/admin/financial/dashboard", headers=vacio)
    assert dash_vacio.status_code == 403
    escritura_vacia = client.post("/api/admin/rechazar-aliado", headers=vacio, json={})
    assert escritura_vacia.status_code == 403

    # Sesión sin lista, pero la ficha del principal sí tiene permisos asignados.
    principal = session_headers("admin", "PRINCIPAL", permisos=[])
    me_principal = client.get("/api/admin/me", headers=principal)
    assert me_principal.status_code == 200
    assert me_principal.get_json()["permisos"] == PERMISOS_COMPLETOS
    dash_principal = client.get("/api/admin/financial/dashboard", headers=principal)
    assert dash_principal.status_code == 200
    assert dash_principal.get_json().get("status") == "success"
    escritura_principal = client.post("/api/admin/rechazar-aliado", headers=principal, json={})
    assert escritura_principal.status_code == 400

    # Login normal: la sesión ya lleva la lista explícita de la ficha.
    login = client.post(
        "/api/admin/validar",
        json={"codigo": "PRINCIPAL", "password": "clave-principal-1"},
    )
    assert login.status_code == 200
    cuerpo = login.get_json()
    assert cuerpo["permisos"] == PERMISOS_COMPLETOS
    sesion = {app_module.RUANA_SESSION_HEADER: cuerpo["session_id"]}
    dash_login = client.get("/api/admin/financial/dashboard", headers=sesion)
    assert dash_login.status_code == 200


def test_admin_sin_clave_permisos_no_hereda_conjunto_completo(client, tmp_path, monkeypatch, session_headers):
    _ficha(
        tmp_path,
        monkeypatch,
        {
            "SINCLAVE": {
                "nombre": "Admin sin clave de permisos",
                "activo": True,
                "password_hash": "x",
            }
        },
    )
    headers = session_headers("admin", "SINCLAVE", permisos=[])
    resp = client.get("/api/admin/me", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["permisos"] == []
    dash = client.get("/api/admin/financial/dashboard", headers=headers)
    assert dash.status_code == 403


def test_panel_admin_no_concede_permisos_si_faltan_en_la_respuesta():
    js = (WEB / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")
    assert "['leer', 'escribir', 'eliminar', 'configurar']" not in js
    assert '["leer", "escribir", "eliminar", "configurar"]' not in js
