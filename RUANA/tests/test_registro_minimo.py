"""Alta del paso 1: solo obligatorios. Marca y descripción no se exigen."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module

WEB = Path(__file__).resolve().parents[1] / "web"


def _sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_registro_minimo.db"))


def _payload(**extra):
    data = {
        "nombre": "Ana Minima",
        "codigo_postal": "03001",
        "oficio": "Electricidad",
        "email": "ana.minima@example.com",
        "telefono": "+34600111301",
        "acepta_privacidad_y_terminos": True,
        "declara_mayoria_edad": True,
    }
    data.update(extra)
    return data


def test_register_paso1_muestra_solo_obligatorios_y_gate():
    html = (WEB / "register.html").read_text(encoding="utf-8")
    for marker in (
        'id="nombre"',
        'id="codigo-postal"',
        'id="oficio-principal"',
        'id="email"',
        'id="telefono-nacional"',
        'id="condiciones"',
        'id="mayoria_edad"',
        "params.get('codigo') || params.get('code')",
        "validateInviteCode",
        "art. 13 RGPD",
        "/politica-privacidad.html",
        "/terminos.html",
        "pin_setup_required",
    ):
        assert marker in html
    assert 'id="marca"' not in html
    assert 'id="descripcion"' not in html
    assert "marca:" not in html
    assert "descripcion:" not in html
    assert 'id="condiciones" checked' not in html
    assert 'id="mayoria_edad" checked' not in html
    assert "<ul>" not in html.split('id="register-legal-layer"', 1)[1].split("</p>", 1)[0]


def test_registrar_valido_solo_obligatorios_sin_marca_ni_descripcion(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "73101")
    payload = _payload()
    assert "marca" not in payload
    assert "descripcion" not in payload
    assert "descripcion_servicio" not in payload
    resp = client.post("/api/aliados/registrar", json=payload)
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["status"] == "success"
    assert body["codigo"] == "73101"
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT nombre, marca, oficio, codigo_postal, email, telefono, descripcion_servicio
        FROM aliados WHERE codigo = ?
        """,
        ("73101",),
    )
    row = cursor.fetchone()
    conn.close()
    assert row[0] == "Ana Minima"
    assert row[1] == ""
    assert row[2] == "Electricidad"
    assert row[3] == "03001"
    assert row[4] == "ana.minima@example.com"
    assert row[5] == "+34600111301"
    assert row[6] is None


def test_registrar_sin_consentimiento_devuelve_400(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    payload = _payload()
    payload.pop("acepta_privacidad_y_terminos")
    resp = client.post("/api/aliados/registrar", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "Política de Privacidad" in data["message"]


def test_registrar_sin_mayoria_edad_devuelve_400(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    payload = _payload()
    payload.pop("declara_mayoria_edad")
    resp = client.post("/api/aliados/registrar", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "mayor de 18" in data["message"]


@pytest.mark.parametrize(
    "campo,field,code,fragmento",
    [
        ("nombre", "nombre", "nombre_requerido", "El nombre es obligatorio"),
        ("email", "email", "email_requerido", "El email es obligatorio"),
        ("telefono", "telefono", "telefono_requerido", "El teléfono es obligatorio"),
        ("oficio", "oficio", "oficio_requerido", "oficio principal es obligatorio"),
    ],
)
def test_registrar_rechaza_sin_campo_obligatorio(client, tmp_path, monkeypatch, campo, field, code, fragmento):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    payload = _payload(email=f"sin.{campo}@example.com", telefono="+34600111399")
    payload.pop(campo)
    if campo == "oficio":
        payload.pop("oficio_principal", None)
    resp = client.post("/api/aliados/registrar", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert fragmento in data["message"]
    assert data.get("field") == field
    assert data.get("code") == code

def test_registrar_nombre_corto_devuelve_400_con_field(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.post("/api/aliados/registrar", json=_payload(nombre="Al"))
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data.get("field") == "nombre"
    assert data.get("code") == "nombre_corto"
    assert "3 caracteres" in data["message"]


def test_registrar_email_invalido_mensaje_legible(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.post("/api/aliados/registrar", json=_payload(email="no-es-email"))
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("field") == "email"
    assert data.get("code") == "email_invalido"
    assert "?" not in data["message"]
    assert "email válido" in data["message"]


def test_registrar_origen_invalido_devuelve_400(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.post(
        "/api/aliados/registrar",
        json=_payload(como_nos_conociste="Publicidad en radio"),
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("field") == "origen"
    assert data.get("code") == "origen_invalido"


def test_register_html_alinea_nombre_minimo_con_backend():
    html = (WEB / "register.html").read_text(encoding="utf-8")
    assert "nombre.length < 3" in html
    assert "result.field" in html
    assert "scrollIntoView" in html
    assert "nombre.length < 2" not in html


def test_registrar_email_duplicado_sin_pii(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "73111")
    first = client.post("/api/aliados/registrar", json=_payload(email="dup@example.com", telefono="+34600111401"))
    assert first.status_code == 201, first.get_json()
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "73112")
    second = client.post(
        "/api/aliados/registrar",
        json=_payload(nombre="Otra Persona", email="dup@example.com", telefono="+34600111402"),
    )
    assert second.status_code == 400
    data = second.get_json()
    assert data.get("field") == "email"
    assert data.get("code") == "email_duplicado"
    assert "dup@example.com" not in data["message"]

