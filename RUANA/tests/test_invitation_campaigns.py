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
    return db_module.DBManager(str(tmp_path / "ruana.db"))


def _admin_headers():
    session_id = app_module._ruana_session_create(
        tipo="admin",
        codigo="ADMIN001",
        expires_at=9999999999,
        permisos=["leer", "escribir"],
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def test_admin_campaign_code_validates_and_is_consumed_on_registration(
    client, sqlite_db, monkeypatch
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "54321")

    create_response = client.post(
        "/api/admin/invitacion-campanas",
        headers=_admin_headers(),
        json={
            "codigo": "RUANA-TEST",
            "nombre": "Campana prueba",
            "codigo_postal": "28001",
            "max_usos": 1,
        },
    )

    assert create_response.status_code == 201
    create_data = create_response.get_json()
    assert create_data["status"] == "success"
    assert create_data["campana"]["codigo"] == "RUANA-TEST"
    assert create_data["campana"]["max_usos"] == 1
    assert create_data["registro_url"].endswith("/invite.html?codigo=RUANA-TEST")
    assert create_data["registro_url"].startswith("https://ruana-4293f.web.app/")

    validation = client.get("/api/validar-invitacion?codigo=RUANA-TEST")
    assert validation.status_code == 200
    validation_data = validation.get_json()
    assert validation_data["status"] == "success"
    assert validation_data["invitacion"]["tipo"] == "campana"
    assert validation_data["invitacion"]["codigo"] == "RUANA-TEST"
    assert validation_data["invitacion"]["usos_restantes"] == 1

    register_response = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Persona Campana",
            "marca": "Marca Campana",
            "oficio": "Electricidad",
            "oficio_principal": "Electricidad",
            "especializacion": "Averias y reparaciones electricas",
            "codigo_postal": "28001",
            "email": "persona.campana@example.com",
            "telefono": "+34600543210",
            "codigo_invitacion": "RUANA-TEST",
        },
    )

    assert register_response.status_code == 201
    register_data = register_response.get_json()
    assert register_data["status"] == "success"
    assert register_data["codigo"] == "54321"

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT usos_actuales FROM invitacion_campanas WHERE codigo = ?",
        ("RUANA-TEST",),
    )
    assert cursor.fetchone()[0] == 1
    conn.close()

    cursor = sqlite_db._connect().cursor()
    cursor.execute(
        "SELECT codigo_invitador FROM referidos WHERE codigo_referido = ?",
        ("54321",),
    )
    referido_row = cursor.fetchone()
    assert referido_row is not None
    assert referido_row[0] == "ADMIN001"
    conn.close()

    second_validation = client.get("/api/validar-invitacion?codigo=RUANA-TEST")
    assert second_validation.status_code == 404
    assert second_validation.get_json()["status"] == "error"


def test_admin_can_deactivate_campaign_code(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    create_response = client.post(
        "/api/admin/invitacion-campanas",
        headers=_admin_headers(),
        json={
            "codigo": "RUANA-OFF",
            "nombre": "Campana desactivable",
            "max_usos": 10,
        },
    )
    assert create_response.status_code == 201

    active_validation = client.get("/api/validar-invitacion?codigo=RUANA-OFF")
    assert active_validation.status_code == 200

    deactivate_response = client.post(
        "/api/admin/invitacion-campanas/RUANA-OFF/desactivar",
        headers=_admin_headers(),
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.get_json()["status"] == "success"

    inactive_validation = client.get("/api/validar-invitacion?codigo=RUANA-OFF")
    assert inactive_validation.status_code == 404
