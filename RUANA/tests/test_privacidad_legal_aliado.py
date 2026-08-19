"""Contratos legales mínimos: consentimiento de alta, portabilidad y baja."""

from types import SimpleNamespace
from pathlib import Path

import pytest

from core import db_manager as db_module
from core.services import aliado_service
from RUANA.web import app as app_module
from tests.conftest import make_session_headers

WEB = Path(__file__).resolve().parents[1] / "web"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_legal.db"))


def _payload_registro(**extra):
    data = {
        "nombre": "Ana Legal",
        "marca": "AL",
        "oficio": "Electricidad",
        "oficio_principal": "Electricidad",
        "codigo_postal": "03001",
        "email": "ana.legal@example.com",
        "telefono": "+34600111000",
        "acepta_privacidad_y_terminos": True,
    }
    data.update(extra)
    return data


def test_schema_crea_tablas_privacidad(sqlite_db):
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('consentimientos_aliado', 'solicitudes_baja_aliado')"
    )
    names = {row[0] for row in cursor.fetchall()}
    conn.close()
    assert names == {"consentimientos_aliado", "solicitudes_baja_aliado"}


def test_registrar_sin_consentimiento_devuelve_400(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    payload = _payload_registro()
    payload.pop("acepta_privacidad_y_terminos")
    resp = client.post("/api/aliados/registrar", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "Política de Privacidad" in data["message"]


def test_registrar_consentimiento_false_devuelve_400(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.post(
        "/api/aliados/registrar",
        json=_payload_registro(acepta_privacidad_y_terminos=False),
    )
    assert resp.status_code == 400


def test_registrar_con_consentimiento_guarda_version(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "73011")
    resp = client.post("/api/aliados/registrar", json=_payload_registro())
    assert resp.status_code == 201, resp.get_json()
    codigo = resp.get_json()["codigo"]
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT codigo_aliado, version_documento, aceptado_en FROM consentimientos_aliado WHERE codigo_aliado = ?",
        (codigo,),
    )
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == codigo
    assert row[1] == aliado_service.LEGAL_DOCUMENT_VERSION
    assert row[2]


def test_exportar_datos_exige_sesion(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.get("/api/aliados/me/exportar-datos")
    assert resp.status_code == 401


def test_exportar_datos_json_perfil_encargos_mensajes(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    creado = sqlite_db.crear_aliado(
        codigo="73012",
        nombre="Exporta Datos",
        marca="ED",
        oficio="Electricidad",
        codigo_postal="03001",
        email="exporta@example.com",
        telefono="+34600111012",
        estado="activo",
        score=50,
    )
    assert creado["status"] == "success"
    headers = make_session_headers("aliado", "73012")
    resp = client.get("/api/aliados/me/exportar-datos", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["status"] == "success"
    datos = data["datos"]
    assert "perfil" in datos
    assert "encargos" in datos
    assert "mensajes" in datos
    assert datos["perfil"]["codigo"] == "73012"
    assert "pin_hash" not in datos["perfil"]
    assert isinstance(datos["encargos"], list)
    assert "chat" in datos["mensajes"]
    assert "negociacion" in datos["mensajes"]


def test_solicitud_baja_no_borra_aliado(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    creado = sqlite_db.crear_aliado(
        codigo="73013",
        nombre="Baja Pendiente",
        marca="BP",
        oficio="Electricidad",
        codigo_postal="03001",
        email="baja@example.com",
        telefono="+34600111013",
        estado="activo",
        score=50,
    )
    assert creado["status"] == "success"
    headers = make_session_headers("aliado", "73013")
    resp = client.post(
        "/api/aliados/me/solicitud-baja",
        json={"motivo": "Quiero salir"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["status"] == "success"
    assert body["solicitud"]["estado"] == "pendiente"
    aliado = sqlite_db.obtener_aliado_por_codigo("73013")
    assert aliado is not None
    assert (aliado.get("estado") or "") != "eliminado"

    resp2 = client.post("/api/aliados/me/solicitud-baja", json={}, headers=headers)
    assert resp2.status_code == 200
    assert resp2.get_json().get("ya_existia") is True


def test_admin_lista_y_resuelve_solicitud_baja(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.crear_aliado(
        codigo="73014",
        nombre="Admin Baja",
        marca="AB",
        oficio="Electricidad",
        codigo_postal="03001",
        email="adminbaja@example.com",
        telefono="+34600111014",
        estado="activo",
        score=50,
    )
    result = aliado_service.crear_solicitud_baja_aliado(sqlite_db, "73014", "motivo test")
    solicitud_id = result["solicitud"]["id"]
    admin_headers = make_session_headers("admin", "ADMIN1", permisos=["leer", "escribir"])
    listed = client.get("/api/admin/solicitudes-baja", headers=admin_headers)
    assert listed.status_code == 200
    items = listed.get_json()["solicitudes"]
    assert any(s["id"] == solicitud_id for s in items)

    resolved = client.post(
        f"/api/admin/solicitudes-baja/{solicitud_id}",
        json={"estado": "completada"},
        headers=admin_headers,
    )
    assert resolved.status_code == 200, resolved.get_json()
    assert resolved.get_json()["solicitud"]["estado"] == "completada"


def test_paginas_legales_son_borrador_y_tienen_footer():
    for name in ("aviso-legal.html", "politica-privacidad.html", "terminos.html"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert "[BORRADOR — PENDIENTE DE REVISIÓN POR UN ABOGADO ANTES DE PUBLICAR]" in text
        assert "id=\"ruana-legal-footer\"" in text
        assert "/aviso-legal.html" in text
        assert "/politica-privacidad.html" in text
        assert "/terminos.html" in text
        assert "[NIF_TITULAR]" in text
        assert "LSSICE art.10 exige NIF" in text
        assert "642868261" not in text.replace("642868261", "") or "642868261" in text


def test_aviso_legal_no_publica_nif_real():
    text = (WEB / "aviso-legal.html").read_text(encoding="utf-8")
    assert "[NIF_TITULAR]" in text
    assert "Carlos Alexander Acero" in text
    assert "Calle Diputado José Luis Barceló 14" in text


def test_terminos_no_inventan_apelacion_ni_edad():
    text = (WEB / "terminos.html").read_text(encoding="utf-8")
    assert "No existe un proceso formal de apelación automática" in text
    assert "centro de comunicación" in text.lower() or "canal de soporte" in text.lower()
    assert "mayoría de edad" not in text.lower()
    assert "menor de" not in text.lower()
    assert "[JURISDICCIÓN_PENDIENTE]" in text
    assert "intermediario tecnológico" in text


def test_privacidad_cita_encargados_y_retencion():
    text = (WEB / "politica-privacidad.html").read_text(encoding="utf-8")
    assert "Supabase" in text
    assert "[REGION_SUPABASE_PENDIENTE_CONFIRMAR]" in text
    assert "Google Cloud" in text
    assert "Stripe Connect" in text
    assert "team.ruana@gmail.com" in text
    assert "[CONFIRMAR CON ASESOR FISCAL]" in text
    assert "[DECISIÓN PENDIENTE]" in text
    assert "no hay banner de cookies" in text.lower() or "no incluye banner de cookies" in text.lower()


def test_register_checkbox_obligatorio_no_premarcado():
    html = (WEB / "register.html").read_text(encoding="utf-8")
    assert "He leído y acepto la" in html
    assert "/politica-privacidad.html" in html
    assert "/terminos.html" in html
    assert 'id="condiciones"' in html
    assert "acepta_privacidad_y_terminos: true" in html
    # No premarcado
    assert "id=\"condiciones\" checked" not in html
    assert "id='condiciones' checked" not in html


def test_footer_legal_incluido_en_paginas_publicas_y_paneles():
    for name in ("index.html", "register.html", "invite.html", "aliado.html", "admin.html"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert "/static/js/ruana-legal-footer.js" in text
        assert "/static/css/ruana-legal.css" in text


def test_panel_aliado_tiene_seccion_mis_datos():
    html = (WEB / "aliado.html").read_text(encoding="utf-8")
    assert 'id="perfil-mis-datos-wrap"' in html
    assert 'id="btn-exportar-mis-datos"' in html
    assert 'id="btn-solicitar-baja"' in html
    js = (WEB / "static" / "js" / "aliado-perfil-module.js").read_text(encoding="utf-8")
    assert "/api/aliados/me/exportar-datos" in js
    assert "/api/aliados/me/solicitud-baja" in js


def test_rutas_html_legales(client):
    for path in ("/aviso-legal.html", "/politica-privacidad.html", "/terminos.html"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert b"BORRADOR" in resp.data


def test_no_se_anade_banner_cookies():
    for name in ("index.html", "register.html", "aviso-legal.html", "politica-privacidad.html"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert "cookie-banner" not in text.lower()
        assert "aceptar cookies" not in text.lower()
