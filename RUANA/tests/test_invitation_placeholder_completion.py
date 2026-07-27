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


def test_register_with_invitation_creates_distinct_personal_code(
    client, sqlite_db, monkeypatch
):
    """El código de invitación y el código personal tras registrarse deben ser distintos."""
    invitador = sqlite_db.crear_aliado(
        codigo="11111",
        nombre="Aliado Invitador",
        marca="",
        oficio="Electricidad",
        codigo_postal="",
        email="invitador@example.com",
        telefono="+34600111111",
        estado="activo",
        score=50,
    )
    assert invitador["status"] == "success"

    sqlite_db._registrar_invitacion("12345", invitador["id"])

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "99999")

    validation = client.get("/api/validar-invitacion?codigo=12345")
    assert validation.status_code == 200
    assert validation.get_json()["status"] == "success"

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
    assert data["codigo"] == "99999"
    assert data["codigo"] != "12345"

    assert _fetch_aliado(sqlite_db, "99999") is not None
    assert _fetch_aliado(sqlite_db, "12345") is None

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT usado FROM invitaciones WHERE codigo = ?", ("12345",))
    assert cursor.fetchone()[0] == 1
    conn.close()

    reused = client.get("/api/validar-invitacion?codigo=12345")
    assert reused.status_code == 404
    assert reused.get_json()["status"] == "error"


def test_legacy_placeholder_is_removed_after_registration(
    client, sqlite_db, monkeypatch
):
    """Placeholders legacy desaparecen del panel al completar el registro."""
    invitador = sqlite_db.crear_aliado(
        codigo="11111",
        nombre="Aliado Invitador",
        marca="",
        oficio="Electricidad",
        codigo_postal="",
        email="invitador@example.com",
        telefono="+34600111111",
        estado="activo",
        score=50,
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
        score=50,
    )
    assert placeholder["status"] == "success"
    sqlite_db._registrar_invitacion("12345", invitador["id"])

    # Antes del registro, el placeholder no debe listarse en control de aliados
    listado_antes = sqlite_db.listar_aliados()
    assert all(a["codigo"] != "12345" for a in listado_antes)
    pendientes = sqlite_db.listar_aliados_pendiente_validacion()
    assert all(a["codigo"] != "12345" for a in pendientes)

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
    assert data["codigo"] == "99999"
    assert data["codigo"] != "12345"

    assert _fetch_aliado(sqlite_db, "12345") is None
    aliado_nuevo = _fetch_aliado(sqlite_db, "99999")
    assert aliado_nuevo is not None
    assert aliado_nuevo["nombre"] == "Persona Invitada"
    assert aliado_nuevo["email"] == "persona.invitada@example.com"

    listado_despues = sqlite_db.listar_aliados()
    codigos = {a["codigo"] for a in listado_despues}
    assert "99999" in codigos
    assert "12345" not in codigos


def test_crear_invitacion_no_crea_placeholder_aliado(client, sqlite_db, monkeypatch, session_headers):
    invitador = sqlite_db.crear_aliado(
        codigo="11111",
        nombre="Aliado Invitador",
        marca="",
        oficio="Electricidad",
        codigo_postal="28001",
        email="invitador2@example.com",
        telefono="+34600111112",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert invitador["status"] == "success"
    # Garantizar estado activo para poder generar invitaciones
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", ("11111",))
    conn.commit()
    conn.close()

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_invitacion", lambda _db: "55555")

    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "28001"},
        headers=session_headers("aliado", "11111"),
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["codigo"] == "55555"
    assert data["tipo"] == "invitacion"

    assert _fetch_aliado(sqlite_db, "55555") is None
    assert sqlite_db.obtener_invitacion_pendiente("55555") is not None
    assert all(a["codigo"] != "55555" for a in sqlite_db.listar_aliados())
