"""Invitación por oficio faltante: reutiliza invitaciones_oficio existentes."""
from pathlib import Path
from types import SimpleNamespace
import re

import pytest

from core import db_manager as db_module
from core.db_constants import RUANA_CODIGO_INVITACION_REGEX
from core.services import invitacion_service
from RUANA.web import app as app_module
from web.blueprints import invitacion_bp as invitacion_bp_mod


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_invitacion_oficio.db"))


def _session_headers(codigo):
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo=codigo,
        expires_at=9999999999,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def _crear_activo(db, codigo, oficio="Electricidad", cp="28001", score=50):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=score,
        especializacion="Averías",
    )
    assert result["status"] == "success"
    return result


def _oficio_faltante(db, grupo_id, excluir="Electricidad"):
    info = db.info_grupo_para_panel(grupo_id)
    faltantes = list(info.get("oficios_faltantes") or [])
    for oficio in faltantes:
        if oficio and oficio != excluir:
            return oficio
    raise AssertionError("El grupo no tiene oficios faltantes para el test")


def _contar_invitaciones_oficio(db, grupo_id=None, oficio=None):
    conn = db._connect()
    cur = conn.cursor()
    sql = "SELECT codigo, grupo_id, oficio, estado FROM invitaciones_oficio"
    params = []
    clauses = []
    if grupo_id is not None:
        clauses.append("grupo_id = ?")
        params.append(grupo_id)
    if oficio is not None:
        clauses.append("oficio = ?")
        params.append(oficio)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def test_endpoint_sigue_delegando_en_generar_invitacion_oficio():
    src = Path(invitacion_bp_mod.__file__).read_text(encoding="utf-8")
    assert "invitacion_service.generar_invitacion_oficio" in src
    assert "db.generar_invitacion_oficio(" not in src
    assert callable(invitacion_service.generar_invitacion_oficio)


def test_clic_oficio_faltante_genera_invitacion(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "81001")
    aliado = sqlite_db.obtener_aliado_por_codigo("81001")
    oficio = _oficio_faltante(sqlite_db, aliado["grupo_id"])

    resp = client.post(
        "/api/generar-invitacion",
        headers=_session_headers("81001"),
        json={"oficio": oficio},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["oficio"] == oficio
    assert data["codigo"]
    assert re.match(RUANA_CODIGO_INVITACION_REGEX, data["codigo"])
    assert data["registro_url"].endswith("/invite.html?codigo=" + data["codigo"])
    assert "3 puntos de score" in data["mensaje_compartir"]
    assert data["codigo"] in data["mensaje_compartir"]
    assert oficio in data["mensaje_compartir"]
    assert "invite.html?codigo=" in data["registro_url"]

    rows = _contar_invitaciones_oficio(sqlite_db, aliado["grupo_id"], oficio)
    assert len(rows) == 1
    assert rows[0][3] == "pendiente"


def test_reutiliza_invitacion_pendiente_sin_duplicar(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "81002")
    aliado = sqlite_db.obtener_aliado_por_codigo("81002")
    oficio = _oficio_faltante(sqlite_db, aliado["grupo_id"])
    headers = _session_headers("81002")

    first = client.post(
        "/api/generar-invitacion",
        headers=headers,
        json={"oficio": oficio},
    )
    second = client.post(
        "/api/aliado/generar-invitacion",
        headers=headers,
        json={"oficio": oficio},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    codigo = first.get_json()["codigo"]
    assert second.get_json()["codigo"] == codigo

    rows = _contar_invitaciones_oficio(sqlite_db, aliado["grupo_id"], oficio)
    assert len(rows) == 1


def test_oficio_no_faltante_no_genera_invitacion(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "81003", oficio="Electricidad")

    resp = client.post(
        "/api/generar-invitacion",
        headers=_session_headers("81003"),
        json={"oficio": "Electricidad"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "faltantes" in (data.get("message") or "").lower()
    assert _contar_invitaciones_oficio(sqlite_db) == []


def test_oficio_inexistente_no_genera_invitacion(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "81004")

    resp = client.post(
        "/api/generar-invitacion",
        headers=_session_headers("81004"),
        json={"oficio": "OficioInventadoXYZ"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"
    assert _contar_invitaciones_oficio(sqlite_db) == []


def test_sin_sesion_no_genera_invitacion(client):
    resp = client.post("/api/generar-invitacion", json={"oficio": "Electricidad"})
    assert resp.status_code == 401


def test_validar_y_consumir_invitacion_oficio_sigue_funcionando(
    client, sqlite_db, monkeypatch
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "54321")
    _crear_activo(sqlite_db, "81005", score=50)
    aliado = sqlite_db.obtener_aliado_por_codigo("81005")
    oficio = _oficio_faltante(sqlite_db, aliado["grupo_id"])

    gen = client.post(
        "/api/generar-invitacion",
        headers=_session_headers("81005"),
        json={"oficio": oficio},
    )
    assert gen.status_code == 200
    codigo = gen.get_json()["codigo"]
    assert sqlite_db.obtener_aliado_por_codigo("81005")["score"] == 50

    validacion = client.get(f"/api/validar-invitacion?codigo={codigo}")
    assert validacion.status_code == 200
    valid_data = validacion.get_json()
    assert valid_data["status"] == "success"
    assert valid_data["invitacion"]["codigo"] == codigo
    assert valid_data["invitacion"]["oficio"] == oficio

    register = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Nuevo Oficio",
            "marca": "Marca Nueva",
            "oficio": oficio,
            "oficio_principal": oficio,
            "especializacion": oficio,
            "codigo_postal": "28001",
            "email": "nuevo.oficio@example.com",
            "telefono": "+34600987654",
            "codigo_invitacion": codigo,
            "acepta_privacidad_y_terminos": True,
        },
    )
    assert register.status_code == 201
    nuevo_codigo = register.get_json()["codigo"]
    assert nuevo_codigo != codigo
    assert nuevo_codigo == "54321"

    invitador = sqlite_db.obtener_aliado_por_codigo("81005")
    assert int(invitador["score"]) == 50 + sqlite_db.REGLA9_DELTA

    rows = _contar_invitaciones_oficio(sqlite_db, aliado["grupo_id"], oficio)
    assert len(rows) == 1
    assert rows[0][3] == "usado"

    reused = client.get(f"/api/validar-invitacion?codigo={codigo}")
    assert reused.status_code == 404


def test_tras_consumir_se_puede_generar_otro_codigo_si_sigue_faltante(
    sqlite_db,
):
    _crear_activo(sqlite_db, "81006", oficio="Electricidad", score=50)
    aliado = sqlite_db.obtener_aliado_por_codigo("81006")
    oficio = _oficio_faltante(sqlite_db, aliado["grupo_id"])

    first = invitacion_service.generar_invitacion_oficio(sqlite_db, "81006", oficio)
    assert first["status"] == "success"
    codigo1 = first["codigo"]

    _crear_activo(sqlite_db, "81007", oficio="Electricidad", cp="08001", score=50)
    ok = invitacion_service.consumir_invitacion_oficio(sqlite_db, codigo1, "81007")
    assert ok is True
    assert invitacion_service.validar_invitacion_oficio(sqlite_db, codigo1) is None

    second = invitacion_service.generar_invitacion_oficio(sqlite_db, "81006", oficio)
    assert second["status"] == "success"
    assert second["codigo"] != codigo1
    rows = _contar_invitaciones_oficio(sqlite_db, aliado["grupo_id"], oficio)
    assert len(rows) == 2


def test_mensaje_compartir_invitacion_oficio_contrato():
    url = "https://ruana-4293f.web.app/invite.html?codigo=RUANA-1-FONTANERO-A1B2"
    msg = invitacion_service.mensaje_compartir_invitacion_oficio(
        "fontanero", "RUANA-1-FONTANERO-A1B2", url
    )
    assert msg.startswith("¿Conoces un fontanero?")
    assert "3 puntos de score" in msg
    assert "después de que tu registro como aliado haya sido confirmado" in msg
    assert "RUANA-1-FONTANERO-A1B2" in msg
    assert url in msg


def test_ui_oficios_faltantes_abre_modal_copiar_y_compartir():
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    inv_js = (root / "static" / "js" / "aliado-invitaciones-module.js").read_text(
        encoding="utf-8"
    )
    events_js = (root / "static" / "js" / "aliado-events-module.js").read_text(
        encoding="utf-8"
    )
    grupo_js = (root / "static" / "js" / "aliado-grupo-module.js").read_text(
        encoding="utf-8"
    )

    assert 'id="grupo-oficios-faltantes-wrap"' in aliado
    assert 'id="modal-invitacion-oficio"' in aliado
    assert "¿Conoces un" in aliado
    assert "Invítalo a formar parte de RUANA." in aliado
    assert "Entrégale este código de invitación:" in aliado
    assert 'id="btn-copiar-invitacion-oficio"' in aliado
    assert ">Copiar código<" in aliado
    assert 'id="btn-compartir-invitacion-oficio"' in aliado
    assert ">Compartir invitación<" in aliado
    assert 'id="btn-cerrar-invitacion-oficio"' in aliado

    assert "generarInvitacionOficio" in inv_js
    assert "/api/generar-invitacion" in inv_js
    assert "navigator.share" in inv_js
    assert "clipboard.writeText" in inv_js
    assert "invite.html?codigo=" in inv_js
    assert "3 puntos de score" in inv_js
    assert "compartirInvitacionOficio" in inv_js
    assert "host.generarInvitacionOficio(tag.dataset.oficio)" in events_js
    assert "host.compartirInvitacionOficio()" in events_js
    assert 'data-oficio=' in grupo_js
    assert "mod.compartirInvitacionOficio(this)" in aliado
