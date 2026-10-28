"""Regresión: códigos de invitación con basura al principio/final (p. ej. «ALC-IG`»)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services.invitacion_service import normalizar_codigo_invitacion
from RUANA.web import app as app_module

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@pytest.mark.parametrize(
    "entrada",
    [
        "ALC-IG",
        "ALC-IG`",
        "`ALC-IG`",
        "ALC-IG´",
        " alc-ig ",
        "\talc-ig\n",
        '"ALC-IG"',
        "'ALC-IG'",
        "‘ALC-IG’",
        "“ALC-IG”",
        "«ALC-IG»",
        "ALC-IG.",
        "ALC-IG,",
        "¡ALC-IG!",
        "(ALC-IG)",
        " «alc-ig`». ",
    ],
)
def test_normaliza_a_alc_ig(entrada):
    assert normalizar_codigo_invitacion(entrada) == "ALC-IG"


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("``", ""),
        ("47604`", "47604"),
        (" ruana-12-electricidad-ab12 ", "RUANA-12-ELECTRICIDAD-AB12"),
        ("A-B", "A-B"),  # el guion interior se respeta
    ],
)
def test_normaliza_otros_casos(entrada, esperado):
    assert normalizar_codigo_invitacion(entrada) == esperado


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana.db"))


def _admin_headers():
    session_id = app_module._ruana_session_create(
        tipo="admin",
        codigo="ADMIN001",
        expires_at=9999999999,
        permisos=["leer", "escribir"],
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def test_validar_y_registrar_con_backtick(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "54322")

    created = client.post(
        "/api/admin/invitacion-campanas",
        headers=_admin_headers(),
        json={"codigo": "ALC-IG", "nombre": "Instagram", "max_usos": 10},
    )
    assert created.status_code == 201

    for raw in ("ALC-IG%60", "%20alc-ig%20", "%22ALC-IG%22", "ALC-IG."):
        resp = client.get(f"/api/validar-invitacion?codigo={raw}")
        assert resp.status_code == 200, (raw, resp.get_json())
        assert resp.get_json()["invitacion"]["codigo"] == "ALC-IG"

    resp = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Persona Backtick",
            "marca": "Marca",
            "oficio": "Electricidad",
            "oficio_principal": "Electricidad",
            "codigo_postal": "28001",
            "email": "persona.backtick@example.com",
            "telefono": "+34600543211",
            "codigo_invitacion": "alc-ig`",
            "acepta_privacidad_y_terminos": True,
            "declara_mayoria_edad": True,
        },
    )
    assert resp.status_code == 201, resp.get_json()

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT usos_actuales FROM invitacion_campanas WHERE codigo = ?", ("ALC-IG",))
    assert cur.fetchone()[0] == 1
    conn.close()


@pytest.mark.parametrize("pagina", ["register.html", "invite.html", "index.html"])
def test_frontend_normaliza_codigo(pagina):
    html = (WEB_DIR / pagina).read_text(encoding="utf-8")
    assert "function normalizarCodigoInvitacion" in html
    assert "\\p{L}\\p{N}" in html
