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
    "campo,fragmento",
    [
        ("nombre", "Campo requerido: nombre"),
        ("email", "Campo requerido: email"),
        ("telefono", "Campo requerido: telefono"),
        ("oficio", "oficio principal es obligatorio"),
    ],
)
def test_registrar_rechaza_sin_campo_obligatorio(client, tmp_path, monkeypatch, campo, fragmento):
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
