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
    return db_module.DBManager(str(tmp_path / "ruana_placeholders.db"))


def _crear_real(db, codigo="11111"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre="Aliado Real",
        marca="",
        oficio="Electricidad",
        codigo_postal="28001",
        email=f"real-{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"
    conn = db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()
    return r


def test_listar_aliados_excluye_placeholders(sqlite_db):
    _crear_real(sqlite_db, "11111")
    ph = sqlite_db.crear_aliado(
        codigo="22222",
        nombre="Nuevo Aliado - 22222",
        marca="",
        oficio="Pendiente",
        codigo_postal="28001",
        email="placeholder-22222@ruana.local",
        telefono="+34 600 22222",
        estado="pendiente_completar",
        score=50,
    )
    assert ph["status"] == "success"

    listado = sqlite_db.listar_aliados()
    codigos = {a["codigo"] for a in listado}
    assert "11111" in codigos
    assert "22222" not in codigos


def test_purgar_aliados_placeholder_no_elimina_datos(sqlite_db):
    _crear_real(sqlite_db, "11111")
    sqlite_db.crear_aliado(
        codigo="33333",
        nombre="Nuevo Aliado - 33333",
        marca="",
        oficio="Pendiente",
        codigo_postal="28001",
        email="placeholder-33333@ruana.local",
        telefono="+34 600 33333",
        estado="pendiente_completar",
        score=50,
    )

    result = sqlite_db.purgar_aliados_placeholder()
    assert result["status"] == "success"
    assert result["eliminados"] == 0

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM aliados WHERE codigo = ?", ("33333",))
    assert cur.fetchone()[0] == 1
    conn.close()
