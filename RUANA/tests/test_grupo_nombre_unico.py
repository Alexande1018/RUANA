"""Unicidad global del nombre de grupo (nunca duplicado, incluye disueltos)."""

import pytest

from core import db_manager as db_module


@pytest.fixture
def sqlite_db(tmp_path):
    return db_module.DBManager(str(tmp_path / "grupo_nombre_unico.db"))


def test_crear_grupos_generan_nombres_distintos(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("28001", ciudad="Madrid", provincia="Madrid")
    g2 = sqlite_db.crear_grupo_en_cp("28001", ciudad="Madrid", provincia="Madrid")
    assert g1.get("id") and g2.get("id")
    assert g1["nombre"] != g2["nombre"]


def test_insertar_grupo_rechaza_nombre_duplicado(sqlite_db):
    g = sqlite_db.crear_grupo_en_cp("28002")
    nombre = g["nombre"]
    conn = sqlite_db._connect()
    cur = conn.cursor()
    from core.repositories.grupo_repo import GrupoRepo

    repo = GrupoRepo()
    with pytest.raises(ValueError, match="Ya existe un grupo"):
        repo.insertar_grupo(cur, nombre, "28002", "", "")
    conn.close()


def test_nombre_disuelto_no_se_reutiliza(sqlite_db):
    g = sqlite_db.crear_grupo_en_cp("28003")
    nombre = g["nombre"]
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (g["id"],))
    conn.commit()
    conn.close()

    g2 = sqlite_db.crear_grupo_en_cp("28003")
    assert g2["nombre"] != nombre


def test_existe_nombre_case_insensitive(sqlite_db):
    g = sqlite_db.crear_grupo_en_cp("28004")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    from core.repositories.grupo_repo import GrupoRepo

    repo = GrupoRepo()
    if g["nombre"].upper() != g["nombre"]:
        assert repo.existe_nombre(cur, g["nombre"].upper())
    conn.close()
