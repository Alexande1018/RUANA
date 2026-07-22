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
    return db_module.DBManager(str(tmp_path / "ruana_score_regla3.db"))


def _crear_activo(db, codigo, nombre, score=50):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo[-5:]}",
        estado="activo",
        score=score,
        especializacion="Averías",
    )
    assert result["status"] == "success"
    return result


def _score(db, codigo):
    aliado = db.obtener_aliado_por_codigo(codigo)
    return int(aliado["score"])


def _motivos(db, codigo):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT delta, motivo FROM score_movimientos WHERE codigo_aliado = ? ORDER BY id",
        (codigo,),
    )
    rows = cur.fetchall()
    conn.close()
    return [(int(r[0]), r[1]) for r in rows]


def test_ancestros_referidos_gen1_y_gen2(sqlite_db):
    _crear_activo(sqlite_db, "10001", "Abuelo")
    _crear_activo(sqlite_db, "10002", "Padre")
    _crear_activo(sqlite_db, "10003", "Nieto")
    assert sqlite_db.asignar_invitado_por("10002", "10001", "aliado")
    assert sqlite_db.asignar_invitado_por("10003", "10002", "aliado")

    ancestros = sqlite_db.ancestros_referidos_para_score("10003", max_generaciones=2)
    assert ancestros == [("10002", 1), ("10001", 2)]


def test_ancestros_omite_sistema_y_admin(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "20001", "HijoAdmin")
    assert sqlite_db.asignar_invitado_por("20001", "RUANA-ADMIN", "admin_invitacion")

    assert sqlite_db.ancestros_referidos_para_score("20001") == []


def test_regla2_y_regla3_al_marcar_apoyo_pagado(sqlite_db):
    # A → B → C (profesional). E → D (solicitante).
    _crear_activo(sqlite_db, "30001", "AbueloA")
    _crear_activo(sqlite_db, "30002", "PadreB")
    _crear_activo(sqlite_db, "30003", "NietoC")
    _crear_activo(sqlite_db, "30004", "SolicD")
    _crear_activo(sqlite_db, "30005", "PadreE")
    assert sqlite_db.asignar_invitado_por("30002", "30001", "aliado")
    assert sqlite_db.asignar_invitado_por("30003", "30002", "aliado")
    assert sqlite_db.asignar_invitado_por("30004", "30005", "aliado")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado,
            importe_final, apoyo_ruana, estado_pago, pendiente_pago
        ) VALUES (?, ?, ?, 'trabajo_cerrado', 100, 12, 'pendiente_pago', 1)
        """,
        ("30004", "30003", "Servicio test"),
    )
    contacto_id = cur.lastrowid
    conn.commit()
    conn.close()

    result = sqlite_db.actualizar_estado_pago_contacto(contacto_id, "pagado", "ADMIN")
    assert result["status"] == "success"

    # Regla 2
    assert _score(sqlite_db, "30003") == 52
    assert _score(sqlite_db, "30004") == 52
    assert (2, "encargo_completado_apoyo_pagado") in _motivos(sqlite_db, "30003")
    assert (2, "encargo_completado_apoyo_pagado") in _motivos(sqlite_db, "30004")

    # Regla 3: gen1/gen2 de C, gen1 de D
    assert _score(sqlite_db, "30002") == 51
    assert _score(sqlite_db, "30001") == 51
    assert _score(sqlite_db, "30005") == 51
    assert (1, "referido_encargo_completado_gen1") in _motivos(sqlite_db, "30002")
    assert (1, "referido_encargo_completado_gen2") in _motivos(sqlite_db, "30001")
    assert (1, "referido_encargo_completado_gen1") in _motivos(sqlite_db, "30005")

    # Idempotente: volver a marcar pagado no suma de nuevo
    result2 = sqlite_db.actualizar_estado_pago_contacto(contacto_id, "pagado", "ADMIN")
    assert result2["status"] == "success"
    assert _score(sqlite_db, "30003") == 52
    assert _score(sqlite_db, "30002") == 51
    assert _score(sqlite_db, "30001") == 51
