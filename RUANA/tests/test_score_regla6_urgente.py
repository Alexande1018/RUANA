from datetime import datetime, timedelta
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
    return db_module.DBManager(str(tmp_path / "ruana_score_regla6.db"))


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


def test_crear_contacto_urgente_persiste_flag(sqlite_db):
    _crear_activo(sqlite_db, "80001", "SolicitanteU")
    _crear_activo(sqlite_db, "80002", "ProfesionalU")
    result = sqlite_db.crear_contacto_ruana(
        "80001", "80002", "Servicio", "Emergencia", es_urgente=True
    )
    assert result["status"] == "success"
    assert result["es_urgente"] is True
    resumen = sqlite_db.obtener_contacto_resumen(result["id"])
    assert resumen["es_urgente"] is True
    assert resumen.get("urgente_marcado_en") is not None


def test_regla6_mas3_profesional_mismo_dia(sqlite_db):
    _crear_activo(sqlite_db, "81001", "SolicitanteV")
    _crear_activo(sqlite_db, "81002", "ProfesionalV")
    created = sqlite_db.crear_contacto_ruana(
        "81001", "81002", "Servicio", "Emergencia", es_urgente=True
    )
    cid = created["id"]

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE contactos_ruana
        SET estado = 'trabajo_cerrado', importe_final = 100, apoyo_ruana = 12,
            estado_pago = 'pendiente_pago', pendiente_pago = 1,
            fecha_cierre = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (cid,),
    )
    conn.commit()
    conn.close()

    assert sqlite_db.actualizar_estado_pago_contacto(cid, "pagado", "ADMIN")["status"] == "success"
    assert _score(sqlite_db, "81002") == 55  # +2 Regla2 + +3 Regla6
    assert (3, f"regla6_urgente_mismo_dia_{cid}") in _motivos(sqlite_db, "81002")
    assert _score(sqlite_db, "81001") == 52  # solo Regla 2

    # Idempotente
    assert sqlite_db.actualizar_estado_pago_contacto(cid, "pagado", "ADMIN")["status"] == "success"
    assert sum(1 for _, m in _motivos(sqlite_db, "81002") if m.startswith("regla6_")) == 1


def test_regla6_no_aplica_si_otro_dia(sqlite_db):
    _crear_activo(sqlite_db, "82001", "SolicitanteW")
    _crear_activo(sqlite_db, "82002", "ProfesionalW")
    created = sqlite_db.crear_contacto_ruana(
        "82001", "82002", "Servicio", "Emergencia", es_urgente=True
    )
    cid = created["id"]
    ayer = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE contactos_ruana
        SET estado = 'trabajo_cerrado', importe_final = 100, apoyo_ruana = 12,
            estado_pago = 'pendiente_pago', pendiente_pago = 1,
            urgente_marcado_en = ?, creado_en = ?, fecha_cierre = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (ayer, ayer, cid),
    )
    conn.commit()
    conn.close()

    assert sqlite_db.evaluar_regla6_urgente_mismo_dia(cid, fecha_pago=datetime.now()) is None
    assert sqlite_db.actualizar_estado_pago_contacto(cid, "pagado", "ADMIN")["status"] == "success"
    assert not any(m.startswith("regla6_") for _, m in _motivos(sqlite_db, "82002"))
    assert _score(sqlite_db, "82002") == 52  # solo Regla 2


def test_regla6_no_aplica_sin_urgente(sqlite_db):
    _crear_activo(sqlite_db, "83001", "SolicitanteX")
    _crear_activo(sqlite_db, "83002", "ProfesionalX")
    created = sqlite_db.crear_contacto_ruana(
        "83001", "83002", "Servicio", "Consulta general", es_urgente=False
    )
    cid = created["id"]
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE contactos_ruana
        SET estado = 'trabajo_cerrado', importe_final = 80, apoyo_ruana = 10,
            estado_pago = 'pendiente_pago', pendiente_pago = 1
        WHERE id = ?
        """,
        (cid,),
    )
    conn.commit()
    conn.close()
    assert sqlite_db.actualizar_estado_pago_contacto(cid, "pagado", "ADMIN")["status"] == "success"
    assert not any(m.startswith("regla6_") for _, m in _motivos(sqlite_db, "83002"))
