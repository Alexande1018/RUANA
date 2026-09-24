"""Mensaje de activación a los 3 días, en el centro de comunicación."""
import json
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import activacion_soporte_service, admin_service, chat_service
from core.services.activacion_soporte_service import (
    MARCA_WHATSAPP,
    MENSAJE_BASE,
    TEXTO_SALTADO,
    TIPO_ACTIVACION,
)


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    monkeypatch.delenv("RUANA_ACTIVACION_FECHA_CORTE", raising=False)
    return db_module.DBManager(str(tmp_path / "ruana_activacion.db"))


def _aliado(db, codigo, oficio, cp, estado="activo", grupo_id=None, dias=4, sin_grupo=False):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@activacion.test",
        telefono=f"+34611{codigo}",
        estado=estado,
        score=50,
    )
    assert r.get("status") == "success", r
    creado = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE aliados SET estado = ?, creado_en = ? WHERE codigo = ?",
        (estado, creado, codigo),
    )
    if sin_grupo:
        cur.execute("UPDATE aliados SET grupo_id = NULL WHERE codigo = ?", (codigo,))
    elif grupo_id is not None:
        cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, codigo))
    conn.commit()
    conn.close()


def _grupo(db, cp):
    return db.crear_grupo_en_cp(cp)["id"]


def _contar(db, codigo):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM ruana_soporte_conversaciones
        WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?
          AND LOWER(TRIM(COALESCE(tipo, ''))) = ?
        """,
        (codigo, TIPO_ACTIVACION),
    )
    total = int(cur.fetchone()[0])
    conn.close()
    return total


def _mensaje_sistema(db, codigo):
    conn = db._connect()
    conn.row_factory = __import__("sqlite3").Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.mensaje, m.emisor_tipo, m.emisor_codigo, m.leido_por_aliado, m.leido_por_admin,
               c.id, c.asunto, c.categoria, c.estado, c.tipo,
               c.tiene_no_leido_aliado, c.tiene_no_leido_admin
        FROM ruana_soporte_mensajes m
        JOIN ruana_soporte_conversaciones c ON c.id = m.conversacion_id
        WHERE TRIM(CAST(c.aliado_codigo AS TEXT)) = ?
          AND LOWER(TRIM(COALESCE(c.tipo, ''))) = ?
        ORDER BY m.id ASC
        """,
        (codigo, TIPO_ACTIVACION),
    )
    fila = cur.fetchone()
    conn.close()
    return dict(fila) if fila else None


def test_el_texto_habla_de_encargo_y_no_repite_como_nos_conociste():
    assert "encargo" in MENSAJE_BASE
    assert "curro" not in MENSAJE_BASE.lower()
    assert "¿Cómo conociste RUANA?" not in MENSAJE_BASE
    assert "¿Tienes ahora mismo algún encargo que no puedas hacer tú?" in MENSAJE_BASE
    assert "¿Qué te frenaría para pasar tu primer encargo por RUANA?" in MENSAJE_BASE


def test_no_crea_antes_de_3_dias(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=2)
    filas = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    assert filas == []
    assert _contar(sqlite_db, "58848") == 0


def test_no_crea_si_no_esta_activo(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", estado="suspendido_temporal", dias=10)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    assert _contar(sqlite_db, "58848") == 0


def test_fecha_de_corte_excluye_altas_anteriores(sqlite_db, monkeypatch):
    corte = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    monkeypatch.setenv("RUANA_ACTIVACION_FECHA_CORTE", corte)
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=10)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    assert _contar(sqlite_db, "58848") == 0


def test_crea_a_los_3_dias_con_un_hueco(sqlite_db, monkeypatch):
    oficio = "Albañilería y obra"
    grupo_id = _grupo(sqlite_db, "03001")
    monkeypatch.setattr(
        sqlite_db,
        "get_catalogo_oficios_ruana",
        lambda: [oficio, "Electricidad"],
    )
    _aliado(sqlite_db, "58848", oficio, "03001", grupo_id=grupo_id, dias=3)
    filas = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    assert len(filas) == 1
    assert filas[0]["tipo"] == TIPO_ACTIVACION
    assert filas[0]["asunto"] == "Tres preguntas rápidas"
    assert int(filas[0]["tiene_no_leido_aliado"]) == 1
    msg = _mensaje_sistema(sqlite_db, "58848")
    assert msg["emisor_tipo"] == "sistema"
    assert msg["emisor_codigo"] == "RUANA"
    assert msg["estado"] == "pendiente"
    assert msg["categoria"] == TIPO_ACTIVACION
    assert int(msg["tiene_no_leido_admin"]) == 0
    assert int(msg["leido_por_aliado"]) == 0
    assert "curro" not in msg["mensaje"].lower()
    assert "En tu zona aún no hay electricista." in msg["mensaje"]
    assert "¿Conoces a uno bueno?" in msg["mensaje"]
    assert MARCA_WHATSAPP in msg["mensaje"]


def test_dos_huecos_caben_en_la_misma_linea(sqlite_db, monkeypatch):
    oficio = "Albañilería y obra"
    grupo_id = _grupo(sqlite_db, "03001")
    monkeypatch.setattr(
        sqlite_db,
        "get_catalogo_oficios_ruana",
        lambda: [oficio, "Electricidad", "Fontanería y fontanería-gas"],
    )
    _aliado(sqlite_db, "58848", oficio, "03001", grupo_id=grupo_id, dias=5)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    texto = _mensaje_sistema(sqlite_db, "58848")["mensaje"]
    assert "electricista ni fontanero" in texto
    assert "¿Conoces a uno bueno?" in texto
    assert "curro" not in texto.lower()
    assert MARCA_WHATSAPP in texto


def test_prioriza_oficios_de_casa_antes_que_el_resto(sqlite_db, monkeypatch):
    oficio = "Idiomas"
    grupo_id = _grupo(sqlite_db, "03001")
    monkeypatch.setattr(
        sqlite_db,
        "get_catalogo_oficios_ruana",
        lambda: [
            "Actividad física y salud básica",
            oficio,
            "Cerrajería",
            "Electricidad",
            "Clases particulares académicas",
        ],
    )
    _aliado(sqlite_db, "58848", oficio, "03001", grupo_id=grupo_id, dias=5)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    texto = _mensaje_sistema(sqlite_db, "58848")["mensaje"]
    assert "electricista ni cerrajero" in texto
    assert "actividad física" not in texto
    assert "curro" not in texto.lower()


def test_sin_oficios_de_casa_usa_el_resto_del_catalogo(sqlite_db, monkeypatch):
    oficio = "Idiomas"
    grupo_id = _grupo(sqlite_db, "03002")
    monkeypatch.setattr(
        sqlite_db,
        "get_catalogo_oficios_ruana",
        lambda: [oficio, "Actividad física y salud básica", "Clases particulares académicas"],
    )
    _aliado(sqlite_db, "58841", oficio, "03002", grupo_id=grupo_id, dias=5)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58841")
    texto = _mensaje_sistema(sqlite_db, "58841")["mensaje"]
    assert "actividad física y salud básica ni clases particulares académicas" in texto


def test_sin_huecos_no_anade_la_linea(sqlite_db, monkeypatch):
    oficio = "Albañilería y obra"
    grupo_id = _grupo(sqlite_db, "03001")
    monkeypatch.setattr(sqlite_db, "get_catalogo_oficios_ruana", lambda: [oficio])
    _aliado(sqlite_db, "58848", oficio, "03001", grupo_id=grupo_id, dias=5)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    texto = _mensaje_sistema(sqlite_db, "58848")["mensaje"]
    assert texto == MENSAJE_BASE
    assert MARCA_WHATSAPP not in texto
    assert "En tu zona aún no hay" not in texto


def test_sin_grupo_no_inventa_huecos(sqlite_db, monkeypatch):
    monkeypatch.setattr(
        sqlite_db,
        "get_catalogo_oficios_ruana",
        lambda: ["Electricidad", "Fontanería y fontanería-gas"],
    )
    _aliado(sqlite_db, "18001", "Electricidad", "18001", dias=8, sin_grupo=True)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "18001")
    texto = _mensaje_sistema(sqlite_db, "18001")["mensaje"]
    assert MARCA_WHATSAPP not in texto


def test_idempotente_aunque_el_hilo_se_oculte(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=6)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE ruana_soporte_conversaciones
        SET eliminada_por_aliado = 1, eliminada_por_admin = 1
        WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ? AND tipo = ?
        """,
        ("58848", TIPO_ACTIVACION),
    )
    conn.commit()
    conn.close()
    visibles = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    assert visibles == []
    assert _contar(sqlite_db, "58848") == 1


def test_idempotente_si_dos_cargas_coinciden(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=6)
    errores = []

    def cargar():
        try:
            chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
        except Exception as exc:  # pragma: no cover - el assert de abajo lo cuenta
            errores.append(exc)

    hilos = [threading.Thread(target=cargar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert errores == []
    assert _contar(sqlite_db, "58848") == 1


def test_guarda_respuesta_y_el_admin_la_ve(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=6)
    filas = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    conv_id = int(filas[0]["id"])
    resultado = activacion_soporte_service.guardar_respuesta_activacion(
        sqlite_db,
        conv_id,
        "58848",
        {"oficio": "Electricidad", "encargo": "Sí", "freno": "No conozco a nadie aún"},
    )
    assert resultado["status"] == "success"
    mensajes = chat_service.listar_mensajes_soporte_aliado(sqlite_db, conv_id, "58848")
    textos = [m["mensaje"] for m in mensajes if m["emisor_tipo"] == "aliado"]
    assert textos == ["Oficio: Electricidad / Encargo ahora: Sí / Freno: No conozco a nadie aún"]
    assert "curro" not in textos[0].lower()
    convs = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, aliado_codigo="58848", tipo=TIPO_ACTIVACION
    )
    assert int(convs[0]["tiene_no_leido_admin"]) == 1
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT metadata FROM eventos_sistema WHERE tipo = ? AND actor_codigo = ?",
        ("activacion_respuesta", "58848"),
    )
    meta = json.loads(cur.fetchone()[0])
    conn.close()
    assert meta["encargo"] == "Sí"
    assert meta["saltado"] is False
    assert meta["oficio"] == "Electricidad"
    repetido = activacion_soporte_service.guardar_respuesta_activacion(
        sqlite_db, conv_id, "58848", {"oficio": "Otra"}
    )
    assert repetido["status"] == "error"


def test_saltar_guarda_marca_corta(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=6)
    conv_id = int(chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")[0]["id"])
    resultado = activacion_soporte_service.guardar_respuesta_activacion(
        sqlite_db, conv_id, "58848", {"saltar": True, "oficio": "no debería guardarse"}
    )
    assert resultado["status"] == "success"
    mensajes = chat_service.listar_mensajes_soporte_aliado(sqlite_db, conv_id, "58848")
    assert [m["mensaje"] for m in mensajes if m["emisor_tipo"] == "aliado"] == [TEXTO_SALTADO]


def test_admin_filtra_por_cp_y_muestra_la_columna(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=6)
    _aliado(sqlite_db, "18001", "Fontanería", "18001", dias=6)
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")
    chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "18001")
    solo = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, codigo_postal="03001", tipo=TIPO_ACTIVACION
    )
    assert [c["aliado_codigo"] for c in solo] == ["58848"]
    assert solo[0]["aliado_codigo_postal"] == "03001"
    otro = admin_service.listar_conversaciones_soporte_admin(
        sqlite_db, codigo_postal="18001", tipo=TIPO_ACTIVACION
    )
    assert [c["aliado_codigo"] for c in otro] == ["18001"]


def test_marcar_leido_incluye_mensaje_de_sistema(sqlite_db):
    _aliado(sqlite_db, "58848", "Electricidad", "03001", dias=6)
    conv_id = int(chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "58848")[0]["id"])
    assert chat_service.marcar_soporte_leido_aliado(sqlite_db, conv_id, "58848")["status"] == "success"
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT leido_por_aliado FROM ruana_soporte_mensajes WHERE conversacion_id = ? AND emisor_tipo = 'sistema'",
        (conv_id,),
    )
    assert int(cur.fetchone()[0]) == 1
    cur.execute(
        "SELECT tiene_no_leido_aliado FROM ruana_soporte_conversaciones WHERE id = ?",
        (conv_id,),
    )
    assert int(cur.fetchone()[0]) == 0
    conn.close()
