"""Apelación de expulsión automática (art. 22 RGPD)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from unittest.mock import patch

from core.aliado_pin_auth import hash_pin
from core.services import admin_service, apelacion_service, chat_service, competencia_service
from core.services.aliado_pin_service import validar_login_aliado
from core.services.apelacion_service import (
    MENSAJE_APELACION,
    MENSAJE_ENLACE_INVALIDO,
    TIPO_APELACION,
    hash_token,
    sumar_dias_habiles,
)
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_apelacion.db"))


def _activo(db, codigo, oficio, cp, score=50, estado="activo", grupo_id=None):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@t.com",
        telefono=f"+346000{codigo[-4:]}",
        estado=estado,
        score=score,
    )
    assert r.get("status") == "success", r
    conn = db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET estado = ? WHERE codigo = ?", (estado, codigo))
    if grupo_id is not None:
        cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, codigo))
    conn.commit()
    conn.close()


def _forzar_segunda_derrota(db, titular="60041", retador="60042", cp="28221"):
    g1 = db.crear_grupo_en_cp(cp)
    g2 = db.crear_grupo_en_cp(cp)
    _activo(db, titular, "Albañilería", cp, score=5, grupo_id=g1["id"])
    _activo(db, retador, "Albañilería", cp, score=70, grupo_id=g2["id"])

    conn = db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET derrotas_competencia = 1 WHERE codigo = ?", (titular,))
    conn.commit()
    conn.close()

    db._iniciar_competencia_si_procede(titular)
    conn = db._connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM competencia WHERE aliado_original_codigo = ?", (titular,))
    cid = cur.fetchone()[0]
    cur.execute("UPDATE aliados SET score = 5 WHERE codigo = ?", (titular,))
    cur.execute("UPDATE aliados SET score = 90 WHERE codigo = ?", (retador,))
    cur.execute(
        "UPDATE competencia SET fecha_fin_prevista = ? WHERE id = ?",
        ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), cid),
    )
    conn.commit()
    conn.close()

    db.finalizar_competencia_activas_vencidas()
    return {
        "titular": titular,
        "retador": retador,
        "competencia_id": cid,
        "grupo_titular": g1["id"],
        "grupo_retador": g2["id"],
    }


def _conv_apelacion(db, aliado_codigo):
    filas = admin_service.listar_conversaciones_soporte_admin(
        db, aliado_codigo=aliado_codigo, tipo=TIPO_APELACION
    )
    assert filas, "No se abrió la conversación de apelación"
    return filas[0]


def test_sumar_dias_habiles_salta_fin_de_semana():
    viernes = datetime(2026, 9, 11, 10, 0, 0)
    sabado = datetime(2026, 9, 12, 10, 0, 0)
    assert sumar_dias_habiles(viernes, 5) == datetime(2026, 9, 18, 10, 0, 0)
    assert sumar_dias_habiles(sabado, 5) == datetime(2026, 9, 18, 10, 0, 0)


def test_segunda_derrota_abre_apelacion_y_notifica(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    titular = sqlite_db.obtener_aliado_por_codigo(ctx["titular"])
    assert titular["estado"] == "expulsado"
    assert titular["derrotas_competencia"] == 2

    conv = _conv_apelacion(sqlite_db, ctx["titular"])
    assert conv["tipo"] == TIPO_APELACION
    assert conv["estado"] == "pendiente"
    assert conv["fecha_limite_apelacion"]
    assert conv["apelacion_vencida"] is False

    mensajes = sqlite_db._connect()
    cur = mensajes.cursor()
    cur.execute(
        "SELECT emisor_tipo, mensaje FROM ruana_soporte_mensajes WHERE conversacion_id = ?",
        (conv["id"],),
    )
    filas = cur.fetchall()
    mensajes.close()
    assert any(row[0] == "sistema" and MENSAJE_APELACION in (row[1] or "") for row in filas)
    assert any(str(ctx["competencia_id"]) in (row[1] or "") for row in filas)

    notifs = sqlite_db.listar_notificaciones_aliado(ctx["titular"], limite=20)
    assert any(n.get("tipo") == "competencia_expulsion" for n in notifs)
    assert any(n.get("tipo") == "competencia_expulsion_apelacion" for n in notifs)
    assert any(MENSAJE_APELACION in (n.get("mensaje") or "") for n in notifs)

    segunda = apelacion_service.abrir_apelacion_expulsion_automatica(
        sqlite_db, ctx["titular"], ctx["competencia_id"]
    )
    assert segunda.get("status") == "exists"


def test_listar_filtra_y_ordena_apelaciones(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    chat_service.crear_conversacion_soporte_aliado(
        sqlite_db, ctx["retador"], "Consulta general", "Hola, una duda"
    )
    conv_real = _conv_apelacion(sqlite_db, ctx["titular"])
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO ruana_soporte_conversaciones
            (aliado_codigo, asunto, categoria, tipo, estado, ultimo_mensaje_preview,
             fecha_limite_apelacion, apelacion_metadata)
        VALUES (?, 'Apelación extra', 'apelacion_expulsion', ?, 'pendiente', 'preview',
                ?, ?)
        """,
        (
            ctx["titular"],
            TIPO_APELACION,
            "2026-09-10 09:00:00",
            '{"competencia_id": 999}',
        ),
    )
    conn.commit()
    conn.close()

    general = admin_service.listar_conversaciones_soporte_admin(sqlite_db)
    tipos_general = {c.get("tipo") or "consulta" for c in general}
    assert TIPO_APELACION in tipos_general
    assert any((c.get("tipo") or "consulta") != TIPO_APELACION for c in general)

    apelaciones = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, tipo=TIPO_APELACION
    )
    assert len(apelaciones) == 2
    assert all(c["tipo"] == TIPO_APELACION for c in apelaciones)
    assert apelaciones[0]["fecha_limite_apelacion"] <= apelaciones[1]["fecha_limite_apelacion"]
    assert apelaciones[0]["apelacion_vencida"] is True
    assert any(c["id"] == conv_real["id"] for c in apelaciones)


def test_resolver_aceptada_revierte_sin_devolver_plaza(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    perdedor_antes = sqlite_db.obtener_aliado_por_codigo(ctx["titular"])
    ganador_antes = sqlite_db.obtener_aliado_por_codigo(ctx["retador"])
    grupo_perdedor = perdedor_antes["grupo_id"]
    grupo_ganador = ganador_antes["grupo_id"]
    assert perdedor_antes["estado"] == "expulsado"
    assert perdedor_antes["score"] == 50
    assert perdedor_antes["derrotas_competencia"] == 2

    conv = _conv_apelacion(sqlite_db, ctx["titular"])
    result = apelacion_service.resolver_apelacion_expulsion(
        sqlite_db, conv["id"], "admin-test", "aceptada", "Error en el cierre"
    )
    assert result.get("status") == "success"
    assert result.get("decision") == "aceptada"

    perdedor = sqlite_db.obtener_aliado_por_codigo(ctx["titular"])
    ganador = sqlite_db.obtener_aliado_por_codigo(ctx["retador"])
    assert perdedor["estado"] == "activo"
    assert perdedor["score"] == 5
    assert perdedor["derrotas_competencia"] == 1
    assert perdedor["grupo_id"] == grupo_perdedor
    assert ganador["grupo_id"] == grupo_ganador
    assert ganador["grupo_id"] != perdedor["grupo_id"] or ganador["grupo_id"] == ctx["grupo_titular"]

    convs = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, aliado_codigo=ctx["titular"], tipo=TIPO_APELACION
    )
    assert convs[0]["estado"] == "resuelta"
    assert convs[0]["decision_apelacion"] == "aceptada"
    assert convs[0]["decision_admin_codigo"] == "admin-test"
    assert "Error en el cierre" in (convs[0]["decision_motivo"] or "")


def test_resolver_rechazada_deja_expulsion_firme(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    perdedor_antes = sqlite_db.obtener_aliado_por_codigo(ctx["titular"])
    conv = _conv_apelacion(sqlite_db, ctx["titular"])
    result = apelacion_service.resolver_apelacion_expulsion(
        sqlite_db, conv["id"], "admin-test", "rechazada", "La derrota es correcta"
    )
    assert result.get("status") == "success"

    perdedor = sqlite_db.obtener_aliado_por_codigo(ctx["titular"])
    assert perdedor["estado"] == "expulsado"
    assert perdedor["score"] == perdedor_antes["score"]
    assert perdedor["derrotas_competencia"] == perdedor_antes["derrotas_competencia"]
    assert perdedor["grupo_id"] == perdedor_antes["grupo_id"]

    convs = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, aliado_codigo=ctx["titular"], tipo=TIPO_APELACION
    )
    assert convs[0]["estado"] == "resuelta"
    assert convs[0]["decision_apelacion"] == "rechazada"


def test_job_vence_sin_respuesta_no_toca_negocio(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    conv = _conv_apelacion(sqlite_db, ctx["titular"])
    perdedor_antes = sqlite_db.obtener_aliado_por_codigo(ctx["titular"])

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE ruana_soporte_conversaciones SET fecha_limite_apelacion = ? WHERE id = ?",
        ("2020-01-01 00:00:00", conv["id"]),
    )
    conn.commit()
    conn.close()

    resultado = apelacion_service.cerrar_apelaciones_expulsion_vencidas(sqlite_db)
    assert resultado.get("status") == "ok"
    assert resultado.get("cerradas") == 1

    perdedor = sqlite_db.obtener_aliado_por_codigo(ctx["titular"])
    assert perdedor["estado"] == "expulsado"
    assert perdedor["score"] == perdedor_antes["score"]
    assert perdedor["derrotas_competencia"] == perdedor_antes["derrotas_competencia"]
    assert perdedor["grupo_id"] == perdedor_antes["grupo_id"]

    convs = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, aliado_codigo=ctx["titular"], tipo=TIPO_APELACION
    )
    assert convs[0]["estado"] == "vencida_sin_apelacion"
    assert convs[0]["decision_apelacion"] == "vencida_sin_apelacion"


def test_job_no_cierra_si_aliado_respondio(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    conv = _conv_apelacion(sqlite_db, ctx["titular"])
    chat_service.enviar_mensaje_soporte_aliado(
        sqlite_db, conv["id"], ctx["titular"], "Apelo esta expulsión."
    )
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE ruana_soporte_conversaciones SET fecha_limite_apelacion = ? WHERE id = ?",
        ("2020-01-01 00:00:00", conv["id"]),
    )
    conn.commit()
    conn.close()

    resultado = apelacion_service.cerrar_apelaciones_expulsion_vencidas(sqlite_db)
    assert resultado.get("cerradas") == 0
    convs = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, aliado_codigo=ctx["titular"], tipo=TIPO_APELACION
    )
    assert convs[0]["estado"] != "vencida_sin_apelacion"
    assert sqlite_db.obtener_aliado_por_codigo(ctx["titular"])["estado"] == "expulsado"


def test_purga_mensual_cierra_apelaciones_vencidas(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    conv = _conv_apelacion(sqlite_db, ctx["titular"])
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE ruana_soporte_conversaciones SET fecha_limite_apelacion = ? WHERE id = ?",
        ("2020-01-01 00:00:00", conv["id"]),
    )
    conn.commit()
    conn.close()

    resultado = competencia_service.purga_mensual(sqlite_db)
    assert resultado.get("status") == "ok"
    assert resultado.get("apelaciones_vencidas") == 1
    convs = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, aliado_codigo=ctx["titular"], tipo=TIPO_APELACION
    )
    assert convs[0]["estado"] == "vencida_sin_apelacion"


def test_login_expulsado_sigue_bloqueado(sqlite_db):
    ctx = _forzar_segunda_derrota(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE aliados SET pin_hash = ? WHERE codigo = ?",
        (hash_pin("1234"), ctx["titular"]),
    )
    conn.commit()
    conn.close()

    bloqueado = validar_login_aliado(sqlite_db, ctx["titular"], "1234")
    assert bloqueado.get("ok") is False
    assert bloqueado.get("http_status") == 403


def test_expulsion_genera_token_y_email(sqlite_db, monkeypatch):
    monkeypatch.setattr(apelacion_service, "generar_token_apelacion", lambda: "token-publico-test")
    with patch("core.email_service.enviar_correo_apelacion_expulsion", return_value=True) as mock_mail:
        ctx = _forzar_segunda_derrota(sqlite_db)
        assert mock_mail.called
        kwargs = mock_mail.call_args.kwargs
        assert "token-publico-test" in kwargs["enlace"]
        assert "/apelar/token-publico-test" in kwargs["enlace"]
        assert kwargs["email"] == f"{ctx['titular']}@t.com"

    conv = _conv_apelacion(sqlite_db, ctx["titular"])
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT apelacion_token_hash FROM ruana_soporte_conversaciones WHERE id = ?",
        (conv["id"],),
    )
    stored = cur.fetchone()[0]
    conn.close()
    assert stored == hash_token("token-publico-test")
    assert stored != "token-publico-test"


def test_ruta_publica_token_valido_invalido_y_expirado(sqlite_db, client, monkeypatch):
    from web.blueprints import soporte_bp as soporte_bp_mod
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(soporte_bp_mod, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(apelacion_service, "generar_token_apelacion", lambda: "token-publico-test")
    _forzar_segunda_derrota(sqlite_db)
    conv = _conv_apelacion(sqlite_db, "60041")

    pagina = client.get("/apelar/token-publico-test")
    assert pagina.status_code == 200
    html = pagina.get_data(as_text=True)
    assert "apelar-expulsion.js" in html
    assert "aliado-centro-comunicacion-module.js" in html

    ok = client.get("/api/apelar/token-publico-test")
    data = ok.get_json()
    assert ok.status_code == 200
    assert data["status"] == "success"
    assert data["conversacion_id"] == conv["id"]

    lista = client.get("/api/apelar/token-publico-test/centro-comunicacion")
    assert lista.status_code == 200
    assert lista.get_json()["conversaciones"][0]["id"] == conv["id"]

    msg = client.post(
        f"/api/apelar/token-publico-test/centro-comunicacion/{conv['id']}/mensajes",
        json={"mensaje": "Apelo esta expulsión."},
    )
    assert msg.status_code == 200
    assert msg.get_json()["status"] == "success"

    hilos = apelacion_service.listar_mensajes_apelacion_por_token(
        sqlite_db, "token-publico-test", conv["id"]
    )
    assert any("Apelo esta expulsión." in (m.get("mensaje") or "") for m in hilos)

    invalido = client.get("/api/apelar/token-que-no-existe")
    expirado_pagina = client.get("/apelar/token-que-no-existe")
    assert invalido.status_code == 404
    assert invalido.get_json()["message"] == MENSAJE_ENLACE_INVALIDO
    assert expirado_pagina.status_code == 200

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE ruana_soporte_conversaciones SET fecha_limite_apelacion = ? WHERE id = ?",
        ("2020-01-01 00:00:00", conv["id"]),
    )
    conn.commit()
    conn.close()
    vencido = client.get("/api/apelar/token-publico-test")
    assert vencido.status_code == 404
    assert vencido.get_json()["message"] == MENSAJE_ENLACE_INVALIDO
    assert vencido.get_json() == invalido.get_json()
