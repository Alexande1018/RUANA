"""Invitaciones por oficio desde el catálogo de oficios faltantes del panel aliado."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import invitacion_service
from RUANA.web import app as app_module


OFICIO_INVITADOR = "Electricidad"
OFICIO_FALTANTE = "Fontanería y fontanería-gas"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "invitacion_oficio_faltantes.db"))


def _session_headers(codigo):
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo=codigo,
        expires_at=9999999999,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def _crear_invitador(db, codigo="81001"):
    result = db.crear_aliado(
        codigo=codigo,
        nombre="Aliado Invitador",
        marca="Marca",
        oficio=OFICIO_INVITADOR,
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo[-5:]}",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert result["status"] == "success"
    aliado = db.obtener_aliado_por_codigo(codigo)
    return codigo, aliado.get("grupo_id")


def _count_invitaciones_pendientes(db, grupo_id, oficio):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM invitaciones_oficio WHERE grupo_id = ? AND oficio = ? AND estado = 'pendiente'",
        (grupo_id, oficio),
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def _score(db, codigo):
    return int(db.obtener_aliado_por_codigo(codigo)["score"])


def test_generar_invitacion_oficio_faltante_via_endpoint(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    codigo, grupo_id = _crear_invitador(sqlite_db)

    resp = client.post(
        "/api/generar-invitacion",
        headers=_session_headers(codigo),
        json={"oficio": OFICIO_FALTANTE},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["codigo"].startswith(f"RUANA-{grupo_id}-")
    assert "registro_url" in data
    assert "invite.html?codigo=" in data["registro_url"]
    assert data["puntos_score_recompensa"] == sqlite_db.REGLA9_DELTA


def test_generar_invitacion_usa_servicio_existente(sqlite_db):
    codigo, _ = _crear_invitador(sqlite_db)
    result = invitacion_service.generar_invitacion_oficio(sqlite_db, codigo, OFICIO_FALTANTE)
    assert result["status"] == "success"
    assert result["codigo"].startswith("RUANA-")


def test_reutiliza_invitacion_pendiente_mismo_codigo(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    codigo, grupo_id = _crear_invitador(sqlite_db)
    headers = _session_headers(codigo)

    r1 = client.post(
        "/api/generar-invitacion",
        headers=headers,
        json={"oficio": OFICIO_FALTANTE},
    )
    r2 = client.post(
        "/api/generar-invitacion",
        headers=headers,
        json={"oficio": OFICIO_FALTANTE},
    )
    assert r1.get_json()["codigo"] == r2.get_json()["codigo"]
    assert _count_invitaciones_pendientes(sqlite_db, grupo_id, OFICIO_FALTANTE) == 1


def test_no_genera_duplicados_pendientes(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    codigo, grupo_id = _crear_invitador(sqlite_db)
    headers = _session_headers(codigo)

    for _ in range(3):
        resp = client.post(
            "/api/generar-invitacion",
            headers=headers,
            json={"oficio": OFICIO_FALTANTE},
        )
        assert resp.status_code == 200

    assert _count_invitaciones_pendientes(sqlite_db, grupo_id, OFICIO_FALTANTE) == 1


def test_oficio_no_faltante_rechazado(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    codigo, _ = _crear_invitador(sqlite_db)

    resp = client.post(
        "/api/generar-invitacion",
        headers=_session_headers(codigo),
        json={"oficio": OFICIO_INVITADOR},
    )
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_validar_y_consumir_invitacion_oficio_sigue_funcionando(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    codigo_invitador, _ = _crear_invitador(sqlite_db)
    headers = _session_headers(codigo_invitador)

    gen = client.post(
        "/api/generar-invitacion",
        headers=headers,
        json={"oficio": OFICIO_FALTANTE},
    )
    codigo_invitacion = gen.get_json()["codigo"]

    validar = client.get(f"/api/validar-invitacion?codigo={codigo_invitacion}")
    assert validar.status_code == 200
    inv = validar.get_json()["invitacion"]
    assert inv["oficio"] == OFICIO_FALTANTE

    register = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Fontanero Nuevo",
            "marca": "Marca F",
            "oficio": OFICIO_FALTANTE,
            "oficio_principal": OFICIO_FALTANTE,
            "especializacion": "Fontanería",
            "codigo_postal": "28001",
            "email": "fontanero.nuevo@example.com",
            "telefono": "+34600999801",
            "codigo_invitacion": codigo_invitacion,
            "acepta_privacidad_y_terminos": True,
        },
    )
    assert register.status_code == 201

    assert _score(sqlite_db, codigo_invitador) == 50 + sqlite_db.REGLA9_DELTA

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT estado FROM invitaciones_oficio WHERE codigo = ?",
        (codigo_invitacion,),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert (row[0] or "").lower() == "usado"

    validar_usado = client.get(f"/api/validar-invitacion?codigo={codigo_invitacion}")
    assert validar_usado.status_code == 404


def test_frontend_modal_compartir_y_copiar_wired():
    """El modal de invitación por oficio expone copiar y compartir en HTML y JS."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    inv_js = (root / "static" / "js" / "aliado-invitaciones-module.js").read_text(encoding="utf-8")
    events_js = (root / "static" / "js" / "aliado-events-module.js").read_text(encoding="utf-8")

    assert "¿Conoces un" in aliado
    assert 'id="btn-compartir-invitacion-oficio"' in aliado
    assert "Copiar código" in aliado
    assert "Compartir invitación" in aliado
    assert "compartirInvitacionOficio" in inv_js
    assert "buildMensajeCompartirInvitacionOficio" in inv_js
    assert "navigator.share" in inv_js
    assert "btn-compartir-invitacion-oficio" in events_js
    assert "compartirInvitacionOficio" in aliado
