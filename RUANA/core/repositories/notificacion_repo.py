"""
Repositorio de Notificaciones de aliado.

Acceso a datos de notificaciones_aliado.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


class NotificacionRepo:
    """Operaciones de persistencia del dominio notificación."""

    def insertar(
        self,
        cursor,
        aliado_codigo: str,
        tipo: str,
        titulo: str,
        mensaje: str,
        metadata_json: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (aliado_codigo, tipo, titulo, mensaje, metadata_json),
        )

    def listar_por_aliado(
        self, cursor, aliado_codigo: str, limite: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, aliado_codigo, tipo, titulo, mensaje, metadata, leida, creado_en
            FROM notificaciones_aliado
            WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?
            ORDER BY creado_en DESC
            LIMIT ?
            """,
            (aliado_codigo, limite),
        )
        return [dict(r) for r in cursor.fetchall()]

    def marcar_leida(self, cursor, notificacion_id: int, aliado_codigo: str) -> int:
        cursor.execute(
            "UPDATE notificaciones_aliado SET leida = 1 WHERE id = ? AND TRIM(CAST(aliado_codigo AS TEXT)) = ?",
            (notificacion_id, aliado_codigo),
        )
        return cursor.rowcount

    def marcar_todas_leidas(self, cursor, aliado_codigo: str) -> int:
        cursor.execute(
            "UPDATE notificaciones_aliado SET leida = 1 WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ? AND leida = 0",
            (aliado_codigo,),
        )
        return cursor.rowcount

    def marcar_contacto_leidas(
        self,
        cursor,
        aliado_codigo: str,
        contacto_id: int,
        tipos: Optional[Sequence[str]] = None,
    ) -> int:
        condiciones = [
            "TRIM(CAST(aliado_codigo AS TEXT)) = ?",
            "leida = 0",
            "(metadata LIKE ? OR metadata LIKE ?)",
        ]
        params: List[Any] = [
            aliado_codigo,
            f'%"contacto_id": {int(contacto_id)}%',
            f'%"contacto_id":{int(contacto_id)}%',
        ]
        tipos_norm = [str(t or "").strip() for t in (tipos or []) if str(t or "").strip()]
        if tipos_norm:
            condiciones.append("tipo IN (" + ",".join(["?"] * len(tipos_norm)) + ")")
            params.extend(tipos_norm)

        cursor.execute(
            "UPDATE notificaciones_aliado SET leida = 1 WHERE " + " AND ".join(condiciones),
            params,
        )
        return cursor.rowcount
