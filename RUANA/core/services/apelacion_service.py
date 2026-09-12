"""Apelación de expulsión automática (art. 22 RGPD).

No altera el cierre de competencia. Abre un canal de soporte con plazo
de 5 días hábiles y permite al admin aceptar o rechazar la apelación.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.services import notificacion_service

logger = logging.getLogger(__name__)

TIPO_APELACION = "apelacion_expulsion"
ESTADOS_ABIERTOS = ("pendiente", "en_revision", "respondido", "reabierto")
MENSAJE_APELACION = (
    "Has sido expulsado de RUANA por perder dos competencias de plaza. "
    "Tienes 5 días hábiles desde esta notificación para apelar respondiendo a este mensaje. "
    "Si no se recibe apelación en ese plazo, la expulsión queda firme."
)


def sumar_dias_habiles(inicio: datetime, dias: int) -> datetime:
    """Suma días laborables (lunes–viernes). No cuenta sábados ni domingos."""
    actual = inicio
    anadidos = 0
    while anadidos < dias:
        actual += timedelta(days=1)
        if actual.weekday() < 5:
            anadidos += 1
    return actual


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _ahora() -> datetime:
    return datetime.now()


def _json_dumps(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _json_loads(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _score_al_cierre(cursor, competencia_id: int, perdedor: str) -> Optional[int]:
    cursor.execute(
        """
        SELECT ganador_codigo, aliado_original_codigo, retador_codigo,
               score_titular_final, score_retador_final, oficio
        FROM competencia WHERE id = ?
        """,
        (int(competencia_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    if hasattr(row, "keys"):
        data = dict(row)
    else:
        data = {
            "ganador_codigo": row[0],
            "aliado_original_codigo": row[1],
            "retador_codigo": row[2],
            "score_titular_final": row[3],
            "score_retador_final": row[4],
            "oficio": row[5],
        }
    if (data.get("aliado_original_codigo") or "").strip() == perdedor:
        val = data.get("score_titular_final")
    else:
        val = data.get("score_retador_final")
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _oficio_competencia(cursor, competencia_id: int) -> str:
    cursor.execute("SELECT oficio FROM competencia WHERE id = ?", (int(competencia_id),))
    row = cursor.fetchone()
    if not row:
        return ""
    return (row[0] if not hasattr(row, "keys") else row["oficio"] or "") or ""


def aliado_tiene_apelacion_abierta(db, aliado_codigo: str, ahora: Optional[datetime] = None) -> bool:
    codigo = (aliado_codigo or "").strip()
    if not codigo:
        return False
    limite = ahora or _ahora()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, fecha_limite_apelacion, estado
                FROM ruana_soporte_conversaciones
                WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?
                  AND COALESCE(tipo, '') = ?
                  AND COALESCE(eliminada_por_admin, 0) = 0
                  AND LOWER(TRIM(COALESCE(estado, ''))) IN (?, ?, ?, ?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (codigo, TIPO_APELACION, *ESTADOS_ABIERTOS),
            )
            row = cursor.fetchone()
            if not row:
                return False
            fecha_limite = _parse_dt(row["fecha_limite_apelacion"])
            if fecha_limite and fecha_limite < limite:
                cursor.execute(
                    """
                    SELECT 1 FROM ruana_soporte_mensajes
                    WHERE conversacion_id = ? AND emisor_tipo = 'aliado'
                    LIMIT 1
                    """,
                    (row["id"],),
                )
                return cursor.fetchone() is not None
            return True
        except Exception as e:
            logger.warning(
                "Fallo al comprobar apelación abierta",
                extra={"aliado_codigo": codigo, "error": str(e)},
                exc_info=True,
            )
            return False
        finally:
            if conn:
                conn.close()


def abrir_apelacion_expulsion_automatica(
    db,
    aliado_codigo: str,
    competencia_id: int,
) -> Dict[str, Any]:
    """Crea la conversación de apelación y notifica. No cambia estado ni plaza."""
    codigo = (aliado_codigo or "").strip()
    if not codigo or not competencia_id:
        return {"status": "error", "message": "Aliado y competencia obligatorios"}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, apelacion_metadata FROM ruana_soporte_conversaciones
                WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?
                  AND COALESCE(tipo, '') = ?
                  AND COALESCE(eliminada_por_admin, 0) = 0
                """,
                (codigo, TIPO_APELACION),
            )
            competencia_id_int = int(competencia_id)
            for previa in cursor.fetchall():
                meta_prev = _json_loads(previa["apelacion_metadata"])
                try:
                    cid_prev = int(meta_prev.get("competencia_id"))
                except (TypeError, ValueError):
                    continue
                if cid_prev == competencia_id_int:
                    return {"status": "exists", "message": "Apelación ya abierta para esta competencia"}

            cursor.execute(
                """
                SELECT estado, score, grupo_id, COALESCE(derrotas_competencia, 0) AS derrotas, oficio
                FROM aliados WHERE codigo = ?
                """,
                (codigo,),
            )
            aliado = cursor.fetchone()
            if not aliado:
                return {"status": "error", "message": "Aliado no encontrado"}

            oficio = _oficio_competencia(cursor, competencia_id) or (aliado["oficio"] or "")
            score_cierre = _score_al_cierre(cursor, competencia_id, codigo)
            ahora = _ahora()
            fecha_limite = sumar_dias_habiles(ahora, 5)
            metadata = {
                "competencia_id": int(competencia_id),
                "oficio": oficio,
                "score_al_cierre": score_cierre,
                "grupo_id_tras_cierre": aliado["grupo_id"],
                "derrotas_tras_cierre": int(aliado["derrotas"] or 0),
                "estado_anterior": "activo",
                "fecha_expulsion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
            }
            asunto = f"Apelación de expulsión · competencia {int(competencia_id)}"
            fecha_txt = ahora.strftime("%d/%m/%Y")
            mensaje = (
                f"Competencia #{int(competencia_id)} · oficio {oficio or '—'} · fecha {fecha_txt}. "
                f"{MENSAJE_APELACION}"
            )
            cursor.execute(
                """
                INSERT INTO ruana_soporte_conversaciones
                    (aliado_codigo, asunto, categoria, tipo, estado, ultimo_mensaje_preview,
                     tiene_no_leido_admin, tiene_no_leido_aliado, fecha_limite_apelacion,
                     apelacion_metadata)
                VALUES (?, ?, 'apelacion_expulsion', ?, 'pendiente', ?, 1, 1, ?, ?)
                """,
                (
                    codigo,
                    asunto[:160],
                    TIPO_APELACION,
                    mensaje[:220],
                    fecha_limite.strftime("%Y-%m-%d %H:%M:%S"),
                    _json_dumps(metadata),
                ),
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
            notificacion_service.crear_notificacion_aliado(
                db,
                codigo,
                "competencia_expulsion_apelacion",
                "Puedes apelar tu expulsión",
                mensaje,
                metadata={
                    "conversacion_id": conv_id,
                    "competencia_id": int(competencia_id),
                    "oficio": oficio,
                    "fecha_limite_apelacion": fecha_limite.strftime("%Y-%m-%d %H:%M:%S"),
                    "origen": "apelacion_expulsion",
                },
                cursor=cursor,
            )
            conn.commit()
            return {
                "status": "success",
                "conversacion_id": conv_id,
                "fecha_limite_apelacion": fecha_limite.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            logger.error(
                "Fallo al abrir apelación de expulsión",
                extra={"aliado_codigo": codigo, "competencia_id": competencia_id, "error": str(e)},
                exc_info=True,
            )
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def _revertir_expulsion_por_apelacion(cursor, codigo: str, metadata: Dict[str, Any]) -> None:
    """Readmite al expulsado sin tocar la plaza del ganador.

    Restaura estado=activo, el score que tenía al cierre y resta una derrota.
    El grupo se deja como quedó tras la derrota (formación o NULL).
    """
    score = metadata.get("score_al_cierre")
    try:
        score_int = int(score) if score is not None else None
    except (TypeError, ValueError):
        score_int = None
    if score_int is None:
        cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
        score_int = int((row[0] if row else 50) or 50)
    cursor.execute(
        """
        UPDATE aliados
        SET estado = 'activo',
            score = ?,
            derrotas_competencia = CASE
                WHEN COALESCE(derrotas_competencia, 0) > 0
                THEN COALESCE(derrotas_competencia, 0) - 1
                ELSE 0
            END,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE codigo = ?
        """,
        (score_int, codigo),
    )


def resolver_apelacion_expulsion(
    db,
    conversacion_id: int,
    admin_codigo: str,
    decision: str,
    motivo: str,
) -> Dict[str, Any]:
    decision_norm = (decision or "").strip().lower()
    if decision_norm not in ("aceptada", "rechazada"):
        return {"status": "error", "message": "La decisión debe ser aceptada o rechazada"}
    motivo_txt = (motivo or "").strip()
    if not motivo_txt:
        return {"status": "error", "message": "Motivo obligatorio"}
    admin = (admin_codigo or "").strip() or "admin"
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, aliado_codigo, tipo, estado, apelacion_metadata, fecha_limite_apelacion
                FROM ruana_soporte_conversaciones
                WHERE id = ? AND COALESCE(eliminada_por_admin, 0) = 0
                """,
                (int(conversacion_id),),
            )
            conv = cursor.fetchone()
            if not conv:
                return {"status": "error", "message": "Conversación no encontrada"}
            if (conv["tipo"] or "") != TIPO_APELACION:
                return {"status": "error", "message": "La conversación no es una apelación de expulsión"}
            estado_actual = (conv["estado"] or "").strip().lower()
            if estado_actual in ("resuelta", "vencida_sin_apelacion"):
                return {"status": "error", "message": "La apelación ya está cerrada"}
            codigo = (conv["aliado_codigo"] or "").strip()
            metadata = _json_loads(conv["apelacion_metadata"])
            if decision_norm == "aceptada":
                _revertir_expulsion_por_apelacion(cursor, codigo, metadata)
                mensaje_admin = (
                    f"Apelación aceptada. Se readmite al aliado {codigo} "
                    f"(estado activo, score restaurado al del cierre, una derrota menos). "
                    f"Motivo: {motivo_txt}"
                )
                titulo_notif = "Tu apelación ha sido aceptada"
                mensaje_notif = (
                    "Un administrador ha aceptado tu apelación. Vuelves a estar activo en RUANA. "
                    f"Motivo: {motivo_txt}"
                )
            else:
                mensaje_admin = f"Apelación rechazada. La expulsión queda firme. Motivo: {motivo_txt}"
                titulo_notif = "Tu apelación ha sido rechazada"
                mensaje_notif = (
                    "Un administrador ha rechazado tu apelación. La expulsión queda firme. "
                    f"Motivo: {motivo_txt}"
                )
            cursor.execute(
                """
                INSERT INTO ruana_soporte_mensajes
                    (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
                VALUES (?, 'admin', ?, ?, 0, 1)
                """,
                (int(conversacion_id), admin, mensaje_admin),
            )
            cursor.execute(
                """
                UPDATE ruana_soporte_conversaciones
                SET estado = 'resuelta',
                    decision_apelacion = ?,
                    decision_admin_codigo = ?,
                    decision_motivo = ?,
                    ultimo_mensaje_preview = ?,
                    ultimo_mensaje_en = CURRENT_TIMESTAMP,
                    actualizado_en = CURRENT_TIMESTAMP,
                    tiene_no_leido_aliado = 1,
                    tiene_no_leido_admin = 0
                WHERE id = ?
                """,
                (decision_norm, admin, motivo_txt[:500], mensaje_admin[:220], int(conversacion_id)),
            )
            notificacion_service.crear_notificacion_aliado(
                db,
                codigo,
                "ruana_soporte_estado",
                titulo_notif,
                mensaje_notif,
                metadata={
                    "conversacion_id": int(conversacion_id),
                    "decision": decision_norm,
                    "origen": "apelacion_expulsion",
                },
                cursor=cursor,
            )
            conn.commit()
            return {
                "status": "success",
                "decision": decision_norm,
                "aliado_codigo": codigo,
                "conversacion_id": int(conversacion_id),
            }
        except Exception as e:
            logger.error(
                "Fallo al resolver apelación de expulsión",
                extra={"conversacion_id": conversacion_id, "admin_codigo": admin, "error": str(e)},
                exc_info=True,
            )
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def cerrar_apelaciones_expulsion_vencidas(
    db, ahora: Optional[datetime] = None
) -> Dict[str, Any]:
    """Cierra apelaciones sin respuesta del aliado cuyo plazo ya pasó. No toca negocio."""
    limite = ahora or _ahora()
    cerradas = []
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.id, c.aliado_codigo, c.fecha_limite_apelacion
                FROM ruana_soporte_conversaciones c
                WHERE COALESCE(c.tipo, '') = ?
                  AND COALESCE(c.eliminada_por_admin, 0) = 0
                  AND LOWER(TRIM(COALESCE(c.estado, ''))) IN (?, ?, ?, ?)
                  AND c.fecha_limite_apelacion IS NOT NULL
                  AND c.fecha_limite_apelacion < ?
                  AND NOT EXISTS (
                      SELECT 1 FROM ruana_soporte_mensajes m
                      WHERE m.conversacion_id = c.id AND m.emisor_tipo = 'aliado'
                  )
                """,
                (TIPO_APELACION, *ESTADOS_ABIERTOS, limite.strftime("%Y-%m-%d %H:%M:%S")),
            )
            filas = [dict(r) for r in cursor.fetchall()]
            mensaje = (
                "Plazo de apelación vencido sin respuesta del aliado. "
                "La expulsión queda firme."
            )
            for fila in filas:
                cid = int(fila["id"])
                cursor.execute(
                    """
                    INSERT INTO ruana_soporte_mensajes
                        (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
                    VALUES (?, 'sistema', 'RUANA', ?, 1, 1)
                    """,
                    (cid, mensaje),
                )
                cursor.execute(
                    """
                    UPDATE ruana_soporte_conversaciones
                    SET estado = 'vencida_sin_apelacion',
                        decision_apelacion = 'vencida_sin_apelacion',
                        decision_motivo = ?,
                        ultimo_mensaje_preview = ?,
                        ultimo_mensaje_en = CURRENT_TIMESTAMP,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (mensaje, mensaje[:220], cid),
                )
                cerradas.append(cid)
            conn.commit()
            return {
                "status": "ok",
                "cerradas": len(cerradas),
                "conversacion_ids": cerradas,
            }
        except Exception as e:
            logger.error(
                "Fallo al cerrar apelaciones vencidas",
                extra={"error": str(e)},
                exc_info=True,
            )
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            return {"status": "error", "message": str(e), "cerradas": 0, "conversacion_ids": []}
        finally:
            if conn:
                conn.close()
