"""
Repositorio de Invitaciones (Campamento Base).

Acceso a datos de invitaciones, campañas e invitaciones_oficio.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional


class InvitacionRepo:
    """Operaciones de persistencia del dominio invitación."""

    def upsert_invitacion_postgres(
        self, cursor, codigo: str, invitador_aliado_id: int, sid: Optional[int]
    ) -> None:
        cursor.execute(
            """
            INSERT INTO invitaciones (codigo, invitador_aliado_id, usado, solicitud_id)
            VALUES (?, ?, 0, ?)
            ON CONFLICT (codigo) DO UPDATE SET
                invitador_aliado_id = EXCLUDED.invitador_aliado_id,
                usado = 0,
                solicitud_id = COALESCE(EXCLUDED.solicitud_id, invitaciones.solicitud_id)
            """,
            (codigo, int(invitador_aliado_id), sid),
        )

    def upsert_invitacion_sqlite(
        self, cursor, codigo: str, invitador_aliado_id: int, sid: Optional[int]
    ) -> None:
        cursor.execute(
            """
            INSERT OR REPLACE INTO invitaciones (codigo, invitador_aliado_id, usado, solicitud_id)
            VALUES (?, ?, 0, ?)
            """,
            (codigo, int(invitador_aliado_id), sid),
        )

    def existe_campana(self, cursor, codigo: str) -> bool:
        cursor.execute(
            "SELECT codigo FROM invitacion_campanas WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone() is not None

    def insertar_campana(
        self,
        cursor,
        codigo: str,
        nombre: str,
        codigo_postal: str,
        max_usos: int,
        creado_por: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO invitacion_campanas
            (codigo, nombre, codigo_postal, max_usos, usos_actuales, activo, creado_por_admin_codigo)
            VALUES (?, ?, ?, ?, 0, 1, ?)
            """,
            (codigo, nombre, codigo_postal, max_usos, creado_por),
        )

    def select_campana(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            "SELECT * FROM invitacion_campanas WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone()

    def listar_campanas(self, cursor, limite: int) -> List[Any]:
        cursor.execute(
            """
            SELECT codigo, nombre, codigo_postal, max_usos, usos_actuales, activo,
                   creado_por_admin_codigo, creado_en, desactivado_en
            FROM invitacion_campanas
            ORDER BY creado_en DESC
            LIMIT ?
            """,
            (limite,),
        )
        return cursor.fetchall()

    def incrementar_uso_campana(self, cursor, codigo: str) -> int:
        cursor.execute(
            """
            UPDATE invitacion_campanas
            SET usos_actuales = usos_actuales + 1
            WHERE codigo = ?
              AND activo = 1
              AND usos_actuales < max_usos
            """,
            (codigo,),
        )
        return cursor.rowcount

    def insertar_uso_campana(
        self, cursor, codigo: str, nuevo_aliado_codigo: str
    ) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO invitacion_campana_usos (codigo_campana, codigo_aliado)
            VALUES (?, ?)
            """,
            (codigo, nuevo_aliado_codigo),
        )

    def desactivar_campana(self, cursor, codigo: str) -> int:
        cursor.execute(
            """
            UPDATE invitacion_campanas
            SET activo = 0, desactivado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
            """,
            (codigo,),
        )
        return cursor.rowcount

    def columnas_invitaciones(self, cursor) -> List[str]:
        cursor.execute("PRAGMA table_info(invitaciones)")
        return [r[1] for r in cursor.fetchall()]

    def listar_invitaciones_recientes(self, cursor, limite: int) -> List[Any]:
        cursor.execute(
            """
            SELECT i.codigo, i.invitador_aliado_id, i.creado_en, i.usado,
                   a.codigo AS invitador_codigo, a.nombre AS invitador_nombre
            FROM invitaciones i
            LEFT JOIN aliados a ON a.id = i.invitador_aliado_id
            ORDER BY i.creado_en DESC
            LIMIT ?
            """,
            (limite,),
        )
        return cursor.fetchall()

    def select_invitacion_con_invitador(
        self, cursor, codigo_invitacion: str
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT i.usado, i.invitador_aliado_id, inv.codigo AS codigo_invitador,
                   inv.estado AS invitador_estado
            FROM invitaciones i
            JOIN aliados inv ON inv.id = i.invitador_aliado_id
            WHERE i.codigo = ?
            """,
            (codigo_invitacion,),
        )
        return cursor.fetchone()

    def select_invitado_por_codigo(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            "SELECT invitado_por_codigo FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone()

    def existe_referido(self, cursor, codigo_referido: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM referidos WHERE codigo_referido = ?",
            (codigo_referido,),
        )
        return cursor.fetchone() is not None

    def marcar_invitacion_usada(self, cursor, codigo_invitacion: str) -> None:
        cursor.execute(
            "UPDATE invitaciones SET usado = 1 WHERE codigo = ?",
            (codigo_invitacion,),
        )

    def select_invitacion_oficio_pendiente(
        self, cursor, grupo_id: int, oficio: str
    ) -> Optional[Any]:
        cursor.execute(
            "SELECT codigo FROM invitaciones_oficio WHERE grupo_id = ? AND oficio = ? AND estado = 'pendiente' LIMIT 1",
            (grupo_id, oficio),
        )
        return cursor.fetchone()

    def insertar_invitacion_oficio(
        self, cursor, codigo: str, grupo_id: int, oficio: str, aliado_id: int
    ) -> None:
        cursor.execute(
            "INSERT INTO invitaciones_oficio (codigo, grupo_id, oficio, aliado_id, estado) VALUES (?, ?, ?, ?, 'pendiente')",
            (codigo, grupo_id, oficio, aliado_id),
        )

    def select_invitacion_oficio(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            "SELECT id, codigo, grupo_id, oficio, aliado_id, estado FROM invitaciones_oficio WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone()

    def select_invitacion_oficio_consumo(
        self, cursor, codigo: str
    ) -> Optional[Any]:
        cursor.execute(
            "SELECT id, aliado_id, estado FROM invitaciones_oficio WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone()

    def select_codigo_aliado_por_id(self, cursor, aliado_id: int) -> Optional[Any]:
        cursor.execute("SELECT codigo FROM aliados WHERE id = ?", (aliado_id,))
        return cursor.fetchone()

    def marcar_invitacion_oficio_usada(
        self, cursor, nuevo_aliado_codigo: str, invitacion_id: int
    ) -> None:
        cursor.execute(
            "UPDATE invitaciones_oficio SET estado = 'usado', codigo_referido = ? WHERE id = ?",
            (nuevo_aliado_codigo, invitacion_id),
        )

    def update_codigo_referido_oficio_si_vacio(
        self, cursor, nuevo_aliado_codigo: str, invitacion_id: int
    ) -> None:
        cursor.execute(
            "UPDATE invitaciones_oficio SET codigo_referido = ? WHERE id = ? AND COALESCE(codigo_referido, '') = ''",
            (nuevo_aliado_codigo, invitacion_id),
        )

    def existe_codigo_invitacion(self, cursor, codigo: str) -> bool:
        cursor.execute("SELECT 1 FROM invitaciones WHERE codigo = ?", (codigo,))
        return cursor.fetchone() is not None

    def select_invitacion_pendiente(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT i.codigo, i.invitador_aliado_id, i.usado, i.creado_en,
                   i.solicitud_id,
                   inv.codigo AS codigo_invitador,
                   inv.codigo_postal AS zona_invitador,
                   inv.id AS invitador_id
            FROM invitaciones i
            JOIN aliados inv ON inv.id = i.invitador_aliado_id
            WHERE i.codigo = ? AND COALESCE(i.usado, 0) = 0
            """,
            (codigo,),
        )
        return cursor.fetchone()

    def eliminar_aliado_placeholder(self, cursor, codigo: str) -> int:
        cursor.execute(
            """
            DELETE FROM aliados
            WHERE codigo = ?
              AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
            """,
            (codigo,),
        )
        return cursor.rowcount
