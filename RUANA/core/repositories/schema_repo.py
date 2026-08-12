"""
Repositorio de Schema (Campamento Base).

Helpers de persistencia para PRAGMA / execute / control de migraciones.
NO contiene el DDL completo de _init_db ni el cuerpo de migraciones multi-paso:
esas sentencias siguen en schema_service porque moverlas es riesgoso
(orden, IF NOT EXISTS, renames, foreign_keys OFF/ON, datos plaza/oficio).

Uso previsto: schema_service delega introspección y ejecución puntual aquí.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence


class SchemaRepo:
    """Helpers de acceso a esquema SQLite (sin orquestar migraciones)."""

    def execute(self, cursor, *args) -> Any:
        return cursor.execute(*args)

    def executescript(self, cursor, script: str) -> Any:
        return cursor.executescript(script)

    def columnas_tabla(self, cursor, tabla: str) -> List[str]:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return [row[1] for row in cursor.fetchall()]

    def pragma_table_info(self, cursor, tabla: str) -> List[Any]:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return cursor.fetchall()

    def foreign_keys_off(self, cursor) -> None:
        cursor.execute("PRAGMA foreign_keys=OFF")

    def foreign_keys_on(self, cursor) -> None:
        cursor.execute("PRAGMA foreign_keys=ON")

    def migracion_aplicada(self, cursor, nombre: str) -> bool:
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = ?", (nombre,))
        return cursor.fetchone() is not None

    def registrar_migracion(self, cursor, nombre: str) -> None:
        cursor.execute("INSERT INTO migraciones (nombre) VALUES (?)", (nombre,))

    def tabla_existe(self, cursor, nombre: str) -> bool:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (nombre,),
        )
        return cursor.fetchone() is not None

    def add_column_if_missing(
        self, cursor, tabla: str, columna: str, def_sql: str
    ) -> bool:
        """Añade columna si no existe. Devuelve True si se ejecutó ALTER."""
        cols = self.columnas_tabla(cursor, tabla)
        if columna in cols:
            return False
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {def_sql}")
        return True

    def fetchone(self, cursor, sql: str, params: Sequence[Any] = ()) -> Optional[Any]:
        cursor.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, cursor, sql: str, params: Sequence[Any] = ()) -> List[Any]:
        cursor.execute(sql, params)
        return cursor.fetchall()
