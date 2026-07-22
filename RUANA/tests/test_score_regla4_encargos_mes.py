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
    return db_module.DBManager(str(tmp_path / "ruana_score_regla4.db"))


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


def _crear_contacto_apoyo(db, solicitante, profesional, servicio="Servicio", estado_pago="pendiente_pago"):
    conn = db._connect()
    cur = conn.cursor()
    pendiente = 0 if estado_pago == "pagado" else 1
    fecha_val = "CURRENT_TIMESTAMP" if estado_pago == "pagado" else "NULL"
    cur.execute(
        f"""
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado,
            importe_final, apoyo_ruana, estado_pago, pendiente_pago, fecha_validacion_pago
        ) VALUES (?, ?, ?, 'trabajo_cerrado', 100, 12, ?, ?, {fecha_val})
        """,
        (solicitante, profesional, servicio, estado_pago, pendiente),
    )
    contacto_id = cur.lastrowid
    conn.commit()
    conn.close()
    return contacto_id


def _score(db, codigo):
    return int(db.obtener_aliado_por_codigo(codigo)["score"])


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


def test_regla4_otorga_mas3_al_cuarto_pagado_limpio(sqlite_db):
    from datetime import datetime

    _crear_activo(sqlite_db, "40001", "ProfesionalA")
    _crear_activo(sqlite_db, "40002", "ClienteUno")
    _crear_activo(sqlite_db, "40003", "ClienteDos")
    _crear_activo(sqlite_db, "40004", "ClienteTre")
    _crear_activo(sqlite_db, "40005", "ClienteCua")

    # 3 ya pagados en el mes (sin pasar por score) + 1 pendiente que dispara Regla 4
    _crear_contacto_apoyo(sqlite_db, "40002", "40001", "Trabajo 1", estado_pago="pagado")
    _crear_contacto_apoyo(sqlite_db, "40003", "40001", "Trabajo 2", estado_pago="pagado")
    _crear_contacto_apoyo(sqlite_db, "40004", "40001", "Trabajo 3", estado_pago="pagado")
    cid4 = _crear_contacto_apoyo(sqlite_db, "40005", "40001", "Trabajo 4")

    assert len(sqlite_db.listar_encargos_pagados_mes("40001", datetime.now().strftime("%Y-%m"))) == 3
    assert sqlite_db.evaluar_regla4_encargos_mes_limpio("40001") is None

    assert sqlite_db.actualizar_estado_pago_contacto(cid4, "pagado", "ADMIN")["status"] == "success"

    anio_mes = datetime.now().strftime("%Y-%m")
    # +2 Regla 2 + +3 Regla 4
    assert _score(sqlite_db, "40001") == 55
    assert (2, "encargo_completado_apoyo_pagado") in _motivos(sqlite_db, "40001")
    assert (3, f"regla4_4_encargos_mes_limpio_{anio_mes}") in _motivos(sqlite_db, "40001")

    # Idempotente
    assert sqlite_db.actualizar_estado_pago_contacto(cid4, "pagado", "ADMIN")["status"] == "success"
    assert _score(sqlite_db, "40001") == 55
    assert sum(1 for d, m in _motivos(sqlite_db, "40001") if m.startswith("regla4_")) == 1


def test_regla4_invalida_si_hubo_rechazo_aunque_luego_pagado(sqlite_db):
    from datetime import datetime

    _crear_activo(sqlite_db, "50001", "ProfesionalB")
    clientes = []
    for i, nombre in enumerate(["CliAaaa", "CliBbbb", "CliCccc", "CliDddd"], start=2):
        codigo = f"5000{i}"
        _crear_activo(sqlite_db, codigo, nombre)
        clientes.append(codigo)

    ids = [_crear_contacto_apoyo(sqlite_db, c, "50001", f"T{i}") for i, c in enumerate(clientes)]

    # Primer contacto: rechazo (incidencia) y luego pagado
    assert sqlite_db.actualizar_estado_pago_contacto(ids[0], "rechazado", "ADMIN", "Comprobante ilegible")[
        "status"
    ] == "success"
    assert sqlite_db.contacto_tiene_incidencia_pago(ids[0]) is True
    assert sqlite_db.actualizar_estado_pago_contacto(ids[0], "pagado", "ADMIN")["status"] == "success"

    # Otros 3 ya como pagados previos del mes (evita tope diario de score)
    for cid in ids[1:3]:
        conn = sqlite_db._connect()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE contactos_ruana
            SET estado_pago = 'pagado', pendiente_pago = 0,
                fecha_validacion_pago = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (cid,),
        )
        conn.commit()
        conn.close()

    assert sqlite_db.actualizar_estado_pago_contacto(ids[3], "pagado", "ADMIN")["status"] == "success"

    assert len(sqlite_db.listar_encargos_pagados_mes("50001", datetime.now().strftime("%Y-%m"))) == 4
    assert sqlite_db.evaluar_regla4_encargos_mes_limpio("50001") is None
    assert not any(m.startswith("regla4_") for _, m in _motivos(sqlite_db, "50001"))


def test_regla4_invalida_si_hubo_disputa(sqlite_db):
    _crear_activo(sqlite_db, "60001", "ProfesionalC")
    _crear_activo(sqlite_db, "60002", "ClienteXxx")
    contacto_id = _crear_contacto_apoyo(sqlite_db, "60002", "60001")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET fecha_disputa = CURRENT_TIMESTAMP WHERE id = ?",
        (contacto_id,),
    )
    conn.commit()
    conn.close()

    assert sqlite_db.contacto_tiene_incidencia_pago(contacto_id) is True
    assert sqlite_db.actualizar_estado_pago_contacto(contacto_id, "pagado", "ADMIN")["status"] == "success"
    assert not any(m.startswith("regla4_") for _, m in _motivos(sqlite_db, "60001"))
