"""Caducidad 24h de códigos «Conozco a alguien» y reactivación de solicitudes."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import invitacion_service, solicitud_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_candidato_exp.db"))


def _crear_grupo_con_aliados(db):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo Expira", "28001", "activo"),
    )
    grupo_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("E0001", "Solicitante", "Electricidad", "28001", grupo_id, "activo", 50),
    )
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("E0002", "Proponente", "Fontaneria", "28001", grupo_id, "activo", 50),
    )
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("E0003", "Otro aliado", "Carpinteria", "28001", grupo_id, "activo", 50),
    )
    conn.commit()
    conn.close()
    return grupo_id


def _setup_candidato_pendiente(db):
    grupo_id = _crear_grupo_con_aliados(db)
    creada = db.crear_solicitud_por_codigo("E0001", "Carpinteria", "Necesito reparar una puerta")
    assert creada.get("status") == "success"
    solicitud_id = creada["id"]
    invitador = db.obtener_aliado_por_codigo("E0002")
    codigo_inv = "77777"
    db._registrar_invitacion(codigo_inv, invitador["id"], solicitud_id)
    mark = db.marcar_solicitud_candidato_pendiente(solicitud_id, "E0002")
    assert mark.get("status") == "success"
    return solicitud_id, codigo_inv, grupo_id


def test_expiracion_reabre_solicitud_y_revoca_codigo(sqlite_db):
    solicitud_id, codigo_inv, _grupo_id = _setup_candidato_pendiente(sqlite_db)

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE solicitudes SET candidato_at = datetime('now', '-25 hours') WHERE id = ?",
        (solicitud_id,),
    )
    conn.commit()
    conn.close()

    result = sqlite_db.expirar_candidatos_pendientes_vencidos()
    assert result.get("status") == "success"
    assert result.get("expiradas") == 1

    propias = sqlite_db.listar_solicitudes_propias_por_codigo("E0001")
    assert propias[0]["estado"] == "pendiente"
    assert not propias[0].get("candidato_por_codigo")

    entrantes = sqlite_db.listar_solicitudes_activas_por_codigo("E0003")
    assert any(s["id"] == solicitud_id for s in entrantes)

    assert invitacion_service.obtener_invitacion_pendiente(sqlite_db, codigo_inv) is None
    assert invitacion_service.es_codigo_conozco_caducado(sqlite_db, codigo_inv) is True


def test_codigo_valido_dentro_de_24h(sqlite_db):
    solicitud_id, codigo_inv, _grupo_id = _setup_candidato_pendiente(sqlite_db)

    assert invitacion_service.obtener_invitacion_pendiente(sqlite_db, codigo_inv) is not None
    assert invitacion_service.es_codigo_conozco_caducado(sqlite_db, codigo_inv) is False

    propias = sqlite_db.listar_solicitudes_propias_por_codigo("E0001")
    assert propias[0]["estado"] == "candidato_pendiente"

    entrantes = sqlite_db.listar_solicitudes_activas_por_codigo("E0003")
    assert all(s["id"] != solicitud_id for s in entrantes)


def test_lazy_expiracion_al_listar_solicitudes(sqlite_db):
    solicitud_id, codigo_inv, _grupo_id = _setup_candidato_pendiente(sqlite_db)

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE solicitudes SET candidato_at = datetime('now', '-30 hours') WHERE id = ?",
        (solicitud_id,),
    )
    conn.commit()
    conn.close()

    entrantes = sqlite_db.listar_solicitudes_activas_por_codigo("E0003")
    assert any(s["id"] == solicitud_id for s in entrantes)
    assert invitacion_service.obtener_invitacion_pendiente(sqlite_db, codigo_inv) is None


def test_calcular_expiracion_candidato():
    desde = solicitud_service.calcular_expiracion_candidato()
    assert desde.endswith("Z")
