"""Tests de contacto soporte desde pantalla de acceso (sin sesión)."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module
from web.limiter import limiter


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "soporte_acceso.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    return db


@pytest.fixture(autouse=True)
def disable_rate_limit():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def _crear_aliado(db, codigo: str, email: str):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=email,
        telefono=f"+346000{codigo}",
        estado="activo",
        score=50,
    )
    assert result["status"] == "success"
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()


def test_contacto_acceso_por_email(client, sqlite_db):
    _crear_aliado(sqlite_db, "82001", "soporte@test.ruana")
    resp = client.post(
        "/api/soporte/contacto-acceso",
        json={
            "email": "soporte@test.ruana",
            "asunto": "Sin acceso al email",
            "mensaje": "No puedo recibir correos de recuperación.",
            "categoria": "ayuda",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json().get("status") == "success"


def test_contacto_acceso_cuenta_desconocida(client, sqlite_db):
    resp = client.post(
        "/api/soporte/contacto-acceso",
        json={
            "email": "nadie@test.ruana",
            "mensaje": "Necesito ayuda",
        },
    )
    assert resp.status_code == 400
