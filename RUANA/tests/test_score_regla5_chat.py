from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core import db_manager as db_module


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_score_regla5.db"))


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


def _crear_contacto(db, solicitante, profesional, estado="aceptado"):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion
        ) VALUES (?, ?, ?, ?, 0)
        """,
        (solicitante, profesional, "Servicio test", estado),
    )
    contacto_id = cur.lastrowid
    conn.commit()
    conn.close()
    return contacto_id


def _insert_msg(db, contacto_id, emisor, texto, creado_en):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO chat_mensajes (contacto_id, emisor_codigo, texto, creado_en)
        VALUES (?, ?, ?, ?)
        """,
        (contacto_id, emisor, texto, creado_en),
    )
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return msg_id


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


def test_regla5_tres_clientes_respuesta_rapida(sqlite_db):
    _crear_activo(sqlite_db, "70001", "ProfesionalX")
    clientes = ["70002", "70003", "70004"]
    for i, codigo in enumerate(clientes):
        _crear_activo(sqlite_db, codigo, f"Cliente{i}xx")

    base = datetime(2026, 7, 23, 10, 0, 0)
    for i, sol in enumerate(clientes):
        cid = _crear_contacto(sqlite_db, sol, "70001")
        t_cliente = base + timedelta(days=i, minutes=0)
        t_pro = t_cliente + timedelta(minutes=20)  # < 1h
        _insert_msg(sqlite_db, cid, sol, "Hola, necesito ayuda", t_cliente.strftime("%Y-%m-%d %H:%M:%S"))
        _insert_msg(sqlite_db, cid, "70001", "Claro, te atiendo", t_pro.strftime("%Y-%m-%d %H:%M:%S"))

    hito = sqlite_db.evaluar_regla5_respuestas_chat("70001")
    assert hito is not None
    assert hito[1] == 3
    assert hito[2].startswith("regla5_3_clientes_respuesta_1h_")

    # Disparo real vía enviar_mensaje (ya hay 3; al escribir de nuevo no duplica el mismo lote)
    cid_extra = _crear_contacto(sqlite_db, "70002", "70001")
    # contacto nuevo mismo cliente no crea lote nuevo; forzar evaluación aplicando hito
    sqlite_db.aplicar_cambio_score(hito[0], hito[1], hito[2])
    assert _score(sqlite_db, "70001") == 53
    assert (3, hito[2]) in _motivos(sqlite_db, "70001")

    assert sqlite_db.evaluar_regla5_respuestas_chat("70001") is None  # idempotente


def test_regla5_no_cuenta_si_responde_despues_de_1h(sqlite_db):
    _crear_activo(sqlite_db, "71001", "ProfesionalY")
    for i, codigo in enumerate(["71002", "71003", "71004"]):
        _crear_activo(sqlite_db, codigo, f"ClientY{i}x")
        cid = _crear_contacto(sqlite_db, codigo, "71001")
        t0 = datetime(2026, 7, 23, 12, 0, 0) + timedelta(days=i)
        _insert_msg(sqlite_db, cid, codigo, "Msg cliente", t0.strftime("%Y-%m-%d %H:%M:%S"))
        _insert_msg(
            sqlite_db,
            cid,
            "71001",
            "Tarde",
            (t0 + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        )

    assert sqlite_db.listar_respuestas_rapidas_regla5("71001") == []
    assert sqlite_db.evaluar_regla5_respuestas_chat("71001") is None


def test_regla5_al_enviar_mensaje_profesional(sqlite_db):
    _crear_activo(sqlite_db, "72001", "ProfesionalZ")
    clientes = ["72002", "72003", "72004"]
    for i, codigo in enumerate(clientes):
        _crear_activo(sqlite_db, codigo, f"ClientZ{i}x")

    now = _utcnow()
    # Dos clientes ya respondidos rápido
    for i, sol in enumerate(clientes[:2]):
        cid = _crear_contacto(sqlite_db, sol, "72001")
        t_cliente = now - timedelta(hours=3 - i)
        _insert_msg(sqlite_db, cid, sol, "Hola", t_cliente.strftime("%Y-%m-%d %H:%M:%S"))
        _insert_msg(
            sqlite_db,
            cid,
            "72001",
            "Ok",
            (t_cliente + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        )

    # Tercer cliente: mensaje cliente reciente + respuesta vía API
    cid3 = _crear_contacto(sqlite_db, clientes[2], "72001")
    t3 = now - timedelta(minutes=5)
    _insert_msg(sqlite_db, cid3, clientes[2], "Necesito servicio", t3.strftime("%Y-%m-%d %H:%M:%S"))

    assert sqlite_db.enviar_mensaje_chat(cid3, "72001", "Te respondo ya")["status"] == "success"

    assert _score(sqlite_db, "72001") == 53
    assert any(m.startswith("regla5_3_clientes_respuesta_1h_") for _, m in _motivos(sqlite_db, "72001"))


def test_regla5_solicitante_no_gana_puntos(sqlite_db):
    _crear_activo(sqlite_db, "73001", "ProfesionalW")
    _crear_activo(sqlite_db, "73002", "ClienteWww")
    cid = _crear_contacto(sqlite_db, "73002", "73001")
    t0 = _utcnow() - timedelta(minutes=1)
    _insert_msg(sqlite_db, cid, "73002", "Hola", t0.strftime("%Y-%m-%d %H:%M:%S"))
    assert sqlite_db.enviar_mensaje_chat(cid, "73002", "Otro msg cliente")["status"] == "success"
    assert _score(sqlite_db, "73002") == 50
    assert _motivos(sqlite_db, "73002") == []
