"""Flujo Conozco a alguien: candidato pendiente → registro → vincular solicitud."""
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
    return db_module.DBManager(str(tmp_path / "ruana_conozco.db"))


def _crear_grupo_con_aliados(db):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo Conozco", "28001", "activo"),
    )
    grupo_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("C0001", "Solicitante", "Electricidad", "28001", grupo_id, "activo", 50),
    )
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("C0002", "Quien conoce", "Fontaneria", "28001", grupo_id, "activo", 50),
    )
    conn.commit()
    conn.close()
    return grupo_id


def test_conozco_alguien_no_cierra_y_vincula_al_registrar(sqlite_db):
    grupo_id = _crear_grupo_con_aliados(sqlite_db)
    creada = sqlite_db.crear_solicitud_por_codigo(
        "C0001", "Carpinteria", "Necesito reparar una puerta"
    )
    assert creada.get("status") == "success"
    solicitud_id = creada["id"]

    invitador = sqlite_db.obtener_aliado_por_codigo("C0002")
    codigo_inv = "54321"
    sqlite_db._registrar_invitacion(codigo_inv, invitador["id"], solicitud_id)
    mark = sqlite_db.marcar_solicitud_candidato_pendiente(solicitud_id, "C0002")
    assert mark.get("status") == "success"

    propias = sqlite_db.listar_solicitudes_propias_por_codigo("C0001")
    assert propias[0]["estado"] == "candidato_pendiente"
    assert propias[0]["candidato_por_codigo"] == "C0002"

    entrantes = sqlite_db.listar_solicitudes_activas_por_codigo("C0002")
    assert all(s["id"] != solicitud_id for s in entrantes)

    # Incorporación del invitado al mismo grupo (plaza disponible)
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("90099", "Nuevo aliado", "Carpinteria", "28001", grupo_id, "activo", 50),
    )
    conn.commit()
    conn.close()

    assert sqlite_db.consumir_invitacion_y_recompensar(codigo_inv, "90099")
    link = sqlite_db.vincular_solicitud_a_aliado_incorporado(codigo_inv, "90099")
    assert link.get("status") == "success"
    assert link.get("vinculada") is True

    propias_despues = sqlite_db.listar_solicitudes_propias_por_codigo("C0001")
    assert propias_despues[0]["estado"] == "pendiente"
    assert propias_despues[0]["asignada_a_codigo"] == "90099"

    entrantes_nuevo = sqlite_db.listar_solicitudes_activas_por_codigo("90099")
    assert any(s["id"] == solicitud_id for s in entrantes_nuevo)

    conn = sqlite_db._connect()
    conn.row_factory = __import__("sqlite3").Row
    cur = conn.cursor()
    cur.execute(
        "SELECT tipo, titulo FROM notificaciones_aliado WHERE aliado_codigo = ?",
        ("90099",),
    )
    notifs = [dict(r) for r in cur.fetchall()]
    conn.close()
    assert any(n.get("tipo") == "solicitud_asignada" for n in notifs)
