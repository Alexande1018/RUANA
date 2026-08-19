"""Repositorio de recompensas por crecimiento orgánico de grupos."""

from __future__ import annotations

from typing import Any, List, Optional


class GrupoCrecimientoRepo:
    """Persistencia de recompensas de crecimiento de grupo."""

    def contar_recompensas(self, cursor, invitador_codigo: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM grupo_crecimiento_recompensas
            WHERE invitador_codigo = ?
            """,
            (invitador_codigo,),
        )
        row = cursor.fetchone()
        return int(row[0] or 0) if row else 0

    def existe_recompensa(
        self, cursor, invitador_codigo: str, invitado_codigo: str
    ) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM grupo_crecimiento_recompensas
            WHERE invitador_codigo = ? AND invitado_codigo = ?
            LIMIT 1
            """,
            (invitador_codigo, invitado_codigo),
        )
        return cursor.fetchone() is not None

    def insertar_recompensa(
        self,
        cursor,
        invitador_codigo: str,
        invitado_codigo: str,
        invitacion_codigo: str,
        grupo_id: Optional[int],
        score_delta: int,
    ) -> bool:
        cursor.execute(
            """
            INSERT OR IGNORE INTO grupo_crecimiento_recompensas
            (invitador_codigo, invitado_codigo, invitacion_codigo, grupo_id, score_delta)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                invitador_codigo,
                invitado_codigo,
                invitacion_codigo,
                grupo_id,
                score_delta,
            ),
        )
        return cursor.rowcount > 0

    def listar_recompensas(
        self, cursor, invitador_codigo: str, limite: int = 20
    ) -> List[Any]:
        cursor.execute(
            """
            SELECT invitador_codigo, invitado_codigo, invitacion_codigo,
                   grupo_id, score_delta, creado_en
            FROM grupo_crecimiento_recompensas
            WHERE invitador_codigo = ?
            ORDER BY creado_en ASC
            LIMIT ?
            """,
            (invitador_codigo, limite),
        )
        return cursor.fetchall()
