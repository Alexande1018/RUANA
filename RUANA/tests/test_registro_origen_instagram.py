"""Alta desde anuncios: campos opcionales, UTMs y código en /register."""

from types import SimpleNamespace
from pathlib import Path

from core import db_manager as db_module
from RUANA.web import app as app_module

WEB = Path(__file__).resolve().parents[1] / "web"


def _sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_origen.db"))


def _payload(**extra):
    data = {
        "nombre": "Ana Instagram",
        "oficio": "Electricidad",
        "oficio_principal": "Electricidad",
        "codigo_postal": "03001",
        "email": "ana.ig@example.com",
        "telefono": "+34600111001",
        "acepta_privacidad_y_terminos": True,
        "declara_mayoria_edad": True,
    }
    data.update(extra)
    return data


def _fila_origen(sqlite_db, codigo):
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT marca, descripcion_servicio, utm_source, utm_medium, utm_campaign, como_nos_conociste
        FROM aliados WHERE codigo = ?
        """,
        (codigo,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def test_register_html_lee_codigo_utm_y_campos_opcionales():
    html = (WEB / "register.html").read_text(encoding="utf-8")
    assert "params.get('codigo') || params.get('code')" in html
    assert "Anuncio en Instagram" in html
    assert "Marca personal / Nombre comercial (opcional)" in html
    assert "Descripción breve del servicio (opcional)" in html
    assert "ruana_utm" in html
    assert "Ese código no es válido o ya no está activo" in html
    assert "oficio-picker-list" in html
    assert "forwardToInvite" in html
    assert "window.location.href = '/invite'" in html
    assert 'class="btn-back"' in html
    assert "position: fixed" not in html.split("btn-back")[1].split("}")[0]


def test_invite_conserva_codigo_y_utms_hasta_register():
    html = (WEB / "invite.html").read_text(encoding="utf-8")
    assert "persistUtms" in html
    assert "ruana_utm" in html
    assert "return '/register'" in html
    assert "Ese código no es válido o ya no está activo" in html
    assert "window.location.href = 'register.html'" not in html


def test_schema_anade_columnas_origen(tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(aliados)")
    columnas = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert {"utm_source", "utm_medium", "utm_campaign", "como_nos_conociste"} <= columnas


def test_registrar_sin_marca_ni_descripcion(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "73021")
    resp = client.post("/api/aliados/registrar", json=_payload())
    assert resp.status_code == 201, resp.get_json()
    marca, descripcion, *_ = _fila_origen(sqlite_db, "73021")
    assert marca == ""
    assert descripcion is None


def test_registrar_guarda_utm_y_como_nos_conociste(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "73022")
    largo = "instagram-" + ("x" * 200)
    resp = client.post(
        "/api/aliados/registrar",
        json=_payload(
            email="ana.utm@example.com",
            telefono="+34600111002",
            utm_source=largo,
            utm_medium="cpc",
            utm_campaign="fase-inaugural",
            como_nos_conociste="anuncio en instagram",
        ),
    )
    assert resp.status_code == 201, resp.get_json()
    row = _fila_origen(sqlite_db, "73022")
    assert row[2] == largo[:100]
    assert row[3] == "cpc"
    assert row[4] == "fase-inaugural"
    assert row[5] == "Anuncio en Instagram"


def test_registrar_rechaza_como_nos_conociste_desconocido(client, tmp_path, monkeypatch):
    sqlite_db = _sqlite(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.post(
        "/api/aliados/registrar",
        json=_payload(como_nos_conociste="Anuncio en TikTok"),
    )
    assert resp.status_code == 400
    assert "Cómo conociste" in resp.get_json()["message"]
