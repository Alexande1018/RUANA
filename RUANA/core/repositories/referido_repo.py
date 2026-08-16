"""
Repositorio de Referidos (Campamento Base).

Acceso a datos de referidos, linaje invitado_por e invitaciones ligadas.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple


class ReferidoRepo:
    """Operaciones de persistencia del dominio referido."""

    # Estados excluidos del árbol genealógico visible
    ESTADOS_EXCLUIDOS_RED = (
        'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
    )

    def _estados_excluidos_sql(self) -> str:
        return ', '.join(f"'{e}'" for e in self.ESTADOS_EXCLUIDOS_RED)

    def referidos_tiene_origen(self, cursor) -> bool:
        try:
            cursor.execute("PRAGMA table_info(referidos)")
            return "origen" in [row[1] for row in cursor.fetchall()]
        except Exception:
            return False

    def aliados_tiene_invitado_por(self, cursor) -> bool:
        try:
            cursor.execute("PRAGMA table_info(aliados)")
            return "invitado_por_codigo" in [row[1] for row in cursor.fetchall()]
        except Exception:
            return False

    def update_invitado_por_overwrite(
        self, cursor, codigo_invitador: str, origen: str, codigo_referido: str
    ) -> int:
        cursor.execute(
            """
            UPDATE aliados
            SET invitado_por_codigo = ?,
                invitado_origen = COALESCE(NULLIF(?, ''), invitado_origen),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
            """,
            (codigo_invitador, origen, codigo_referido),
        )
        return cursor.rowcount

    def update_invitado_por_si_vacio(
        self, cursor, codigo_invitador: str, origen: str, codigo_referido: str
    ) -> int:
        cursor.execute(
            """
            UPDATE aliados
            SET invitado_por_codigo = ?,
                invitado_origen = CASE
                    WHEN COALESCE(invitado_origen, '') = '' THEN ?
                    ELSE invitado_origen
                END,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
              AND (invitado_por_codigo IS NULL OR TRIM(COALESCE(invitado_por_codigo, '')) = '')
            """,
            (codigo_invitador, origen, codigo_referido),
        )
        return cursor.rowcount

    def insert_referido_con_origen(
        self, cursor, codigo_referido: str, codigo_invitador: str, origen: str
    ) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador, origen)
            VALUES (?, ?, ?)
            """,
            (codigo_referido, codigo_invitador, origen),
        )

    def update_origen_si_vacio(
        self, cursor, origen: str, codigo_referido: str
    ) -> None:
        cursor.execute(
            """
            UPDATE referidos
            SET origen = ?
            WHERE codigo_referido = ?
              AND (origen IS NULL OR origen = '')
            """,
            (origen, codigo_referido),
        )

    def insert_referido_sin_origen(
        self, cursor, codigo_referido: str, codigo_invitador: str
    ) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador)
            VALUES (?, ?)
            """,
            (codigo_referido, codigo_invitador),
        )

    def listar_pendientes_backfill_desde_referidos_con_origen(
        self, cursor
    ) -> List[Any]:
        cursor.execute(
            """
            SELECT r.codigo_referido, r.codigo_invitador,
                   COALESCE(r.origen, '') AS origen
            FROM referidos r
            JOIN aliados a ON a.codigo = r.codigo_referido
            WHERE a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = ''
            """
        )
        return cursor.fetchall()

    def listar_pendientes_backfill_desde_referidos_sin_origen(
        self, cursor
    ) -> List[Any]:
        cursor.execute(
            """
            SELECT r.codigo_referido, r.codigo_invitador, '' AS origen
            FROM referidos r
            JOIN aliados a ON a.codigo = r.codigo_referido
            WHERE a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = ''
            """
        )
        return cursor.fetchall()

    def listar_pendientes_backfill_desde_invitaciones(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT i.codigo AS codigo_referido, inv.codigo AS codigo_invitador,
                   inv.estado AS invitador_estado
            FROM invitaciones i
            JOIN aliados inv ON inv.id = i.invitador_aliado_id
            JOIN aliados ref ON ref.codigo = i.codigo
            WHERE COALESCE(ref.estado, '') NOT IN ('pendiente_completar', 'sistema')
              AND (ref.invitado_por_codigo IS NULL OR TRIM(COALESCE(ref.invitado_por_codigo, '')) = '')
            """
        )
        return cursor.fetchall()

    def listar_huerfanos_sin_invitado_por(
        self, cursor, admin_codigo: str
    ) -> List[Any]:
        cursor.execute(
            """
            SELECT a.codigo
            FROM aliados a
            WHERE COALESCE(a.estado, '') NOT IN (
                'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
            )
              AND a.codigo != ?
              AND (a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = '')
            """,
            (admin_codigo,),
        )
        return cursor.fetchall()

    def listar_hijos_directos_linaje(self, cursor, codigo_invitador: str) -> List[Any]:
        cursor.execute(
            """
            SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                   a.estado, a.score, a.telefono, a.email,
                   a.creado_en, a.invitado_origen AS origen,
                   (
                       SELECT COUNT(*) FROM aliados h
                       WHERE h.invitado_por_codigo = a.codigo
                         AND COALESCE(h.estado, '') NOT IN (
                             'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                         )
                   ) AS referidos_count
            FROM aliados a
            WHERE a.invitado_por_codigo = ?
              AND COALESCE(a.estado, '') NOT IN (
                  'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
              )
            ORDER BY a.creado_en ASC
            """,
            (codigo_invitador,),
        )
        return cursor.fetchall()

    def select_invitado_origen_aliado(self, cursor, codigo_referido: str) -> Optional[Any]:
        cursor.execute(
            "SELECT COALESCE(invitado_origen, '') AS origen FROM aliados WHERE codigo = ?",
            (codigo_referido,),
        )
        return cursor.fetchone()

    def select_origen_referidos(self, cursor, codigo_referido: str) -> Optional[Any]:
        cursor.execute(
            "SELECT origen FROM referidos WHERE codigo_referido = ?",
            (codigo_referido,),
        )
        return cursor.fetchone()

    def existe_uso_campana(self, cursor, codigo_referido: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM invitacion_campana_usos WHERE codigo_aliado = ? LIMIT 1",
            (codigo_referido,),
        )
        return cursor.fetchone() is not None

    def existe_invitacion_oficio_usada(self, cursor, codigo_referido: str) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM invitaciones_oficio
            WHERE codigo_referido = ? AND estado = 'usado'
            LIMIT 1
            """,
            (codigo_referido,),
        )
        return cursor.fetchone() is not None

    def select_invitador_estado_por_referido(
        self, cursor, codigo_referido: str
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT inv.estado AS invitador_estado
            FROM referidos r
            JOIN aliados inv ON inv.codigo = r.codigo_invitador
            WHERE r.codigo_referido = ?
            """,
            (codigo_referido,),
        )
        return cursor.fetchone()

    def contar_referidos_union_linaje(self, cursor, codigo_aliado: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT a.codigo AS codigo
                FROM aliados a
                WHERE a.invitado_por_codigo = ?
                  AND COALESCE(a.estado, '') NOT IN (
                      'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                  )
                UNION
                SELECT r.codigo_referido AS codigo
                FROM referidos r
                JOIN aliados a ON a.codigo = r.codigo_referido
                WHERE r.codigo_invitador = ?
                  AND COALESCE(a.estado, '') NOT IN (
                      'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                  )
            )
            """,
            (codigo_aliado, codigo_aliado),
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def contar_referidos_tabla(self, cursor, codigo_aliado: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM referidos r
            JOIN aliados a ON a.codigo = r.codigo_referido
            WHERE r.codigo_invitador = ?
              AND COALESCE(a.estado, '') NOT IN (
                  'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
              )
            """,
            (codigo_aliado,),
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def select_invitacion_con_invitador(
        self, cursor, codigo_invitacion: str
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT i.invitador_aliado_id, inv.codigo AS codigo_invitador, inv.estado AS invitador_estado
            FROM invitaciones i
            JOIN aliados inv ON inv.id = i.invitador_aliado_id
            WHERE i.codigo = ?
            """,
            (codigo_invitacion,),
        )
        return cursor.fetchone()

    def marcar_invitacion_usada(self, cursor, codigo_invitacion: str) -> None:
        cursor.execute(
            "UPDATE invitaciones SET usado = 1 WHERE codigo = ?",
            (codigo_invitacion,),
        )

    def buscar_codigos_en_red(self, cursor, like: str, limite: int) -> List[Any]:
        excl = self._estados_excluidos_sql()
        cursor.execute(
            f"""
            SELECT DISTINCT a.codigo
            FROM aliados a
            WHERE COALESCE(a.estado, '') NOT IN ({excl})
              AND (
                  a.codigo LIKE ? OR a.nombre LIKE ? OR a.oficio LIKE ?
                  OR a.marca LIKE ? OR a.codigo_postal LIKE ?
              )
            ORDER BY a.nombre
            LIMIT ?
            """,
            (like, like, like, like, like, limite),
        )
        return cursor.fetchall()

    def listar_raices(self, cursor) -> List[Any]:
        """Raíces del bosque: prefiere linaje (invitado_por) con fallback a referidos."""
        if self.aliados_tiene_invitado_por(cursor):
            rows = self.listar_raices_linaje(cursor)
            if rows:
                return rows
        cursor.execute(
            """
            SELECT DISTINCT r.codigo_invitador
            FROM referidos r
            WHERE r.codigo_invitador NOT IN (SELECT codigo_referido FROM referidos)
            ORDER BY r.codigo_invitador
            """
        )
        return cursor.fetchall()

    def listar_invitaciones_usadas_sin_referido(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT i.codigo AS codigo_referido,
                   inv.codigo AS codigo_invitador,
                   inv.estado AS invitador_estado
            FROM invitaciones i
            JOIN aliados inv ON inv.id = i.invitador_aliado_id
            JOIN aliados ref ON ref.codigo = i.codigo
            WHERE i.invitador_aliado_id IS NOT NULL
              AND COALESCE(ref.estado, '') NOT IN ('pendiente_completar', 'sistema')
              AND NOT EXISTS (
                  SELECT 1 FROM referidos r WHERE r.codigo_referido = i.codigo
              )
            """
        )
        return cursor.fetchall()

    def listar_invitaciones_oficio_usadas_sin_referido(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT io.codigo_referido, inv.codigo AS codigo_invitador
            FROM invitaciones_oficio io
            JOIN aliados inv ON inv.id = io.aliado_id
            WHERE io.estado = 'usado'
              AND COALESCE(io.codigo_referido, '') != ''
              AND EXISTS (
                  SELECT 1 FROM aliados a WHERE a.codigo = io.codigo_referido
              )
              AND NOT EXISTS (
                  SELECT 1 FROM referidos r WHERE r.codigo_referido = io.codigo_referido
              )
            """
        )
        return cursor.fetchall()

    def contar_nodos_red(self, cursor) -> int:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT codigo) FROM (
                SELECT codigo_referido AS codigo FROM referidos
                UNION
                SELECT codigo_invitador AS codigo FROM referidos
            )
            """
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def contar_aliados_activos_red(self, cursor) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM aliados
            WHERE COALESCE(estado, '') NOT IN (
                'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
            )
            """
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def contar_aliados_fuera_red(self, cursor) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM aliados a
            WHERE COALESCE(a.estado, '') = 'pendiente_completar'
               OR (
                   COALESCE(a.estado, '') NOT IN ('sistema', 'rechazado', 'expulsado')
                   AND NOT EXISTS (
                       SELECT 1 FROM referidos r
                       WHERE r.codigo_referido = a.codigo
                          OR r.codigo_invitador = a.codigo
                   )
               )
            """
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def listar_referidos_desde(self, cursor, desde: str) -> List[Any]:
        if desde:
            cursor.execute(
                """
                SELECT r.codigo_referido, r.codigo_invitador, r.creado_en
                FROM referidos r
                WHERE datetime(r.creado_en) > datetime(?)
                ORDER BY r.creado_en ASC
                """,
                (desde,),
            )
        else:
            cursor.execute(
                """
                SELECT r.codigo_referido, r.codigo_invitador, r.creado_en
                FROM referidos r
                ORDER BY r.creado_en ASC
                """
            )
        return cursor.fetchall()

    def listar_referidos_directos(self, cursor, codigo_invitador: str) -> List[Any]:
        """Hijos directos unificando invitado_por_codigo (linaje) y tabla referidos."""
        excl = self._estados_excluidos_sql()
        cursor.execute(
            f"""
            SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                   a.estado, a.score, a.telefono, a.email,
                   a.creado_en, a.creado_en AS referido_en,
                   COALESCE(a.invitado_origen, '') AS origen
            FROM aliados a
            WHERE a.invitado_por_codigo = ?
              AND COALESCE(a.estado, '') NOT IN ({excl})
            UNION
            SELECT COALESCE(a.codigo, r.codigo_referido) AS codigo,
                   COALESCE(a.nombre, r.codigo_referido) AS nombre,
                   COALESCE(a.oficio, '—') AS oficio,
                   COALESCE(a.codigo_postal, '') AS codigo_postal,
                   COALESCE(a.marca, '') AS marca,
                   COALESCE(a.estado, 'desconocido') AS estado,
                   COALESCE(a.score, 0) AS score,
                   COALESCE(a.telefono, '') AS telefono,
                   COALESCE(a.email, '') AS email,
                   COALESCE(a.creado_en, r.creado_en) AS creado_en,
                   r.creado_en AS referido_en,
                   COALESCE(r.origen, '') AS origen
            FROM referidos r
            LEFT JOIN aliados a ON a.codigo = r.codigo_referido
            WHERE r.codigo_invitador = ?
              AND NOT EXISTS (
                  SELECT 1 FROM aliados ax
                  WHERE ax.codigo = r.codigo_referido
                    AND COALESCE(ax.invitado_por_codigo, '') = ?
              )
              AND (
                  a.codigo IS NULL
                  OR COALESCE(a.estado, '') NOT IN ({excl})
              )
            ORDER BY creado_en ASC
            """,
            (codigo_invitador, codigo_invitador, codigo_invitador),
        )
        return cursor.fetchall()

    def listar_raices_linaje(self, cursor) -> List[Any]:
        """Raíces según invitado_por_codigo: sin padre válido y con descendencia o sistema."""
        excl = self._estados_excluidos_sql()
        cursor.execute(
            f"""
            SELECT DISTINCT a.codigo
            FROM aliados a
            WHERE COALESCE(a.estado, '') NOT IN ('rechazado', 'expulsado', 'pendiente_completar')
              AND (
                  COALESCE(a.invitado_por_codigo, '') = ''
                  OR NOT EXISTS (
                      SELECT 1 FROM aliados p
                      WHERE p.codigo = a.invitado_por_codigo
                        AND COALESCE(p.estado, '') NOT IN ('rechazado', 'expulsado', 'pendiente_completar')
                  )
              )
              AND (
                  COALESCE(a.estado, '') = 'sistema'
                  OR EXISTS (
                      SELECT 1 FROM aliados h
                      WHERE h.invitado_por_codigo = a.codigo
                        AND COALESCE(h.estado, '') NOT IN ({excl})
                  )
                  OR EXISTS (
                      SELECT 1 FROM referidos r WHERE r.codigo_invitador = a.codigo
                  )
              )
            ORDER BY a.codigo
            """
        )
        return cursor.fetchall()

    def listar_pendientes_sync_desde_linaje(self, cursor) -> List[Any]:
        """Aliados con invitado_por_codigo pero sin fila en referidos."""
        cursor.execute(
            """
            SELECT a.codigo AS codigo_referido,
                   a.invitado_por_codigo AS codigo_invitador,
                   COALESCE(a.invitado_origen, '') AS origen
            FROM aliados a
            WHERE COALESCE(a.invitado_por_codigo, '') != ''
              AND COALESCE(a.estado, '') NOT IN (
                  'rechazado', 'expulsado', 'pendiente_completar'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM referidos r WHERE r.codigo_referido = a.codigo
              )
            """
        )
        return cursor.fetchall()

    def select_invitador_por_linaje(self, cursor, codigo_referido: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                   a.estado, a.score, a.creado_en AS referido_en
            FROM aliados ref
            JOIN aliados a ON a.codigo = ref.invitado_por_codigo
            WHERE ref.codigo = ?
              AND COALESCE(ref.invitado_por_codigo, '') != ''
            """,
            (codigo_referido,),
        )
        return cursor.fetchone()
