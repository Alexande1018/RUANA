"""Servicio de crecimiento orgánico de grupos profesionales."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from core.db_constants import (
    CRECIMIENTO_GRUPO_MAX_RECOMPENSAS,
    CRECIMIENTO_GRUPO_SCORE_DELTA,
    GRUPO_EN_CREACION_MAX_ALIADOS,
    INVITACION_TIPO_CRECIMIENTO_GRUPO,
    SCORE_MOTIVO_ALIADO_INVITADO_REGISTRADO,
)
from core.repositories.grupo_crecimiento_repo import GrupoCrecimientoRepo

_repo = GrupoCrecimientoRepo()


def es_grupo_en_creacion(num_aliados_activos: int) -> bool:
    """Grupo en creación: 0 a 10 aliados activos inclusive."""
    try:
        n = int(num_aliados_activos)
    except (TypeError, ValueError):
        n = 0
    return n <= GRUPO_EN_CREACION_MAX_ALIADOS


def motivo_score_aliado_invitado(codigo_invitado: str) -> str:
    codigo = (codigo_invitado or "").strip()
    return f"{SCORE_MOTIVO_ALIADO_INVITADO_REGISTRADO}_{codigo}"


def info_progreso_invitador(db, codigo_invitador: str) -> Dict[str, Any]:
    """Progreso de recompensas de crecimiento para el panel del aliado."""
    codigo = (codigo_invitador or "").strip()
    if not codigo:
        return {
            "recompensas_obtenidas": 0,
            "recompensas_max": CRECIMIENTO_GRUPO_MAX_RECOMPENSAS,
            "score_obtenido": 0,
            "score_max": CRECIMIENTO_GRUPO_MAX_RECOMPENSAS * CRECIMIENTO_GRUPO_SCORE_DELTA,
            "limite_alcanzado": False,
        }
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            obtenidas = _repo.contar_recompensas(cursor, codigo)
        except Exception:
            obtenidas = 0
        finally:
            if conn:
                conn.close()
    score_obtenido = obtenidas * CRECIMIENTO_GRUPO_SCORE_DELTA
    return {
        "recompensas_obtenidas": obtenidas,
        "recompensas_max": CRECIMIENTO_GRUPO_MAX_RECOMPENSAS,
        "score_obtenido": score_obtenido,
        "score_max": CRECIMIENTO_GRUPO_MAX_RECOMPENSAS * CRECIMIENTO_GRUPO_SCORE_DELTA,
        "limite_alcanzado": obtenidas >= CRECIMIENTO_GRUPO_MAX_RECOMPENSAS,
    }


def puede_crear_invitacion_crecimiento(db, codigo_invitador: str) -> Dict[str, Any]:
    """Valida si el aliado puede generar una invitación de crecimiento de grupo."""
    aliado = db.obtener_aliado_por_codigo(codigo_invitador)
    if not aliado:
        return {"ok": False, "message": "Aliado no encontrado"}
    if (aliado.get("estado") or "").strip().lower() != "activo":
        return {"ok": False, "message": "Aliado no autorizado para crear invitaciones"}
    grupo_id = aliado.get("grupo_id")
    if not grupo_id:
        return {"ok": False, "message": "No perteneces a un grupo"}
    num_aliados = db.contar_aliados_activos_grupo(int(grupo_id))
    if not es_grupo_en_creacion(num_aliados):
        return {
            "ok": False,
            "message": "Tu grupo ya está consolidado para esta acción",
        }
    return {"ok": True, "grupo_id": int(grupo_id), "num_aliados": num_aliados}


def otorgar_recompensa_registro(
    db,
    invitador_codigo: str,
    invitado_codigo: str,
    invitacion_codigo: str,
    grupo_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Otorga +5 Score al invitador cuando un referido de crecimiento de grupo se registra.
    Idempotente: no duplica recompensa por invitado ni por motivo de score.
    """
    invitador = (invitador_codigo or "").strip()
    invitado = (invitado_codigo or "").strip()
    codigo_inv = (invitacion_codigo or "").strip()
    if not invitador or not invitado:
        return {"otorgada": False, "motivo": "datos_incompletos"}
    if invitador == invitado:
        return {"otorgada": False, "motivo": "auto_invitacion"}

    motivo = motivo_score_aliado_invitado(invitado)
    if db._ya_aplicado_motivo_score(invitador, motivo):
        return {"otorgada": False, "motivo": "ya_aplicado"}

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if _repo.existe_recompensa(cursor, invitador, invitado):
                return {"otorgada": False, "motivo": "duplicado"}
            if _repo.contar_recompensas(cursor, invitador) >= CRECIMIENTO_GRUPO_MAX_RECOMPENSAS:
                return {"otorgada": False, "motivo": "limite_alcanzado"}
        except Exception:
            return {"otorgada": False, "motivo": "error_validacion"}
        finally:
            if conn:
                conn.close()

    resultado_score = db.aplicar_cambio_score(
        invitador, CRECIMIENTO_GRUPO_SCORE_DELTA, motivo
    )
    delta = int((resultado_score or {}).get("aplicado") or 0)
    if delta == 0:
        return {"otorgada": False, "motivo": "score_no_aplicado"}

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            insertado = _repo.insertar_recompensa(
                cursor,
                invitador,
                invitado,
                codigo_inv,
                grupo_id,
                delta,
            )
            conn.commit()
            if not insertado:
                return {"otorgada": False, "motivo": "auditoria_duplicada"}
        except Exception:
            return {"otorgada": True, "delta": delta, "motivo": "auditoria_pendiente"}
        finally:
            if conn:
                conn.close()

    return {
        "otorgada": True,
        "delta": delta,
        "motivo": motivo,
        "invitador": invitador,
        "invitado": invitado,
        "grupo_id": grupo_id,
        "invitacion_codigo": codigo_inv,
    }


def contar_recompensas_invitador(db, codigo_invitador: str) -> int:
    codigo = (codigo_invitador or "").strip()
    if not codigo:
        return 0
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.contar_recompensas(cursor, codigo)
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()
