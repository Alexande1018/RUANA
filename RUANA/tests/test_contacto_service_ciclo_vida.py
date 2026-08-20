"""
Tests del ciclo de vida Contacto (service + repo) vía fachada DBManager.
Cubre crear + aceptar + resumen.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.repositories.contacto_repo import ContactoRepo
from core.services import contacto_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_contacto_ciclo.db"))


def _crear_activo(db, codigo, nombre="Aliado"):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Fontanería",
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo[-5:]}",
        estado="activo",
        score=50,
        especializacion="Averías",
    )
    assert result["status"] == "success", result.get("message")
    return result


def test_imports_contacto_service_repo():
    assert hasattr(contacto_service, "crear_contacto_ruana")
    assert hasattr(contacto_service, "aceptar_contacto_ruana")
    assert hasattr(contacto_service, "obtener_contacto_resumen")
    assert ContactoRepo is not None


def test_ciclo_vida_crear_aceptar_resumen(sqlite_db):
    _crear_activo(sqlite_db, "92001", "Solicitante")
    _crear_activo(sqlite_db, "92002", "Profesional")

    creado = sqlite_db.crear_contacto_ruana(
        "92001",
        "92002",
        servicio="Reparar grifo",
        motivo_contacto="Urgencia cocina",
    )
    assert creado["status"] == "success", creado.get("message")
    assert creado["estado"] == "iniciado"
    cid = creado["id"]
    assert cid

    por_id = sqlite_db.obtener_contacto_por_id(cid)
    assert por_id is not None
    assert por_id["solicitante_codigo"] == "92001"
    assert por_id["profesional_codigo"] == "92002"
    assert por_id["estado"] == "iniciado"

    aceptado = sqlite_db.aceptar_contacto_ruana(cid, "92002")
    assert aceptado["status"] == "success", aceptado.get("message")
    assert aceptado["estado"] == "aceptado"

    resumen = sqlite_db.obtener_contacto_resumen(cid)
    assert resumen is not None
    assert resumen["id"] == cid
    assert resumen["estado"] == "aceptado"
    assert resumen["solicitante_codigo"] == "92001"
    assert resumen["profesional_codigo"] == "92002"
    assert "importe_solicitante" not in resumen
    assert "importe_profesional" not in resumen


def test_aceptar_contacto_via_service_directo(sqlite_db):
    _crear_activo(sqlite_db, "92011", "Sol")
    _crear_activo(sqlite_db, "92012", "Pro")
    creado = contacto_service.crear_contacto_ruana(
        sqlite_db, "92011", "92012", servicio="Desatasco", motivo_contacto="Baño"
    )
    assert creado["status"] == "success"
    cid = creado["id"]
    ok = contacto_service.aceptar_contacto_ruana(sqlite_db, cid, "92012")
    assert ok["status"] == "success"
    resumen = contacto_service.obtener_contacto_resumen(sqlite_db, cid)
    assert resumen["estado"] == "aceptado"


def _marcar_precio_confirmado(db, contacto_id, estado="pendiente_de_pago", importe=150.0):
    conn = db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado = ?, importe_acordado = ? WHERE id = ?",
        (estado, importe, contacto_id),
    )
    conn.commit()
    conn.close()


def test_no_concretado_permitido_antes_de_confirmar_precio(sqlite_db):
    _crear_activo(sqlite_db, "92101", "Sol")
    _crear_activo(sqlite_db, "92102", "Pro")
    creado = sqlite_db.crear_contacto_ruana("92101", "92102", servicio="Grifo", motivo_contacto="Presupuesto")
    assert creado["status"] == "success"
    cid = creado["id"]

    r = sqlite_db.marcar_cerrado_no_concretado(cid, actor_codigo="92101")
    assert r["status"] == "success", r.get("message")
    assert r["estado"] == "cerrado_no_concretado"
    contacto = sqlite_db.obtener_contacto_por_id(cid)
    assert contacto["estado"] == "cerrado_no_concretado"


def test_no_concretado_bloqueado_si_precio_confirmado(sqlite_db):
    _crear_activo(sqlite_db, "92111", "Sol")
    _crear_activo(sqlite_db, "92112", "Pro")
    creado = sqlite_db.crear_contacto_ruana("92111", "92112", servicio="Grifo", motivo_contacto="Presupuesto")
    cid = creado["id"]
    _marcar_precio_confirmado(sqlite_db, cid, estado="pendiente_de_pago", importe=180.0)

    r = sqlite_db.marcar_cerrado_no_concretado(cid, actor_codigo="92111")
    assert r["status"] == "error"
    assert "precio" in (r.get("message") or "").lower()
    assert "concretado" in (r.get("message") or "").lower()
    contacto = sqlite_db.obtener_contacto_por_id(cid)
    assert contacto["estado"] == "pendiente_de_pago"
    assert float(contacto["importe_acordado"]) == 180.0


def test_no_concretado_bloqueado_si_acuerdo_alcanzado(sqlite_db):
    _crear_activo(sqlite_db, "92121", "Sol")
    _crear_activo(sqlite_db, "92122", "Pro")
    creado = sqlite_db.crear_contacto_ruana("92121", "92122", servicio="Grifo", motivo_contacto="Presupuesto")
    cid = creado["id"]
    _marcar_precio_confirmado(sqlite_db, cid, estado="acuerdo_alcanzado", importe=90.0)

    r = contacto_service.marcar_cerrado_no_concretado(
        sqlite_db, cid, motivo="intento", actor_codigo="92121"
    )
    assert r["status"] == "error"
    assert "precio" in (r.get("message") or "").lower()
    contacto = sqlite_db.obtener_contacto_por_id(cid)
    assert contacto["estado"] == "acuerdo_alcanzado"


def test_no_concretado_bloqueado_solo_con_importe_acordado(sqlite_db):
    """Si hay importe oficial, el negocio ya está hecho aunque el estado siga abierto."""
    _crear_activo(sqlite_db, "92131", "Sol")
    _crear_activo(sqlite_db, "92132", "Pro")
    creado = sqlite_db.crear_contacto_ruana("92131", "92132", servicio="Grifo", motivo_contacto="Presupuesto")
    cid = creado["id"]
    sqlite_db.aceptar_contacto_ruana(cid, "92132")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET importe_acordado = ? WHERE id = ?", (200.0, cid))
    conn.commit()
    conn.close()

    r = sqlite_db.marcar_cerrado_no_concretado(cid, actor_codigo="92132")
    assert r["status"] == "error"
    contacto = sqlite_db.obtener_contacto_por_id(cid)
    assert contacto["estado"] == "aceptado"
