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
    return db_module.DBManager(str(tmp_path / "ruana_activar_grupo.db"))


def _crear_grupo_con_invitador(db, codigo_invitador="INV01", oficio_invitador="Electricidad"):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo Invitador", "03014", "activo"),
    )
    grupo_id = cur.lastrowid
    cur.execute(
        """INSERT INTO aliados
           (codigo, nombre, oficio, codigo_postal, grupo_id, estado, email, telefono)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (codigo_invitador, "Aliado Invitador", oficio_invitador, "03014", grupo_id, "activo", "inv@example.com", "+34600111111"),
    )
    conn.commit()
    conn.close()
    return grupo_id


def test_activar_pendiente_asigna_grupo_del_invitador(sqlite_db):
    grupo_id = _crear_grupo_con_invitador(sqlite_db)

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO aliados
           (codigo, nombre, oficio, codigo_postal, estado, invitado_por_codigo, email, telefono)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("PND01", "Pendiente Hosteleria", "Hostelería", "03014", "pendiente_validacion", "INV01", "p1@example.com", "+34600222222"),
    )
    conn.commit()
    conn.close()

    result = sqlite_db.activar_aliado_pendiente("PND01")
    assert result["status"] == "success"
    assert result.get("grupo_id") == grupo_id

    aliado = sqlite_db.obtener_aliado_por_codigo("PND01")
    assert aliado["estado"] == "activo"
    assert aliado["grupo_id"] == grupo_id


def test_activar_pendiente_por_id_usa_grupo_invitador(sqlite_db):
    grupo_id = _crear_grupo_con_invitador(sqlite_db, codigo_invitador="INV02")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO aliados
           (codigo, nombre, oficio, codigo_postal, estado, invitado_por_codigo, email, telefono)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("PND02", "Otro Pendiente", "Coach personal", "03014", "pendiente_validacion", "INV02", "p2@example.com", "+34600333333"),
    )
    aliado_id = cur.lastrowid
    conn.commit()
    conn.close()

    result = sqlite_db.activar_aliado_por_id(aliado_id)
    assert result["status"] == "success"
    assert result.get("grupo_id") == grupo_id

    aliado = sqlite_db.obtener_aliado_por_codigo("PND02")
    assert aliado["grupo_id"] == grupo_id


def test_activar_pendiente_si_oficio_ocupado_en_grupo_invitador_busca_otro(sqlite_db):
    grupo_id = _crear_grupo_con_invitador(sqlite_db, codigo_invitador="INV03", oficio_invitador="Electricidad")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo Alternativo", "03014", "activo"),
    )
    grupo_alt = cur.lastrowid
    cur.execute(
        """INSERT INTO aliados
           (codigo, nombre, oficio, codigo_postal, estado, invitado_por_codigo, email, telefono)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("PND03", "Pendiente Electricista", "Electricidad", "03014", "pendiente_validacion", "INV03", "p3@example.com", "+34600444444"),
    )
    conn.commit()
    conn.close()

    result = sqlite_db.activar_aliado_pendiente("PND03")
    assert result["status"] == "success"
    assert result.get("grupo_id") == grupo_alt

    aliado = sqlite_db.obtener_aliado_por_codigo("PND03")
    assert aliado["grupo_id"] == grupo_alt
    assert aliado["grupo_id"] != grupo_id
