"""
Repositorio de Grupos (Campamento Base).

Acceso a datos de grupos, avisos_grupo y grupo_oficio_cerrado,
más lecturas auxiliares de aliados ligadas al ciclo de grupo.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional


class GrupoRepo:
    """Operaciones de persistencia del dominio grupo."""

    def existe_nombre(self, cursor, nombre: str) -> bool:
        nombre_s = (nombre or "").strip()
        if not nombre_s:
            return False
        cursor.execute(
            "SELECT 1 FROM grupos WHERE TRIM(nombre) = ? COLLATE NOCASE LIMIT 1",
            (nombre_s,),
        )
        return cursor.fetchone() is not None

    def listar_activos_por_cp(self, cursor, codigo_postal: str) -> List[Any]:
        cursor.execute(
            """SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion,
                      COALESCE(tipo, 'territorial') AS tipo
               FROM grupos WHERE codigo_postal = ? AND estado = 'activo'
                 AND COALESCE(tipo, 'territorial') = 'territorial'
               ORDER BY id""",
            (codigo_postal,),
        )
        return cursor.fetchall()

    def tiene_oficio(self, cursor, grupo_id: int, oficio: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM aliados WHERE grupo_id = ? AND oficio = ? AND estado = 'activo' LIMIT 1",
            (grupo_id, oficio),
        )
        return cursor.fetchone() is not None

    def listar_activos_por_cp_con_n_aliados(
        self, cursor, codigo_postal: str
    ) -> List[Any]:
        cursor.execute(
            """SELECT g.id, g.nombre, g.codigo_postal, g.ciudad, g.provincia, g.estado, g.fecha_creacion,
                      (SELECT COUNT(*) FROM aliados a2
                       WHERE a2.grupo_id = g.id AND a2.estado = 'activo') AS n_aliados
               FROM grupos g
               WHERE g.codigo_postal = ? AND g.estado = 'activo'
               ORDER BY n_aliados ASC, g.id ASC""",
            (codigo_postal,),
        )
        return cursor.fetchall()

    def contar_activos_por_cp(self, cursor, codigo_postal: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM grupos
            WHERE codigo_postal = ? AND estado = 'activo'
              AND COALESCE(tipo, 'territorial') = 'territorial'
            """,
            (codigo_postal,),
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def insertar_grupo(
        self,
        cursor,
        nombre: str,
        codigo_postal: str,
        ciudad: Optional[str],
        provincia: Optional[str],
    ) -> Any:
        nombre_s = (nombre or "").strip()
        if not nombre_s:
            raise ValueError("Nombre de grupo requerido")
        if self.existe_nombre(cursor, nombre_s):
            raise ValueError(f"Ya existe un grupo con el nombre «{nombre_s}»")
        cursor.execute(
            """
            INSERT INTO grupos (nombre, codigo_postal, ciudad, provincia, estado, tipo, fecha_creacion)
            VALUES (?, ?, ?, ?, 'activo', 'territorial', CURRENT_TIMESTAMP)
            """,
            (nombre_s, codigo_postal, ciudad or None, provincia or None),
        )
        return cursor.lastrowid

    def select_grupo_por_id(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion FROM grupos WHERE id = ?",
            (grupo_id,),
        )
        return cursor.fetchone()

    def contar_aliados_activos(self, cursor, grupo_id: int) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM aliados WHERE grupo_id = ? AND estado = 'activo'",
            (grupo_id,),
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def update_estado_disuelto(self, cursor, grupo_id: int) -> None:
        cursor.execute(
            "UPDATE grupos SET estado = 'disuelto' WHERE id = ?",
            (grupo_id,),
        )

    def select_aliado_activo_del_grupo(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, codigo, oficio, codigo_postal FROM aliados WHERE grupo_id = ? AND estado = 'activo' LIMIT 1",
            (grupo_id,),
        )
        return cursor.fetchone()

    def update_aliado_grupo_id(self, cursor, nuevo_grupo_id: int, aliado_id: int) -> None:
        cursor.execute(
            "UPDATE aliados SET grupo_id = ? WHERE id = ?",
            (nuevo_grupo_id, aliado_id),
        )

    def select_ciudad_provincia(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT ciudad, provincia FROM grupos WHERE id = ?",
            (grupo_id,),
        )
        return cursor.fetchone()

    def listar_avisos(
        self, cursor, grupo_id: int, tipo: Optional[str] = None
    ) -> List[Any]:
        if tipo:
            cursor.execute(
                "SELECT id, grupo_id, tipo, texto, creado_en FROM avisos_grupo WHERE grupo_id = ? AND tipo = ? ORDER BY creado_en DESC",
                (grupo_id, tipo),
            )
        else:
            cursor.execute(
                "SELECT id, grupo_id, tipo, texto, creado_en FROM avisos_grupo WHERE grupo_id = ? ORDER BY creado_en DESC",
                (grupo_id,),
            )
        return cursor.fetchall()

    def existe_grupo_activo(self, cursor, grupo_id: int) -> bool:
        cursor.execute(
            "SELECT 1 FROM grupos WHERE id = ? AND estado = 'activo'",
            (grupo_id,),
        )
        return cursor.fetchone() is not None

    def insertar_oficio_cerrado(self, cursor, grupo_id: int, oficio_s: str) -> None:
        cursor.execute(
            "INSERT OR IGNORE INTO grupo_oficio_cerrado (grupo_id, oficio) VALUES (?, ?)",
            (grupo_id, oficio_s),
        )

    def delete_oficio_cerrado(self, cursor, grupo_id: int, oficio_s: str) -> None:
        cursor.execute(
            "DELETE FROM grupo_oficio_cerrado WHERE grupo_id = ? AND oficio = ?",
            (grupo_id, oficio_s),
        )

    def listar_oficios_cerrados(self, cursor, grupo_id: int) -> List[Any]:
        cursor.execute(
            "SELECT oficio FROM grupo_oficio_cerrado WHERE grupo_id = ? ORDER BY oficio",
            (grupo_id,),
        )
        return cursor.fetchall()

    def contar_total(self, cursor) -> int:
        cursor.execute("SELECT COUNT(*) FROM grupos")
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def contar_por_estado(self, cursor, estado: str) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM grupos WHERE estado = ?",
            (estado,),
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0
