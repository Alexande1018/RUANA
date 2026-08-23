"""Tests de generar_invitacion_oficio (invitacion_service)."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import catalogo_service, invitacion_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_invitacion_oficio.db"))


def _crear_activo(db, codigo, oficio="Electricidad"):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca test",
        oficio=oficio,
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
        especializacion="Servicio general",
    )
    assert result["status"] == "success"
    return result


def test_generar_invitacion_oficio_genera_codigo_valido(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "71001", oficio="Electricidad")

    catalogo = catalogo_service.get_catalogo_oficios_ruana(sqlite_db)
    oficio_faltante = next(o for o in catalogo if o != "Electricidad")

    result = invitacion_service.generar_invitacion_oficio(
        sqlite_db, "71001", oficio_faltante
    )

    assert result["status"] == "success"
    assert "codigo" in result
    assert result["codigo"].startswith("RUANA-")
    assert oficio_faltante.split()[0].upper()[:4] in result["codigo"].upper() or "OFICIO" in result["codigo"]


def test_generar_invitacion_oficio_reutiliza_pendiente(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "71002", oficio="Electricidad")

    catalogo = catalogo_service.get_catalogo_oficios_ruana(sqlite_db)
    oficio_faltante = next(o for o in catalogo if o != "Electricidad")

    first = invitacion_service.generar_invitacion_oficio(
        sqlite_db, "71002", oficio_faltante
    )
    second = invitacion_service.generar_invitacion_oficio(
        sqlite_db, "71002", oficio_faltante
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert first["codigo"] == second["codigo"]


def test_generar_invitacion_oficio_rechaza_oficio_no_faltante(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "71003", oficio="Electricidad")

    result = invitacion_service.generar_invitacion_oficio(
        sqlite_db, "71003", "Electricidad"
    )

    assert result["status"] == "error"
    assert "faltantes" in result["message"].lower()
