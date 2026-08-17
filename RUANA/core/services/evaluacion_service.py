"""Servicio de dominio evaluación (Motor RUANA).

Extracción desde DBManager. Las fachadas permanecen en DBManager.
SQL de evaluaciones vía EvaluacionRepo.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from core.repositories.evaluacion_repo import EvaluacionRepo

_repo = EvaluacionRepo()


def _parse_razones(item: Dict[str, Any]) -> Dict[str, Any]:
    if item.get("razones"):
        try:
            item["razones"] = json.loads(item["razones"])
        except Exception:
            item["razones"] = []
    return item


def guardar_evaluacion(
    db,
    codigo_aliado: str,
    estado: str,
    score: float,
    intencion: str = "",
    tasa_respuesta: float = 0.0,
    tasa_confirmacion: float = 0.0,
    meses_sin_trabajo: int = 0,
    ciclos_consecutivos: int = 1,
    razones: list = None,
    severidad: str = "normal",
) -> Dict[str, Any]:
    """
    Guarda o actualiza la evaluación de un aliado

    Args:
        codigo_aliado: Código del aliado
        estado: Estado (verde, amarillo, rojo)
        score: Score de 0-500
        intencion: Intención (mantener, vigilar, evaluar_suplencia)
        tasa_respuesta: Métrica de respuesta (0-1)
        tasa_confirmacion: Métrica de confirmación (0-1)
        meses_sin_trabajo: Meses sin trabajo
        ciclos_consecutivos: Ciclos consecutivos en este estado
        razones: Lista de razones del estado
        severidad: normal, alerta, critico

    Returns:
        Dict con resultado de la operación
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            resultado = _repo.select_estado_score(cursor, codigo_aliado)
            razones_str = json.dumps(razones or [], ensure_ascii=False)

            if resultado:
                estado_anterior, score_anterior = resultado

                if estado_anterior != estado or score_anterior != score:
                    _repo.insertar_historico(
                        cursor,
                        codigo_aliado,
                        estado_anterior,
                        estado,
                        score_anterior,
                        score,
                    )

                _repo.actualizar(
                    cursor,
                    codigo_aliado,
                    estado,
                    score,
                    intencion,
                    tasa_respuesta,
                    tasa_confirmacion,
                    meses_sin_trabajo,
                    ciclos_consecutivos,
                    razones_str,
                    severidad,
                )
            else:
                _repo.insertar(
                    cursor,
                    codigo_aliado,
                    estado,
                    score,
                    intencion,
                    tasa_respuesta,
                    tasa_confirmacion,
                    meses_sin_trabajo,
                    ciclos_consecutivos,
                    razones_str,
                    severidad,
                )

            conn.commit()

            return {
                "status": "success",
                "codigo_aliado": codigo_aliado,
                "estado": estado,
                "score": score,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def obtener_evaluacion(db, codigo_aliado: str) -> Optional[Dict[str, Any]]:
    """Obtiene la evaluación más reciente de un aliado"""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            resultado = _repo.select_por_codigo(cursor, codigo_aliado)
            if not resultado:
                return None

            return _parse_razones(resultado)

        except Exception as e:
            print(f"Error obteniendo evaluación: {e}")
            return None
        finally:
            conn.close()


def listar_evaluaciones(db, estado: str = None) -> List[Dict[str, Any]]:
    """
    Lista evaluaciones, opcionalmente filtradas por estado

    Args:
        estado: Estado a filtrar (verde, amarillo, rojo) - opcional

    Returns:
        Lista de evaluaciones
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            rows = _repo.listar(cursor, estado)
            return [_parse_razones(item) for item in rows]

        except Exception as e:
            print(f"Error listando evaluaciones: {e}")
            return []
        finally:
            conn.close()


def obtener_historico_evaluaciones(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """Obtiene el histórico de cambios de evaluación de un aliado"""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            return _repo.select_historico(cursor, codigo_aliado)

        except Exception as e:
            print(f"Error obteniendo histórico: {e}")
            return []
        finally:
            conn.close()


def obtener_estadisticas_evaluaciones(db) -> Dict[str, Any]:
    """Obtiene estadísticas generales de las evaluaciones"""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            por_estado = _repo.conteo_por_estado(cursor)
            por_severidad = _repo.conteo_por_severidad(cursor)
            score_promedio = _repo.score_promedio(cursor)
            total_evaluados = _repo.total_evaluados(cursor)

            return {
                "total_evaluados": total_evaluados,
                "por_estado": por_estado,
                "por_severidad": por_severidad,
                "score_promedio": round(score_promedio, 2),
            }

        except Exception as e:
            print(f"Error obteniendo estadísticas: {e}")
            return {}
        finally:
            conn.close()


def ejecutar_motor_periodico(db) -> Dict[str, Any]:
    """Evalúa todos los aliados activos con MotorEvaluacion v0.2 y persiste resultados."""
    from engines.motor_evaluacion import MotorEvaluacion
    from core.services import admin_service

    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT TRIM(CAST(codigo AS TEXT)) FROM aliados WHERE estado = 'activo'"
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

    codigos: List[str] = []
    for row in rows:
        if isinstance(row, dict):
            cod = row.get("codigo")
        elif hasattr(row, "keys"):
            cod = row["codigo"]
        else:
            cod = row[0]
        if cod:
            codigos.append(str(cod).strip())

    metricas: Dict[str, Dict[str, Any]] = {}
    for codigo in codigos:
        metricas[codigo] = admin_service.obtener_metricas_motor_por_aliado(db, codigo)

    motor = MotorEvaluacion()
    decisiones = motor.evaluate_all(metricas)
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0}
    for decision in decisiones:
        estado = (decision.get("estado") or "").lower()
        if estado in resumen:
            resumen[estado] += 1

    return {
        "status": "success",
        "evaluados": len(decisiones),
        "resumen_estados": resumen,
    }
