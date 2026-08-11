"""
Repositorio de Score RUANA.

Acceso a datos de score_movimientos, score de aliados y notificaciones de score.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

import json
from typing import Any, Optional


class ScoreRepo:
    """Operaciones de persistencia del dominio score."""

    def obtener_score(self, cursor, codigo_aliado: str) -> Optional[int]:
        cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (codigo_aliado,))
        row = cursor.fetchone()
        if not row:
            return None
        return int(row[0]) if row[0] is not None else 0

    def delta_score_hoy(self, cursor, codigo_aliado: str) -> int:
        """Suma de deltas aplicados hoy al aliado (para límite ±10/día)."""
        cursor.execute(
            """
            SELECT COALESCE(SUM(delta), 0) FROM score_movimientos
            WHERE codigo_aliado = ? AND date(creado_en) = date('now', 'localtime')
            """,
            (codigo_aliado,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def insertar_movimiento(
        self,
        cursor,
        codigo_aliado: str,
        delta_real: int,
        motivo: str,
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO score_movimientos (codigo_aliado, delta, motivo)
            VALUES (?, ?, ?)
            """,
            (codigo_aliado, delta_real, motivo),
        )
        return cursor.lastrowid

    def actualizar_score_aliado(self, cursor, codigo_aliado: str, score_nuevo: int) -> None:
        cursor.execute(
            """
            UPDATE aliados SET score = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
            """,
            (score_nuevo, codigo_aliado),
        )

    def registrar_notificacion_cambio_score(
        self,
        cursor,
        codigo_aliado: str,
        delta_real: int,
        score_nuevo: int,
        motivo: str,
        movimiento_id: Optional[int] = None,
    ) -> None:
        """Crea una notificación persistente por cada cambio real de score."""
        if not codigo_aliado or not delta_real:
            return
        try:
            direccion = "subió" if delta_real > 0 else "bajó"
            puntos = f"{delta_real:+d}"
            motivo_txt = (motivo or "actualización de reglas RUANA").strip()
            titulo = "Cambio en tu Score RUANA"
            mensaje = f"Tu score {direccion} {puntos} puntos. Motivo: {motivo_txt}."
            metadata = json.dumps(
                {
                    "delta": delta_real,
                    "score_final": int(score_nuevo),
                    "motivo": motivo_txt,
                    "movimiento_id": movimiento_id,
                },
                ensure_ascii=False,
            )
            cursor.execute(
                """
                INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                VALUES (?, 'score_change', ?, ?, ?, 0)
                """,
                (codigo_aliado, titulo, mensaje, metadata),
            )
        except Exception:
            # No romper el flujo principal de score si falla la notificación
            return
