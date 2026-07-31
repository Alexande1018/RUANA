from types import SimpleNamespace

import pytest

from core import db_manager as db_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_grupo_nombre.db"))


def test_listar_aliados_incluye_grupo_nombre(sqlite_db):
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo Norte QA", "28001", "activo"),
    )
    grupo_id = cur.lastrowid
    cur.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado) VALUES (?, ?, ?, ?, ?, ?)",
        ("GN001", "Aliado con grupo", "Electricidad", "28001", grupo_id, "activo"),
    )
    conn.commit()
    conn.close()

    listado = sqlite_db.listar_aliados()
    aliado = next(a for a in listado if a["codigo"] == "GN001")
    assert aliado["grupo_id"] == grupo_id
    assert aliado["grupo_nombre"] == "Grupo Norte QA"
