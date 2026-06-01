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


def _fetch_aliado(db, codigo):
    conn = db._connect()
    conn.row_factory = db_module.sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM aliados WHERE codigo = ?", (codigo,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def test_register_with_placeholder_invitation_completes_existing_ally(
    client, sqlite_db, monkeypatch
):
    invitador = sqlite_db.crear_aliado(
        codigo="11111",
        nombre="Aliado Invitador",
        marca="",
        oficio="Electricidad",
        codigo_postal="",
        email="invitador@example.com",
        telefono="+34600111111",
        estado="activo",
        score=75,
    )
    assert invitador["status"] == "success"

    placeholder = sqlite_db.crear_aliado(
        codigo="12345",
        nombre="Nuevo Aliado - 12345",
        marca="",
        oficio="Pendiente",
        codigo_postal="28001",
        email="placeholder-12345@ruana.local",
        telefono="+34 600 12345",
        estado="pendiente_completar",
        score=75,
    )
    assert placeholder["status"] == "success"
    sqlite_db._registrar_invitacion("12345", invitador["id"])

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "99999")

    response = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Persona Invitada",
            "marca": "Marca Invitada",
            "oficio": "Electricidad",
            "oficio_principal": "Electricidad",
            "especializacion": "Averías y reparaciones eléctricas",
            "codigo_postal": "28001",
            "email": "persona.invitada@example.com",
            "telefono": "+34600999999",
            "codigo_invitacion": "12345",
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["codigo"] == "12345"

    aliado_actualizado = _fetch_aliado(sqlite_db, "12345")
    assert aliado_actualizado["nombre"] == "Persona Invitada"
    assert aliado_actualizado["email"] == "persona.invitada@example.com"
    assert aliado_actualizado["estado"] == "activo"
    assert _fetch_aliado(sqlite_db, "99999") is None

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT usado FROM invitaciones WHERE codigo = ?", ("12345",))
    assert cursor.fetchone()[0] == 1
    conn.close()

    validation = client.get("/api/validar-invitacion?codigo=12345")
    assert validation.status_code == 404
    assert validation.get_json()["status"] == "error"
