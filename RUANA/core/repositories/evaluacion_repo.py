"""
Repositorio de Evaluaciones (Motor RUANA).

Acceso a datos de evaluaciones y evaluaciones_historico.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class EvaluacionRepo:
    """Operaciones de persistencia del dominio evaluación."""

    def select_estado_score(
        self, cursor, codigo_aliado: str
    ) -> Optional[Tuple[Any, Any]]:
        cursor.execute(
            "SELECT estado, score FROM evaluaciones WHERE codigo_aliado = ?",
            (codigo_aliado,),
        )
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

    def insertar_historico(
        self,
        cursor,
        codigo_aliado: str,
        estado_anterior: Any,
        estado_nuevo: str,
        score_anterior: Any,
        score_nuevo: float,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO evaluaciones_historico
            (codigo_aliado, estado_anterior, estado_nuevo, score_anterior, score_nuevo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (codigo_aliado, estado_anterior, estado_nuevo, score_anterior, score_nuevo),
        )

    def actualizar(
        self,
        cursor,
        codigo_aliado: str,
        estado: str,
        score: float,
        intencion: str,
        tasa_respuesta: float,
        tasa_confirmacion: float,
        meses_sin_trabajo: int,
        ciclos_consecutivos: int,
        razones_str: str,
        severidad: str,
    ) -> None:
        cursor.execute(
            """
            UPDATE evaluaciones
            SET estado = ?, score = ?, intencion = ?, tasa_respuesta = ?,
                tasa_confirmacion = ?, meses_sin_trabajo = ?, ciclos_consecutivos = ?,
                razones = ?, severidad = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo_aliado = ?
            """,
            (
                estado,
                score,
                intencion,
                tasa_respuesta,
                tasa_confirmacion,
                meses_sin_trabajo,
                ciclos_consecutivos,
                razones_str,
                severidad,
                codigo_aliado,
            ),
        )

    def insertar(
        self,
        cursor,
        codigo_aliado: str,
        estado: str,
        score: float,
        intencion: str,
        tasa_respuesta: float,
        tasa_confirmacion: float,
        meses_sin_trabajo: int,
        ciclos_consecutivos: int,
        razones_str: str,
        severidad: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO evaluaciones
            (codigo_aliado, estado, score, intencion, tasa_respuesta,
             tasa_confirmacion, meses_sin_trabajo, ciclos_consecutivos, razones, severidad)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
            ),
        )

    def select_por_codigo(
        self, cursor, codigo_aliado: str
    ) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM evaluaciones WHERE codigo_aliado = ?",
            (codigo_aliado,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def listar(self, cursor, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        if estado:
            cursor.execute(
                "SELECT * FROM evaluaciones WHERE estado = ? ORDER BY actualizado_en DESC",
                (estado,),
            )
        else:
            cursor.execute(
                "SELECT * FROM evaluaciones ORDER BY actualizado_en DESC"
            )
        return [dict(row) for row in cursor.fetchall()]

    def select_historico(
        self, cursor, codigo_aliado: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT * FROM evaluaciones_historico
            WHERE codigo_aliado = ?
            ORDER BY registrado_en DESC
            LIMIT 100
            """,
            (codigo_aliado,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def conteo_por_estado(self, cursor) -> Dict[str, Any]:
        cursor.execute(
            "SELECT estado, COUNT(*) as cantidad FROM evaluaciones GROUP BY estado"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def conteo_por_severidad(self, cursor) -> Dict[str, Any]:
        cursor.execute(
            "SELECT severidad, COUNT(*) as cantidad FROM evaluaciones GROUP BY severidad"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def score_promedio(self, cursor) -> float:
        cursor.execute("SELECT AVG(score) FROM evaluaciones")
        row = cursor.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    def total_evaluados(self, cursor) -> int:
        cursor.execute("SELECT COUNT(*) FROM evaluaciones")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
