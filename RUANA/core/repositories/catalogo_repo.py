"""
Repositorio de Catálogo (Campamento Base).

Acceso a datos de oficios en aliados y catalogo_servicios_aliado.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence


class CatalogoRepo:
    """Operaciones de persistencia del dominio catálogo."""

    def listar_oficios_distintos_grupo_activo(self, cursor, grupo_id: int) -> List[Any]:
        cursor.execute(
            "SELECT DISTINCT oficio FROM aliados WHERE grupo_id = ? AND estado = 'activo' AND oficio IS NOT NULL AND oficio != ''",
            (grupo_id,),
        )
        return cursor.fetchall()

    def listar_oficios_distintos_todos(self, cursor) -> List[Any]:
        cursor.execute(
            "SELECT DISTINCT oficio FROM aliados WHERE oficio IS NOT NULL AND oficio != '' ORDER BY oficio"
        )
        return cursor.fetchall()

    def listar_servicios_aliado(self, cursor, codigo: str) -> List[Any]:
        cursor.execute(
            """
            SELECT posicion, descripcion, precio, actualizado_en
            FROM catalogo_servicios_aliado
            WHERE aliado_codigo = ?
            ORDER BY posicion ASC
            """,
            (codigo,),
        )
        return cursor.fetchall()

    def existe_aliado(self, cursor, codigo: str) -> bool:
        cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (codigo,))
        return cursor.fetchone() is not None

    def upsert_servicio_aliado(
        self,
        cursor,
        codigo: str,
        pos: int,
        desc_db: Optional[str],
        pr_db: Optional[str],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO catalogo_servicios_aliado (aliado_codigo, posicion, descripcion, precio, actualizado_en)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(aliado_codigo, posicion)
            DO UPDATE SET
                descripcion = excluded.descripcion,
                precio = excluded.precio,
                actualizado_en = CURRENT_TIMESTAMP
            """,
            (codigo, pos, desc_db, pr_db),
        )

    def contar_oficios_ocupados(self, cursor) -> int:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT oficio) FROM aliados
            WHERE estado = 'activo' AND oficio IS NOT NULL AND TRIM(oficio) != ''
            """
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0
