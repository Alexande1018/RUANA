"""Vista de solo lectura de TODAS las solicitudes para el panel admin.

Junta en una sola lista:
- solicitudes semanales («Solicitudes de esta semana», tabla ``solicitudes_semanales``
  + respuestas en ``solicitudes_semanales_respuestas``), y
- solicitudes de conexión («Nuevas conexiones», tabla ``solicitudes``).

Todas las semanas y todos los estados, con texto completo, respuestas y candidatos.

Es estrictamente de lectura: no expira solicitudes, no hace commit y no cambia
nada del flujo del aliado, de pagos, del 5 %, de puntos ni de encargos externos.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TIPO_SEMANAL = "semanal"
TIPO_CONEXION = "conexion"
TIPOS = (TIPO_SEMANAL, TIPO_CONEXION)

# Tope de filas leídas por tabla (el volumen real es pequeño; la paginación
# se hace después de unir las dos fuentes).
MAX_FILAS_POR_TABLA = 5000
LIMITE_POR_DEFECTO = 50
LIMITE_MAXIMO = 200

_RESPUESTA_ES_CANDIDATO = ("puedo_ayudar", "conozco_alguien")


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------

def _json_safe_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return value


def _row_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    try:
        data = dict(row)
    except Exception:
        return {}
    return {str(k): _json_safe_value(v) for k, v in data.items()}


def _rows(cursor) -> List[Dict[str, Any]]:
    return [_row_dict(r) for r in cursor.fetchall()]


def _columnas(cursor, tabla: str) -> List[str]:
    try:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return [str(r[1]) for r in cursor.fetchall()]
    except Exception:
        return []


def _semana_inicio_de(valor: Any) -> str:
    """Lunes (YYYY-MM-DD) de la semana de una fecha ISO; '' si no se puede."""
    if not valor:
        return ""
    try:
        d = date.fromisoformat(str(valor)[:10])
    except ValueError:
        return ""
    return (d - timedelta(days=d.weekday())).isoformat()


def _semana_actual() -> str:
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def _texto(v: Any) -> str:
    return str(v or "").strip()


def _limpiar_limite(limite: Any) -> int:
    try:
        n = int(limite)
    except (TypeError, ValueError):
        n = LIMITE_POR_DEFECTO
    return max(1, min(n, LIMITE_MAXIMO))


def _limpiar_offset(offset: Any) -> int:
    try:
        n = int(offset)
    except (TypeError, ValueError):
        n = 0
    return max(0, n)


def _abrir(db):
    conn = db._connect()
    try:
        conn.row_factory = sqlite3.Row
    except Exception:
        pass
    return conn


def _cerrar(conn) -> None:
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# lectura de cada fuente
# ---------------------------------------------------------------------------

def _leer_semanales(cursor) -> List[Dict[str, Any]]:
    cursor.execute(
        """
        SELECT s.*, g.nombre AS grupo_nombre
        FROM solicitudes_semanales s
        LEFT JOIN grupos g ON g.id = s.grupo_id
        ORDER BY s.created_at DESC
        LIMIT ?
        """,
        (MAX_FILAS_POR_TABLA,),
    )
    filas = _rows(cursor)
    ids = [int(f["id"]) for f in filas if f.get("id") is not None]
    conteos: Dict[int, Dict[str, int]] = {}
    if ids:
        # Conteos por tipo en una sola consulta (sin IN gigante: agregamos todo).
        cursor.execute(
            """
            SELECT solicitud_semanal_id, tipo_respuesta, COUNT(*) AS n
            FROM solicitudes_semanales_respuestas
            GROUP BY solicitud_semanal_id, tipo_respuesta
            """
        )
        for r in _rows(cursor):
            sid = int(r.get("solicitud_semanal_id") or 0)
            conteos.setdefault(sid, {})[_texto(r.get("tipo_respuesta"))] = int(r.get("n") or 0)
    semana = _semana_actual()
    out = []
    for f in filas:
        c = conteos.get(int(f.get("id") or 0), {})
        out.append({
            "tipo": TIPO_SEMANAL,
            "id": f.get("id"),
            "grupo_id": f.get("grupo_id"),
            "grupo_nombre": f.get("grupo_nombre") or "",
            "solicitante_codigo": f.get("solicitante_codigo") or "",
            "solicitante_nombre": f.get("solicitante_nombre") or "",
            "oficio": f.get("oficio") or "",
            "descripcion": f.get("descripcion") or "",
            "estado": f.get("estado") or "",
            "created_at": f.get("created_at"),
            "semana_inicio": f.get("semana_inicio") or _semana_inicio_de(f.get("created_at")),
            "es_semana_actual": str(f.get("semana_inicio") or "") == semana,
            "expira_at": f.get("expira_at"),
            "respuestas_count": sum(c.values()),
            "pueden_ayudar_count": c.get("puedo_ayudar", 0),
            "recomiendan_count": c.get("conozco_alguien", 0),
            "no_pueden_count": c.get("no_puedo_ayudar", 0),
            "atendido_por_nombre": "",
            "atendido_por_codigo": "",
        })
    return out


def _leer_conexion(cursor) -> List[Dict[str, Any]]:
    cols = _columnas(cursor, "solicitudes")
    if "solicitante_codigo" not in cols:
        logger.warning(
            "admin_solicitudes: la tabla solicitudes no tiene solicitante_codigo (columnas=%s)",
            cols,
        )
        return []
    cursor.execute(
        """
        SELECT s.*, g.nombre AS grupo_nombre
        FROM solicitudes s
        LEFT JOIN grupos g ON g.id = s.grupo_id
        ORDER BY s.created_at DESC
        LIMIT ?
        """,
        (MAX_FILAS_POR_TABLA,),
    )
    semana = _semana_actual()
    out = []
    for f in _rows(cursor):
        sem = _semana_inicio_de(f.get("created_at"))
        candidato = f.get("candidato_por_nombre") or f.get("candidato_por_codigo")
        out.append({
            "tipo": TIPO_CONEXION,
            "id": f.get("id"),
            "grupo_id": f.get("grupo_id"),
            "grupo_nombre": f.get("grupo_nombre") or "",
            "solicitante_codigo": f.get("solicitante_codigo") or "",
            "solicitante_nombre": f.get("solicitante_nombre") or "",
            "oficio": f.get("oficio") or "",
            "descripcion": f.get("descripcion") or "",
            "estado": f.get("estado") or "",
            "created_at": f.get("created_at"),
            "semana_inicio": sem,
            "es_semana_actual": sem == semana,
            "destino": f.get("destino") or "",
            "respuestas_count": 1 if (f.get("atendido_por_codigo") or candidato) else 0,
            "pueden_ayudar_count": 1 if f.get("atendido_por_codigo") else 0,
            "recomiendan_count": 1 if candidato else 0,
            "no_pueden_count": 0,
            "atendido_por_nombre": f.get("atendido_por_nombre") or "",
            "atendido_por_codigo": f.get("atendido_por_codigo") or "",
        })
    return out


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def listar_todas(
    db,
    *,
    tipo: str = "",
    estado: str = "",
    grupo: str = "",
    semana: str = "",
    q: str = "",
    limite: Any = LIMITE_POR_DEFECTO,
    offset: Any = 0,
) -> Dict[str, Any]:
    """Lista paginada de solicitudes semanales + de conexión (solo lectura)."""
    tipo = _texto(tipo).lower()
    if tipo and tipo not in TIPOS:
        return {"status": "error", "message": "tipo debe ser 'semanal' o 'conexion'", "http": 400}
    estado = _texto(estado).lower()
    grupo = _texto(grupo)
    semana = _texto(semana)
    if semana:
        semana = _semana_inicio_de(semana)
        if not semana:
            return {"status": "error", "message": "semana debe ser una fecha YYYY-MM-DD", "http": 400}
    q = _texto(q).lower()
    limite = _limpiar_limite(limite)
    offset = _limpiar_offset(offset)

    items: List[Dict[str, Any]] = []
    avisos: List[str] = []
    fuentes = [t for t in TIPOS if not tipo or t == tipo]
    with db._lock:
        conn = None
        try:
            conn = _abrir(db)
            cursor = conn.cursor()
            for fuente in fuentes:
                lector = _leer_semanales if fuente == TIPO_SEMANAL else _leer_conexion
                try:
                    items.extend(lector(cursor))
                except Exception as exc:  # una fuente rota no tapa la otra
                    logger.exception("admin_solicitudes: fallo leyendo %s", fuente)
                    avisos.append(f"No se pudieron leer las solicitudes de tipo {fuente}: {exc}")
        except Exception as exc:
            logger.exception("admin_solicitudes: fallo abriendo conexión")
            return {"status": "error", "message": str(exc), "http": 500}
        finally:
            _cerrar(conn)

    estados = sorted({_texto(i.get("estado")) for i in items if i.get("estado")})
    semanas = sorted({i.get("semana_inicio") for i in items if i.get("semana_inicio")}, reverse=True)

    def _pasa(i: Dict[str, Any]) -> bool:
        if estado and _texto(i.get("estado")).lower() != estado:
            return False
        if grupo:
            if grupo.isdigit():
                if str(i.get("grupo_id") or "") != grupo:
                    return False
            elif grupo.lower() not in _texto(i.get("grupo_nombre")).lower():
                return False
        if semana and i.get("semana_inicio") != semana:
            return False
        if q:
            pajar = " ".join(
                _texto(i.get(k)).lower()
                for k in ("solicitante_nombre", "solicitante_codigo", "oficio", "descripcion", "grupo_nombre")
            )
            if q not in pajar:
                return False
        return True

    filtrados = [i for i in items if _pasa(i)]
    filtrados.sort(key=lambda i: (str(i.get("created_at") or ""), str(i.get("tipo"))), reverse=True)
    total = len(filtrados)
    pagina = filtrados[offset: offset + limite]
    return {
        "status": "success",
        "items": pagina,
        "total": total,
        "limit": limite,
        "offset": offset,
        "semana_actual": _semana_actual(),
        "filtros_disponibles": {"tipos": list(TIPOS), "estados": estados, "semanas": semanas},
        "avisos": avisos,
    }


def _aliado_basico(cursor, codigo: Any) -> Optional[Dict[str, Any]]:
    codigo = _texto(codigo)
    if not codigo:
        return None
    try:
        cursor.execute(
            """
            SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.estado,
                   a.telefono, a.email, a.grupo_id, g.nombre AS grupo_nombre
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            WHERE TRIM(CAST(a.codigo AS TEXT)) = ?
            """,
            (codigo,),
        )
        row = cursor.fetchone()
    except Exception:
        logger.exception("admin_solicitudes: fallo leyendo aliado %s", codigo)
        return None
    return _row_dict(row) if row else None


def _invitacion(cursor, codigo: Any) -> Optional[Dict[str, Any]]:
    codigo = _texto(codigo)
    if not codigo:
        return None
    try:
        cursor.execute("SELECT * FROM invitaciones WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
    except Exception:
        logger.exception("admin_solicitudes: fallo leyendo invitación")
        return None
    return _row_dict(row) if row else None


def _detalle_semanal(cursor, solicitud_id: int) -> Optional[Dict[str, Any]]:
    cursor.execute(
        """
        SELECT s.*, g.nombre AS grupo_nombre
        FROM solicitudes_semanales s
        LEFT JOIN grupos g ON g.id = s.grupo_id
        WHERE s.id = ?
        """,
        (int(solicitud_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    solicitud = _row_dict(row)
    solicitud["semana_actual"] = _semana_actual()
    solicitud["es_semana_actual"] = str(solicitud.get("semana_inicio") or "") == _semana_actual()
    cursor.execute(
        """
        SELECT * FROM solicitudes_semanales_respuestas
        WHERE solicitud_semanal_id = ?
        ORDER BY created_at ASC
        """,
        (int(solicitud_id),),
    )
    respuestas = _rows(cursor)
    candidatos = []
    for r in respuestas:
        aliado = _aliado_basico(cursor, r.get("aliado_codigo"))
        if aliado:
            r["aliado"] = aliado
        inv = _invitacion(cursor, r.get("invitacion_codigo"))
        if inv:
            r["invitacion"] = inv
        if _texto(r.get("tipo_respuesta")) in _RESPUESTA_ES_CANDIDATO:
            candidatos.append({
                "origen": r.get("tipo_respuesta"),
                "codigo": r.get("aliado_codigo"),
                "nombre": r.get("aliado_nombre"),
                "oficio": (aliado or {}).get("oficio"),
                "contacto_id": r.get("contacto_id"),
                "invitacion_codigo": r.get("invitacion_codigo"),
                "invitacion_usada": (inv or {}).get("usado"),
                "fecha": r.get("created_at"),
            })
    return {
        "solicitud": solicitud,
        "respuestas": respuestas,
        "candidatos": candidatos,
        "invitaciones": [r["invitacion"] for r in respuestas if r.get("invitacion")],
    }


def _detalle_conexion(cursor, solicitud_id: int) -> Optional[Dict[str, Any]]:
    cursor.execute(
        """
        SELECT s.*, g.nombre AS grupo_nombre
        FROM solicitudes s
        LEFT JOIN grupos g ON g.id = s.grupo_id
        WHERE s.id = ?
        """,
        (int(solicitud_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    s = _row_dict(row)
    s["semana_inicio"] = _semana_inicio_de(s.get("created_at"))
    candidatos = []
    vistos = set()

    def _add(origen, codigo, nombre, fecha=None, extra=None):
        codigo = _texto(codigo)
        if not codigo and not _texto(nombre):
            return
        clave = (origen, codigo)
        if clave in vistos:
            return
        vistos.add(clave)
        aliado = _aliado_basico(cursor, codigo)
        item = {
            "origen": origen,
            "codigo": codigo,
            "nombre": nombre or (aliado or {}).get("nombre"),
            "oficio": (aliado or {}).get("oficio"),
            "fecha": fecha,
        }
        if extra:
            item.update(extra)
        candidatos.append(item)

    _add("asignada_a", s.get("asignada_a_codigo"), s.get("asignada_a_nombre"))
    _add("proximidad", s.get("proximidad_codigo"), s.get("proximidad_nombre"), None, {
        "cp": s.get("proximidad_cp"),
        "zona": s.get("proximidad_zona"),
        "estado": s.get("proximidad_estado"),
    })
    _add("candidato", s.get("candidato_por_codigo"), s.get("candidato_por_nombre"), s.get("candidato_at"))
    _add("atendido_por", s.get("atendido_por_codigo"), s.get("atendido_por_nombre"), s.get("atendido_at"))

    respuestas = []
    if s.get("atendido_por_codigo") or s.get("atendido_por_nombre"):
        respuestas.append({
            "tipo_respuesta": "atendida",
            "aliado_codigo": s.get("atendido_por_codigo"),
            "aliado_nombre": s.get("atendido_por_nombre"),
            "created_at": s.get("atendido_at"),
        })
    if s.get("candidato_por_codigo") or s.get("candidato_por_nombre"):
        respuestas.append({
            "tipo_respuesta": "candidato",
            "aliado_codigo": s.get("candidato_por_codigo"),
            "aliado_nombre": s.get("candidato_por_nombre"),
            "created_at": s.get("candidato_at"),
        })

    invitaciones: List[Dict[str, Any]] = []
    if "solicitud_id" in _columnas(cursor, "invitaciones"):
        try:
            cursor.execute("SELECT * FROM invitaciones WHERE solicitud_id = ?", (int(solicitud_id),))
            invitaciones = _rows(cursor)
        except Exception:
            logger.exception("admin_solicitudes: fallo leyendo invitaciones de la solicitud")
    return {
        "solicitud": s,
        "respuestas": respuestas,
        "candidatos": candidatos,
        "invitaciones": invitaciones,
    }


def obtener_detalle(db, tipo: str, solicitud_id: Any) -> Dict[str, Any]:
    """Detalle completo de una solicitud (solo lectura)."""
    tipo = _texto(tipo).lower()
    if tipo not in TIPOS:
        return {"status": "error", "message": "tipo debe ser 'semanal' o 'conexion'", "http": 400}
    try:
        sid = int(solicitud_id)
    except (TypeError, ValueError):
        return {"status": "error", "message": "id no válido", "http": 400}
    with db._lock:
        conn = None
        try:
            conn = _abrir(db)
            cursor = conn.cursor()
            lector = _detalle_semanal if tipo == TIPO_SEMANAL else _detalle_conexion
            data = lector(cursor, sid)
            if data is None:
                return {"status": "error", "message": "Solicitud no encontrada", "http": 404}
            data["solicitante"] = _aliado_basico(cursor, data["solicitud"].get("solicitante_codigo"))
        except Exception as exc:
            logger.exception("admin_solicitudes: fallo leyendo detalle %s/%s", tipo, sid)
            return {"status": "error", "message": str(exc), "http": 500}
        finally:
            _cerrar(conn)
    data["tipo"] = tipo
    data["status"] = "success"
    return data
