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


def _session_headers(codigo):
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo=codigo,
        expires_at=9999999999,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def test_ally_invitation_places_referral_under_inviter_not_admin(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    invitador = sqlite_db.crear_aliado(
        codigo="11111",
        nombre="Aliado Invitador",
        marca="Marca Invitador",
        oficio="Electricidad",
        codigo_postal="28001",
        email="invitador@example.com",
        telefono="+34600111111",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert invitador["status"] == "success"
    assert invitador.get("estado") == "activo"
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")

    create_inv = client.post(
        "/api/invitaciones/crear",
        headers=_session_headers("11111"),
        json={"zona": "28001"},
    )
    assert create_inv.status_code == 201
    codigo_invitacion = create_inv.get_json()["codigo"]

    register = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Persona Invitada Por Aliado",
            "marca": "Marca Invitada",
            "oficio": "Electricidad",
            "oficio_principal": "Electricidad",
            "especializacion": "Averias y reparaciones electricas",
            "codigo_postal": "28001",
            "email": "invitada.aliado@example.com",
            "telefono": "+34600999901",
            "codigo_invitacion": codigo_invitacion,
        },
    )
    assert register.status_code == 201
    codigo_referido = register.get_json()["codigo"]

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT codigo_invitador, origen FROM referidos WHERE codigo_referido = ?",
        (codigo_referido,),
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "11111"
    assert row[1] == "aliado"


def test_orphan_active_ally_is_assigned_to_admin_on_sync(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    directo = sqlite_db.crear_aliado(
        codigo="22222",
        nombre="Aliado Directo",
        marca="Marca Directa",
        oficio="Electricidad",
        codigo_postal="28001",
        email="directo@example.com",
        telefono="+34600222222",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert directo["status"] == "success"

    sync = sqlite_db.sincronizar_referidos_completo()
    assert sync["huerfanos"] >= 1

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT codigo_invitador, origen FROM referidos WHERE codigo_referido = ?",
        ("22222",),
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "RUANA-ADMIN"
    assert row[1] == "huerfano"


def test_all_active_allies_participate_in_network_after_sync(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    for codigo, nombre in [("33333", "Uno"), ("44444", "Dos")]:
        result = sqlite_db.crear_aliado(
            codigo=codigo,
            nombre=nombre,
            marca="Marca",
            oficio="Electricidad",
            codigo_postal="28001",
            email=f"{codigo}@example.com",
            telefono=f"+34600{codigo}",
            estado="activo",
            score=50,
            especializacion="Averías y reparaciones eléctricas",
        )
        assert result["status"] == "success"

    sqlite_db.sincronizar_referidos_completo()
    resumen = sqlite_db.obtener_resumen_referidos_red()

    assert resumen["total_aliados_activos"] == 2
    assert resumen["aliados_fuera_red"] == 0
    assert resumen["total_nodos"] >= 3
