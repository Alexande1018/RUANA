"""Mensaje único de activación en el centro de comunicación, a los 3 días.

No crea tablas ni columnas. La conversación usa ruana_soporte_conversaciones.tipo
= 'activacion'. La fecha de corte se cambia con la variable de entorno
RUANA_ACTIVACION_FECHA_CORTE (YYYY-MM-DD). Si no está definida, vale
FECHA_CORTE_DEFECTO (el día de publicación). Si se publica otro día, hay
que cambiar esa constante o fijar la variable de entorno.

Los huecos (oficios del catálogo sin titular activo en el grupo) se calculan
al crear el mensaje y quedan escritos en el texto. Si no hay huecos, esa
línea no se añade.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import zlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.repositories.admin_repo import AdminRepo
from core.repositories.chat_repo import ChatRepo

logger = logging.getLogger(__name__)

_admin_repo = AdminRepo()
_chat_repo = ChatRepo()

TIPO_ACTIVACION = "activacion"
CATEGORIA_ACTIVACION = "activacion"
ASUNTO_ACTIVACION = "Tres preguntas rápidas"
DIAS_ACTIVACION = 3
ENV_FECHA_CORTE = "RUANA_ACTIVACION_FECHA_CORTE"
# Día de publicación del mensaje de activación. Si el merge cae otro día,
# cambia esta fecha o fija la variable RUANA_ACTIVACION_FECHA_CORTE.
FECHA_CORTE_DEFECTO = "2026-09-25"
MARCA_WHATSAPP = "Pásale tu código por WhatsApp"
TEXTO_SALTADO = "(saltado)"

# Oficios de reformas y hogar, en el orden en que se mencionan.
# La frase usa un nombre corto; el empareje es con el nombre real del catálogo.
HUECOS_PRIORITARIOS = (
    ("Electricidad", "electricista"),
    ("Fontanería y fontanería-gas", "fontanero"),
    ("Pintura y decoración", "pintor"),
    ("Albañilería y obra", "albañil"),
    ("Carpintería de madera e interior", "carpintero"),
    ("Carpintería de aluminio / PVC / metálica", "carpintero de aluminio"),
    ("Cerrajería", "cerrajero"),
    ("Climatización y calefacción", "climatización"),
)

MENSAJE_BASE = (
    "Llevas unos días en RUANA y queremos afinar tu zona. "
    "Tres preguntas rápidas, puedes saltarlas.\n\n"
    "1. ¿A qué oficio de tu zona le pasarías trabajo?\n"
    "2. ¿Tienes ahora mismo algún encargo que no puedas hacer tú?\n"
    "3. ¿Qué te frenaría para pasar tu primer encargo por RUANA?"
)


def fecha_corte() -> datetime:
    """Día desde el que un alta puede recibir el mensaje. Inclusive."""
    raw = (os.environ.get(ENV_FECHA_CORTE) or "").strip() or FECHA_CORTE_DEFECTO
    parsed = _parse_fecha_corte(raw)
    if parsed is None:
        logger.warning(
            "RUANA_ACTIVACION_FECHA_CORTE inválida (%s); se usa %s",
            raw,
            FECHA_CORTE_DEFECTO,
        )
        parsed = datetime.strptime(FECHA_CORTE_DEFECTO, "%Y-%m-%d")
    return parsed


def mensaje_activacion(linea: str = "") -> str:
    extra = str(linea or "").strip()
    if not extra:
        return MENSAJE_BASE
    return MENSAJE_BASE + "\n\n" + extra


def linea_huecos(oficios: List[str]) -> str:
    """Un párrafo con uno o dos oficios libres. Vacío si no hay huecos."""
    nombres = [_en_frase(o) for o in (oficios or []) if str(o or "").strip()]
    if not nombres:
        return ""
    if len(nombres) == 1:
        mencionado = nombres[0]
    else:
        mencionado = f"{nombres[0]} ni {nombres[1]}"
    return (
        f"En tu grupo aún no hay {mencionado}. "
        f"¿Conoces a uno bueno? {MARCA_WHATSAPP}"
    )


def elegir_huecos_para_frase(faltan: List[str]) -> List[str]:
    """Hasta dos huecos. Primero los de casa; si no hay, el resto del catálogo."""
    libres = {str(o).strip().casefold(): str(o).strip() for o in faltan if str(o or "").strip()}
    if not libres:
        return []
    prioritarios: List[str] = []
    for catalogo_nombre, en_frase in HUECOS_PRIORITARIOS:
        if catalogo_nombre.casefold() in libres:
            prioritarios.append(en_frase)
        if len(prioritarios) == 2:
            return prioritarios
    if prioritarios:
        return prioritarios
    resto = sorted(libres.values(), key=lambda nombre: nombre.casefold())
    return [_en_frase(nombre) for nombre in resto[:2]]


def oficios_hueco(db, grupo_id: Optional[int]) -> List[str]:
    """Huecos del grupo, ya en el orden y con el nombre que va en la frase.

    Un hueco es un oficio del catálogo sin aliado titular activo en el grupo,
    igual que oficios_faltantes de info_grupo_para_panel. Si la lectura falla,
    no hay línea: un error no es lo mismo que «ningún oficio ocupado».
    """
    if not grupo_id:
        return []
    try:
        ocupados = _leer_oficios_ocupados(db, int(grupo_id))
        catalogo = db.get_catalogo_oficios_ruana() or []
    except Exception:
        logger.exception("No se pudieron calcular los huecos del grupo %s", grupo_id)
        return []
    ocupados_txt = {str(o).strip() for o in ocupados if str(o or "").strip()}
    faltan = []
    for oficio in catalogo:
        nombre = str(oficio or "").strip()
        if nombre and nombre not in ocupados_txt:
            faltan.append(nombre)
    return elegir_huecos_para_frase(faltan)


def _leer_oficios_ocupados(db, grupo_id: int) -> set:
    """Misma lectura que obtener_oficios_grupo, pero el fallo se propaga.

    obtener_oficios_grupo traga la excepción y devuelve un conjunto vacío.
    Aquí eso se leería como «nadie ocupa ningún oficio» y el mensaje
    inventaría huecos. Si esta lectura falla, oficios_hueco no añade línea.
    """
    from core.repositories.catalogo_repo import CatalogoRepo

    conn = None
    try:
        conn = db._connect()
        cursor = conn.cursor()
        rows = CatalogoRepo().listar_oficios_distintos_grupo_activo(cursor, int(grupo_id))
        return {str(row[0]).strip() for row in (rows or []) if row and str(row[0] or "").strip()}
    finally:
        if conn is not None:
            conn.close()


def texto_respuesta_activacion(payload: Dict[str, Any]) -> str:
    """Texto que lee el admin. Vacío o saltar → '(saltado)'."""
    if not isinstance(payload, dict):
        return TEXTO_SALTADO
    if _es_verdadero(payload.get("saltar")):
        return TEXTO_SALTADO
    oficio = _oficio_en_mensaje(payload)
    encargo = _normalizar_encargo(payload.get("encargo"))
    freno = str(payload.get("freno") or "").strip()[:400]
    if not oficio and not encargo and not freno:
        return TEXTO_SALTADO
    return (
        f"Oficio: {oficio or '—'} / "
        f"Encargo ahora: {encargo or '—'} / "
        f"Freno: {freno or '—'}"
    )


def asegurar_conversacion_activacion(db, aliado_codigo: str) -> None:
    """Crea la conversación una sola vez. No rompe el listado si falla."""
    try:
        _asegurar(db, aliado_codigo)
    except Exception:
        logger.exception(
            "No se pudo crear el mensaje de activación",
            extra={"aliado_codigo": str(aliado_codigo or "").strip()},
        )


def guardar_respuesta_activacion(
    db, conversacion_id: int, aliado_codigo: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Guarda la respuesta (o el salto) como mensaje del aliado en el mismo hilo."""
    codigo = str(aliado_codigo or "").strip()
    if not codigo:
        return {"status": "error", "message": "Código requerido"}
    texto = texto_respuesta_activacion(payload if isinstance(payload, dict) else {})
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if _chat_repo.select_id_conversacion_soporte_aliado(cursor, conversacion_id, codigo) is None:
                return {"status": "error", "message": "Conversación no encontrada"}
            cursor.execute(
                """
                SELECT LOWER(TRIM(COALESCE(tipo, ''))) AS tipo
                FROM ruana_soporte_conversaciones
                WHERE id = ?
                """,
                (int(conversacion_id),),
            )
            fila = cursor.fetchone()
            tipo = fila["tipo"] if fila is not None else ""
            if tipo != TIPO_ACTIVACION:
                return {"status": "error", "message": "Esta conversación no es de activación"}
            if _ya_respondio(cursor, conversacion_id):
                return {"status": "error", "message": "Ya has respondido"}
            _chat_repo.insertar_mensaje_soporte_aliado(cursor, conversacion_id, codigo, texto)
            _chat_repo.update_conversacion_tras_mensaje_aliado(cursor, texto[:220], conversacion_id)
            meta = _metadata_respuesta(conversacion_id, payload if isinstance(payload, dict) else {}, texto)
            _admin_repo.insertar_evento_sistema(
                cursor,
                "activacion_respuesta",
                f"Respuesta de activación de {codigo}",
                "aliado",
                codigo,
                meta,
            )
            conn.commit()
            return {"status": "success"}
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.exception("No se pudo guardar la respuesta de activación")
            return {"status": "error", "message": str(exc)}
        finally:
            if conn is not None:
                conn.close()


def _asegurar(db, aliado_codigo: str) -> None:
    codigo = str(aliado_codigo or "").strip()
    if not codigo:
        return
    with db._lock:
        aliado = _leer_aliado(db, codigo)
        if not _es_elegible(aliado):
            return
        if _ya_existe(db, codigo):
            return
        grupo_id = aliado.get("grupo_id") if aliado else None
        linea = linea_huecos(oficios_hueco(db, grupo_id))
        _insertar_exclusivo(db, codigo, mensaje_activacion(linea))


def _es_elegible(aliado: Optional[Dict[str, Any]], ahora: Optional[datetime] = None) -> bool:
    if not aliado:
        return False
    if str(aliado.get("estado") or "").strip().lower() != "activo":
        return False
    creado = _parse_dt(aliado.get("creado_en"))
    if creado is None:
        return False
    ahora = ahora or datetime.now()
    if creado > ahora - timedelta(days=DIAS_ACTIVACION):
        return False
    return creado >= fecha_corte()


def _leer_aliado(db, codigo: str) -> Optional[Dict[str, Any]]:
    conn = None
    try:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT estado, creado_en, grupo_id
            FROM aliados
            WHERE TRIM(CAST(codigo AS TEXT)) = ?
            """,
            (codigo,),
        )
        fila = cursor.fetchone()
        return dict(fila) if fila is not None else None
    finally:
        if conn is not None:
            conn.close()


def _ya_existe(db, codigo: str) -> bool:
    conn = None
    try:
        conn = db._connect()
        cursor = conn.cursor()
        return _existe_en_cursor(cursor, codigo)
    finally:
        if conn is not None:
            conn.close()


def _existe_en_cursor(cursor, codigo: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM ruana_soporte_conversaciones
        WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?
          AND LOWER(TRIM(COALESCE(tipo, ''))) = ?
        LIMIT 1
        """,
        (codigo, TIPO_ACTIVACION),
    )
    return cursor.fetchone() is not None


def _insertar_exclusivo(db, codigo: str, mensaje: str) -> None:
    conn = None
    try:
        conn = db._connect()
        cursor = conn.cursor()
        _bloquear(cursor, db, codigo)
        if _existe_en_cursor(cursor, codigo):
            conn.rollback()
            return
        preview = mensaje[:220]
        cursor.execute(
            """
            INSERT INTO ruana_soporte_conversaciones
                (aliado_codigo, asunto, categoria, tipo, estado, ultimo_mensaje_preview,
                 tiene_no_leido_admin, tiene_no_leido_aliado)
            VALUES (?, ?, ?, ?, 'pendiente', ?, 0, 1)
            """,
            (codigo, ASUNTO_ACTIVACION, CATEGORIA_ACTIVACION, TIPO_ACTIVACION, preview),
        )
        conv_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO ruana_soporte_mensajes
                (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
            VALUES (?, 'sistema', 'RUANA', ?, 0, 1)
            """,
            (conv_id, mensaje),
        )
        cursor.execute(
            """
            UPDATE ruana_soporte_conversaciones
            SET ultimo_mensaje_en = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (conv_id,),
        )
        conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn is not None:
            conn.close()


def _bloquear(cursor, db, codigo: str) -> None:
    """Reserva la escritura entre procesos. Dentro del proceso ya está db._lock."""
    if getattr(db, "backend", "") == "postgres":
        clave = zlib.crc32(f"ruana-activacion:{codigo}".encode("utf-8")) & 0x7FFFFFFF
        cursor.execute("SELECT pg_advisory_xact_lock(?)", (int(clave),))
        return
    cursor.execute("BEGIN IMMEDIATE")


def _ya_respondio(cursor, conversacion_id: int) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM ruana_soporte_mensajes
        WHERE conversacion_id = ? AND emisor_tipo = 'aliado'
        LIMIT 1
        """,
        (int(conversacion_id),),
    )
    return cursor.fetchone() is not None


def _oficio_en_mensaje(payload: Dict[str, Any]) -> str:
    """Texto que ve el admin. El libre, si lo hay, manda sobre el desplegable."""
    libre = str(payload.get("oficio_libre") or "").strip()[:80]
    if libre:
        return libre
    return str(payload.get("oficio") or "").strip()[:80]


def _metadata_respuesta(conversacion_id: int, payload: Dict[str, Any], texto: str) -> str:
    """Solo indicadores. El texto libre se queda en el mensaje del aliado."""
    import json

    saltado = texto == TEXTO_SALTADO or _es_verdadero(payload.get("saltar"))
    datos: Dict[str, Any] = {
        "conversacion_id": int(conversacion_id),
        "respondio": not saltado,
        "saltado": saltado,
    }
    if saltado:
        return json.dumps(datos, ensure_ascii=False)
    datos["encargo"] = _normalizar_encargo(payload.get("encargo"))
    libre = str(payload.get("oficio_libre") or "").strip()
    if libre:
        datos["oficio_libre"] = True
    else:
        oficio = str(payload.get("oficio") or "").strip()[:80]
        datos["oficio_libre"] = False
        if oficio:
            datos["oficio"] = oficio
    return json.dumps(datos, ensure_ascii=False)


def _normalizar_encargo(valor: Any) -> str:
    texto = str(valor or "").strip().lower()
    if texto in ("si", "sí"):
        return "Sí"
    if texto == "no":
        return "No"
    return ""


def _es_verdadero(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    return str(valor or "").strip().lower() in ("1", "true", "si", "sí", "yes")


def _en_frase(nombre: str) -> str:
    texto = str(nombre or "").strip()
    if not texto:
        return texto
    return texto[0].lower() + texto[1:]


def _parse_fecha_corte(raw: str) -> Optional[datetime]:
    texto = str(raw or "").strip()
    if not texto:
        return None
    if len(texto) <= 10:
        try:
            return datetime.strptime(texto, "%Y-%m-%d")
        except ValueError:
            return None
    return _parse_dt(texto)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip().replace("Z", "").replace("T", " ")
        if not raw:
            return None
        for sep in ("+",):
            if sep in raw[10:]:
                raw = raw.split(sep, 1)[0].strip()
        if raw.endswith("-00:00"):
            raw = raw[: -len("-00:00")].strip()
        try:
            dt = datetime.fromisoformat(raw[:19])
        except ValueError:
            try:
                dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt
