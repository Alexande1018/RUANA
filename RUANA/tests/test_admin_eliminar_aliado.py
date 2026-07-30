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
    return db_module.DBManager(str(tmp_path / "ruana_eliminar_aliado.db"))


def _admin_headers(permisos=None):
    session_id = app_module._ruana_session_create(
        tipo="admin",
        codigo="ADMIN001",
        expires_at=9999999999,
        permisos=permisos or ["leer", "escribir"],
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


def test_eliminar_perfil_activo_expulsa_aliado(sqlite_db):
    _crear_activo(sqlite_db, "90001", "Aliado Activo")

    result = sqlite_db.eliminar_perfil_aliado_admin("90001", motivo="Prueba admin")
    assert result["status"] == "success"
    assert result["accion"] == "expulsado"

    aliado = sqlite_db.obtener_aliado_por_codigo("90001")
    assert aliado["estado"] == "expulsado"
    assert aliado["email"] == "liberado+90001@ruana.invalid"
    assert aliado["telefono"] == "LIBERADO-90001"


def test_eliminar_perfil_libera_email_y_telefono_para_nuevo_registro(sqlite_db):
    email = "reutilizar@example.com"
    telefono = "+34600111222"
    sqlite_db.crear_aliado(
        codigo="90010",
        nombre="Aliado Reutilizable",
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=email,
        telefono=telefono,
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )

    eliminacion = sqlite_db.eliminar_perfil_aliado_admin("90010")
    assert eliminacion["status"] == "success"

    nuevo = sqlite_db.crear_aliado(
        codigo="90011",
        nombre="Nuevo Aliado",
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=email,
        telefono=telefono,
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert nuevo["status"] == "success"
    assert nuevo["email"] == email
    assert nuevo["telefono"] == telefono


def test_eliminar_perfil_rechaza_pendiente_validacion(sqlite_db):
    sqlite_db.crear_aliado(
        codigo="90002",
        nombre="Pendiente",
        marca="Marca",
        oficio="Fontanería",
        codigo_postal="28001",
        email="90002@example.com",
        telefono="+3460090002",
        estado="pendiente_validacion",
        score=50,
        especializacion="Reparaciones de fontanería",
    )

    result = sqlite_db.eliminar_perfil_aliado_admin("90002")
    assert result["status"] == "success"
    assert result["accion"] == "rechazado"
    aliado = sqlite_db.obtener_aliado_por_codigo("90002")
    assert aliado["estado"] == "rechazado"
    assert aliado["email"] == "liberado+90002@ruana.invalid"
    assert aliado["telefono"] == "LIBERADO-90002"


def test_eliminar_perfil_bloquea_sistema(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")

    result = sqlite_db.eliminar_perfil_aliado_admin("RUANA-ADMIN")
    assert result["status"] == "error"
    assert "sistema" in result["message"].lower()


def test_admin_eliminar_aliado_endpoint(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "90003", "Endpoint Aliado")

    resp = client.post(
        "/api/admin/eliminar-aliado",
        headers=_admin_headers(),
        json={"codigo": "90003", "motivo": "Test endpoint"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert sqlite_db.obtener_aliado_por_codigo("90003")["estado"] == "expulsado"


def test_admin_eliminar_aliado_rechaza_solo_lectura(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "90004", "Solo Lectura")

    resp = client.post(
        "/api/admin/eliminar-aliado",
        headers=_admin_headers(permisos=["leer"]),
        json={"codigo": "90004"},
    )
    assert resp.status_code == 403
    assert sqlite_db.obtener_aliado_por_codigo("90004")["estado"] == "activo"
