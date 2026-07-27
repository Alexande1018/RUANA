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
    # Forzar activo por si el catálogo lo mueve a pendiente
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


def test_purgar_aliados_placeholder_elimina_filas(sqlite_db):
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
    sqlite_db._registrar_invitacion("33333", 1)

    result = sqlite_db.purgar_aliados_placeholder()
    assert result["status"] == "success"
    assert result["eliminados"] >= 1

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM aliados WHERE codigo = ?", ("33333",))
    assert cur.fetchone()[0] == 0
    # La invitación se conserva para registro futuro
    cur.execute("SELECT usado FROM invitaciones WHERE codigo = ?", ("33333",))
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert int(row[0]) == 0

    listado = sqlite_db.listar_aliados()
    assert all(a["codigo"] != "33333" for a in listado)
    assert any(a["codigo"] == "11111" for a in listado)


def test_init_purga_placeholders_automatica(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db_path = str(tmp_path / "ruana_init_purge.db")
    db1 = db_module.DBManager(db_path)
    db1.crear_aliado(
        codigo="44444",
        nombre="Nuevo Aliado - 44444",
        marca="",
        oficio="Pendiente",
        codigo_postal="28001",
        email="placeholder-44444@ruana.local",
        telefono="+34 600 44444",
        estado="pendiente_completar",
        score=50,
    )
    # Simular BD antigua: quitar marca de migración y reabrir
    conn = db1._connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM migraciones WHERE nombre = 'purgar_placeholders_control_v1'")
    # Insertar placeholder directo por si crear_aliado cambió estado
    cur.execute(
        """
        INSERT OR REPLACE INTO aliados
        (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)
        VALUES ('55555', 'Nuevo Aliado - 55555', '', 'Pendiente', '28001',
                'placeholder-55555@ruana.local', '+34 600 55555', 'pendiente_completar', 50)
        """
    )
    conn.commit()
    conn.close()

    db2 = db_module.DBManager(db_path)
    result = db2.purgar_aliados_placeholder()
    assert result["status"] == "success"
    conn = db2._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM aliados WHERE estado = 'pendiente_completar' OR email LIKE 'placeholder-%@ruana.local'"
    )
    assert cur.fetchone()[0] == 0
    conn.close()
