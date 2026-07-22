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
    return db_module.DBManager(str(tmp_path / "ruana_linaje.db"))


def _session_headers(codigo):
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo=codigo,
        expires_at=9999999999,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def _crear_activo(db, codigo, nombre):
    result = db.crear_aliado(
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
    return result


def test_asignar_invitado_por_escribe_en_aliados(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo")

    ok = sqlite_db.asignar_invitado_por("22222", "11111", "aliado")
    assert ok is True

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT invitado_por_codigo, invitado_origen FROM aliados WHERE codigo = ?",
        ("22222",),
    )
    row = cur.fetchone()
    conn.close()
    assert row[0] == "11111"
    assert row[1] == "aliado"


def test_backfill_huerfanos_bajo_admin(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "33333", "Huerfano")

    stats = sqlite_db.backfill_invitado_por_linaje()
    assert stats["huerfanos"] >= 1

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT invitado_por_codigo, invitado_origen FROM aliados WHERE codigo = ?", ("33333",))
    row = cur.fetchone()
    conn.close()
    assert row[0] == "RUANA-ADMIN"
    assert row[1] == "huerfano"


def test_listar_hijos_y_linaje_api(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")

    admin_sid = app_module._ruana_session_create(
        tipo="admin",
        codigo="ADMIN001",
        expires_at=9999999999,
        permisos=["leer", "escribir"],
    )
    admin_headers = {app_module.RUANA_SESSION_HEADER: admin_sid}

    resp = client.get("/api/admin/aliados/22222/linaje", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["linaje"]["padre"]["codigo"] == "11111"
    assert data["linaje"]["hijos_count"] == 0

    resp2 = client.get("/api/aliado/linaje/hijos", headers=_session_headers("11111"))
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["status"] == "success"
    assert data2["total"] == 1
    assert data2["hijos"][0]["codigo"] == "22222"


def test_invitation_flow_sets_invitado_por(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "11111", "Invitador")
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
            "nombre": "Persona Invitada",
            "marca": "Marca Inv",
            "oficio": "Electricidad",
            "oficio_principal": "Electricidad",
            "especializacion": "Averias y reparaciones electricas",
            "codigo_postal": "28001",
            "email": "invitada.linaje@example.com",
            "telefono": "+34600999888",
            "codigo_invitacion": codigo_invitacion,
        },
    )
    assert register.status_code == 201
    codigo_referido = register.get_json()["codigo"]

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT invitado_por_codigo, invitado_origen FROM aliados WHERE codigo = ?",
        (codigo_referido,),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "11111"
    assert row[1] in ("aliado", "admin_invitacion", "")
