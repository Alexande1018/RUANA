"""
Servicio de Score RUANA.

Reglas de mutación de score: rango [0, 500], tope ±10 por día.
La orquestación de competencia por umbral permanece en la fachada DBManager.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.repositories.score_repo import ScoreRepo

_SCORE_MIN = 0
_SCORE_MAX = 500
_DELTA_DIA_MAX = 10


def calcular_delta_aplicar(delta: int, delta_hoy: int) -> int:
    """Aplica el tope diario ±10 al delta solicitado."""
    if delta > 0:
        techo_dia = _DELTA_DIA_MAX - delta_hoy
        return min(delta, max(0, techo_dia))
    piso_dia = -_DELTA_DIA_MAX - delta_hoy
    return max(delta, min(0, piso_dia))


def calcular_score_nuevo(score_actual: int, delta_aplicar: int) -> tuple[int, int]:
    """Devuelve (score_nuevo, delta_real) respetando [0, 500]."""
    score_nuevo = max(_SCORE_MIN, min(_SCORE_MAX, score_actual + delta_aplicar))
    delta_real = score_nuevo - score_actual
    return score_nuevo, delta_real


def aplicar_cambio_score(
    cursor,
    codigo_aliado: str,
    delta: int,
    motivo: str = "",
    repo: Optional[ScoreRepo] = None,
) -> Dict[str, Any]:
    """
    Aplica un cambio de score en el cursor dado (sin commit ni side-effects externos).

    Returns:
        Dict con status, aplicado, score_final y, si hubo cambio o no-op con aliado,
        score_anterior. No dispara competencia.
    """
    if not codigo_aliado or delta == 0:
        return {"status": "success", "aplicado": 0, "score_final": None}

    repo = repo or ScoreRepo()
    score_actual = repo.obtener_score(cursor, codigo_aliado)
    if score_actual is None:
        return {
            "status": "error",
            "message": f"Aliado {codigo_aliado} no encontrado",
        }

    delta_hoy = repo.delta_score_hoy(cursor, codigo_aliado)
    delta_aplicar = calcular_delta_aplicar(delta, delta_hoy)
    score_nuevo, delta_real = calcular_score_nuevo(score_actual, delta_aplicar)

    if delta_real == 0:
        return {
            "status": "success",
            "aplicado": 0,
            "score_final": score_actual,
            "score_anterior": score_actual,
        }

    movimiento_id = repo.insertar_movimiento(cursor, codigo_aliado, delta_real, motivo)
    repo.actualizar_score_aliado(cursor, codigo_aliado, score_nuevo)
    repo.registrar_notificacion_cambio_score(
        cursor=cursor,
        codigo_aliado=codigo_aliado,
        delta_real=delta_real,
        score_nuevo=score_nuevo,
        motivo=motivo,
        movimiento_id=movimiento_id,
    )
    return {
        "status": "success",
        "aplicado": delta_real,
        "score_final": score_nuevo,
        "score_anterior": score_actual,
    }
