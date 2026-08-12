"""
Tests básicos del dominio Evaluación (service + repo) vía fachada DBManager.
Cubre guardar + obtener + listar.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.repositories.evaluacion_repo import EvaluacionRepo
from core.services import evaluacion_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_evaluacion.db"))


def test_imports_evaluacion_service_repo():
    assert hasattr(evaluacion_service, "guardar_evaluacion")
    assert hasattr(evaluacion_service, "obtener_evaluacion")
    assert hasattr(evaluacion_service, "listar_evaluaciones")
    assert hasattr(evaluacion_service, "obtener_historico_evaluaciones")
    assert hasattr(evaluacion_service, "obtener_estadisticas_evaluaciones")
    assert EvaluacionRepo is not None


def test_guardar_obtener_listar_evaluacion(sqlite_db):
    result = sqlite_db.guardar_evaluacion(
        "93001",
        estado="verde",
        score=320.0,
        intencion="mantener",
        tasa_respuesta=0.9,
        tasa_confirmacion=0.8,
        meses_sin_trabajo=0,
        ciclos_consecutivos=2,
        razones=["alta_respuesta"],
        severidad="normal",
    )
    assert result["status"] == "success", result.get("message")
    assert result["codigo_aliado"] == "93001"
    assert result["estado"] == "verde"
    assert result["score"] == 320.0

    obt = sqlite_db.obtener_evaluacion("93001")
    assert obt is not None
    assert obt["codigo_aliado"] == "93001"
    assert obt["estado"] == "verde"
    assert float(obt["score"]) == 320.0
    assert obt["razones"] == ["alta_respuesta"]
    assert obt["intencion"] == "mantener"

    lista = sqlite_db.listar_evaluaciones()
    assert any(e["codigo_aliado"] == "93001" for e in lista)

    verdes = sqlite_db.listar_evaluaciones("verde")
    assert len(verdes) >= 1
    assert all(e["estado"] == "verde" for e in verdes)


def test_guardar_via_service_directo_y_historico(sqlite_db):
    ok = evaluacion_service.guardar_evaluacion(
        sqlite_db, "93011", "amarillo", 180.0, razones=["vigilar"]
    )
    assert ok["status"] == "success"

    ok2 = evaluacion_service.guardar_evaluacion(
        sqlite_db, "93011", "rojo", 40.0, razones=["baja_respuesta"], severidad="alerta"
    )
    assert ok2["status"] == "success"

    obt = evaluacion_service.obtener_evaluacion(sqlite_db, "93011")
    assert obt["estado"] == "rojo"
    assert float(obt["score"]) == 40.0

    hist = evaluacion_service.obtener_historico_evaluaciones(sqlite_db, "93011")
    assert len(hist) >= 1
    assert hist[0]["estado_nuevo"] == "rojo"
    assert hist[0]["estado_anterior"] == "amarillo"

    stats = evaluacion_service.obtener_estadisticas_evaluaciones(sqlite_db)
    assert stats["total_evaluados"] >= 1
    assert "por_estado" in stats
