"""Consolidación v2 es no-op: los grupos territoriales no se absorben en un Grupo Madre."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import schema_service


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


def test_consolidar_v2_no_mueve_grupos_territoriales(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("03001", "Alicante", "Alicante")
    g2 = sqlite_db.crear_grupo_en_cp("03003", "Alicante", "Alicante")
    assert g1.get("id") and g2.get("id")

    _crear(sqlite_db, "80001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "80002", oficio="Fontanería y fontanería-gas", cp="03001")
    _crear(sqlite_db, "80003", oficio="Albañilería y obra", cp="03003")
    _crear(sqlite_db, "80004", oficio="Cerrajería", cp="03003")

    assert sqlite_db.contar_grupos_activos_por_cp("03001") == 1
    assert sqlite_db.contar_grupos_activos_por_cp("03003") == 1

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    schema_service._migrar_grupo_madre_v2_consolidar_si_procede(sqlite_db, conn, cursor)
    conn.commit()
    conn.close()

    for codigo in ("80001", "80002", "80003", "80004"):
        aliado = sqlite_db.obtener_aliado_por_codigo(codigo)
        g = sqlite_db.obtener_grupo_por_id(aliado["grupo_id"])
        assert (g or {}).get("tipo") == "territorial"

    assert sqlite_db.contar_grupos_activos_por_cp("03001") == 1
    assert sqlite_db.contar_grupos_activos_por_cp("03003") == 1
    assert sqlite_db.cp_en_modo_territorial("03001") is True

    g1_after = sqlite_db.obtener_grupo_por_id(g1["id"])
    g2_after = sqlite_db.obtener_grupo_por_id(g2["id"])
    assert (g1_after or {}).get("estado") == "activo"
    assert (g2_after or {}).get("estado") == "activo"


def test_nuevo_registro_sigue_en_territorial(sqlite_db):
    sqlite_db.crear_grupo_en_cp("03001", "Alicante", "Alicante")
    _crear(sqlite_db, "80101", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "80102", oficio="Pintura y decoración", cp="03001")
    aliado = sqlite_db.obtener_aliado_por_codigo("80102")
    g = sqlite_db.obtener_grupo_por_id(aliado["grupo_id"])
    assert (g or {}).get("tipo") == "territorial"
