"""Tests HTTP de rutas de negociación guiada (aceptar / cerrar)."""
from types import SimpleNamespace

import pytest

from RUANA.web import app as app_module
from core import db_manager as db_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_neg_api.db"))


def _crear_contacto(db):
    for i, (codigo, nombre) in enumerate((("91001", "Sol"), ("91002", "Pro"))):
        db.crear_aliado(
            codigo=codigo,
            nombre=nombre,
            marca="M",
            oficio="Fontanería",
            codigo_postal="28001",
            email=f"{codigo}@test.com",
            telefono=f"+3461000000{i}",
            estado="activo",
            score=50,
        )
    r = db.crear_contacto_ruana("91001", "91002", servicio="Grifo", motivo_contacto="Presupuesto")
    assert r["status"] == "success", r.get("message")
    return r["id"]


def test_negociacion_aceptar_y_cerrar_rutas(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _crear_contacto(sqlite_db)

    valores = {
        "servicio": "Grifo",
        "fecha": "2026-08-15",
        "hora": "10:00",
        "direccion": "Calle Mayor 1",
        "observaciones": "Acceso por portal B",
    }
    ok = sqlite_db.proponer_propuesta_completa_negociacion(cid, "91001", valores)
    assert ok["status"] == "success", ok.get("message")

    headers = session_headers("aliado", "91002")
    resp = client.post(
        f"/api/contactos/{cid}/negociacion/aceptar",
        json={"campo": "servicio"},
        headers=headers,
    )
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data.get("status") == "success", data.get("message")

    resp_cerrar = client.post(
        f"/api/contactos/{cid}/negociacion/cerrar",
        json={},
        headers=session_headers("aliado", "91001"),
    )
    data_cerrar = resp_cerrar.get_json()
    assert resp_cerrar.status_code == 200, data_cerrar
    assert data_cerrar.get("status") == "success", data_cerrar.get("message")
    assert data_cerrar.get("estado") == "cerrado_no_concretado"


def test_negociacion_ruta_inexistente_devuelve_404(client):
    resp = client.post("/api/contactos/999999/negociacion/aceptar", json={"campo": "servicio"})
    assert resp.status_code in (401, 404)
