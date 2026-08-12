"""
Tests mínimos del dominio Notificación (service + repo) vía fachada DBManager.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.repositories.notificacion_repo import NotificacionRepo
from core.services import notificacion_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_notificacion.db"))


def test_imports_notificacion_service_repo():
    assert hasattr(notificacion_service, "crear_notificacion_aliado")
    assert hasattr(notificacion_service, "listar_notificaciones_aliado")
    assert hasattr(notificacion_service, "marcar_notificacion_leida")
    assert hasattr(notificacion_service, "marcar_todas_notificaciones_leidas")
    assert hasattr(notificacion_service, "marcar_notificaciones_contacto_leidas")
    assert NotificacionRepo is not None


def test_crear_listar_marcar_notificacion(sqlite_db):
    sqlite_db._crear_notificacion_aliado(
        "93001",
        "apoyo_ruana",
        "Apoyo RUANA",
        "Mensaje de prueba",
        metadata={"contacto_id": 42, "origen": "test"},
    )

    lista = sqlite_db.listar_notificaciones_aliado("93001", limite=10)
    assert len(lista) >= 1
    item = lista[0]
    assert item["tipo"] == "apoyo_ruana"
    assert item["titulo"] == "Apoyo RUANA"
    assert item["leida"] in (0, False)
    assert item["metadata"]["contacto_id"] == 42

    ok = sqlite_db.marcar_notificacion_leida(item["id"], "93001")
    assert ok["status"] == "success"

    lista2 = sqlite_db.listar_notificaciones_aliado("93001")
    leida = next(n for n in lista2 if n["id"] == item["id"])
    assert leida["leida"] in (1, True)

    sqlite_db._crear_notificacion_aliado(
        "93001", "otro", "Otra", "Segunda", metadata={"contacto_id": 99}
    )
    todas = sqlite_db.marcar_todas_notificaciones_leidas("93001")
    assert todas["status"] == "success"
    assert todas["actualizadas"] >= 1
