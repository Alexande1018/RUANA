"""Consolidación: aliados de grupos territoriales pequeños pasan al Grupo Madre."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import TIPO_GRUPO_MADRE
from core.services import grupo_madre_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_madre_consolidar.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03001"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()
    return r


def test_consolidar_mueve_grupos_pequenos_al_madre(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("03001", "Alicante", "Alicante")
    g2 = sqlite_db.crear_grupo_en_cp("03003", "Alicante", "Alicante")
    assert g1.get("id") and g2.get("id")

    _crear(sqlite_db, "80001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "80002", oficio="Fontanería y fontanería-gas", cp="03001")
    _crear(sqlite_db, "80003", oficio="Albañilería y obra", cp="03003")
    _crear(sqlite_db, "80004", oficio="Cerrajería", cp="03003")

    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, "03001") == 1
    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, "03003") == 1

    result = grupo_madre_service.consolidar_territoriales_en_madre(sqlite_db)
    assert result["status"] == "ok"
    assert result["aliados_movidos"] >= 4
    assert result["grupos_disueltos"] >= 2

    ids = set()
    for codigo in ("80001", "80002", "80003", "80004"):
        aliado = sqlite_db.obtener_aliado_por_codigo(codigo)
        g = sqlite_db.obtener_grupo_por_id(aliado["grupo_id"])
        assert (g or {}).get("tipo") == TIPO_GRUPO_MADRE
        ids.add(aliado["grupo_id"])
    assert len(ids) == 1

    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, "03001") == 0
    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, "03003") == 0
    assert grupo_madre_service.cp_en_modo_territorial(sqlite_db, "03001") is False

    g1_after = sqlite_db.obtener_grupo_por_id(g1["id"])
    g2_after = sqlite_db.obtener_grupo_por_id(g2["id"])
    assert (g1_after or {}).get("estado") == "disuelto"
    assert (g2_after or {}).get("estado") == "disuelto"


def test_nuevo_registro_tras_consolidar_sigue_en_madre(sqlite_db):
    sqlite_db.crear_grupo_en_cp("03001", "Alicante", "Alicante")
    _crear(sqlite_db, "80101", oficio="Electricidad", cp="03001")
    grupo_madre_service.consolidar_territoriales_en_madre(sqlite_db)

    _crear(sqlite_db, "80102", oficio="Pintura y decoración", cp="03001")
    aliado = sqlite_db.obtener_aliado_por_codigo("80102")
    g = sqlite_db.obtener_grupo_por_id(aliado["grupo_id"])
    assert (g or {}).get("tipo") == TIPO_GRUPO_MADRE
