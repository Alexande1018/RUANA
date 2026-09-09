"""Persistencia territorial: contadores de CP, migración desde Grupo Madre e informe."""

from __future__ import annotations

from typing import Any, List, Optional

from core.db_constants import CP_POSTAL_SENTINEL_MADRE, TIPO_GRUPO_MADRE, TIPO_GRUPO_TERRITORIAL


class TerritorioRepo:
    def listar_aliados_en_grupo_madre(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT a.id AS aliado_id, a.codigo, a.oficio, a.estado,
                   TRIM(COALESCE(a.codigo_postal, '')) AS codigo_postal,
                   a.grupo_id,
                   COALESCE(g.tipo, 'territorial') AS grupo_tipo,
                   TRIM(COALESCE(g.codigo_postal, '')) AS grupo_cp,
                   TRIM(COALESCE(g.ciudad, '')) AS grupo_ciudad,
                   TRIM(COALESCE(g.provincia, '')) AS grupo_provincia
            FROM aliados a
            INNER JOIN grupos g ON g.id = a.grupo_id
            WHERE COALESCE(g.tipo, 'territorial') = ?
               OR TRIM(COALESCE(g.codigo_postal, '')) = ?
            ORDER BY a.id
            """,
            (TIPO_GRUPO_MADRE, CP_POSTAL_SENTINEL_MADRE),
        )
        return cursor.fetchall() or []

    def listar_grupos_madre(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT id, nombre, codigo_postal, ciudad, provincia, estado
            FROM grupos
            WHERE COALESCE(tipo, 'territorial') = ?
               OR TRIM(COALESCE(codigo_postal, '')) = ?
            ORDER BY id
            """,
            (TIPO_GRUPO_MADRE, CP_POSTAL_SENTINEL_MADRE),
        )
        return cursor.fetchall() or []

    def contar_aliados_grupo(self, cursor, grupo_id: int) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM aliados WHERE grupo_id = ?",
            (int(grupo_id),),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def listar_sin_grupo_territorial_valido(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT a.id, a.codigo, a.nombre, a.oficio, a.estado,
                   TRIM(COALESCE(a.codigo_postal, '')) AS codigo_postal,
                   a.grupo_id,
                   COALESCE(g.tipo, 'territorial') AS grupo_tipo,
                   g.estado AS grupo_estado,
                   TRIM(COALESCE(g.codigo_postal, '')) AS grupo_cp
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            WHERE a.estado IN ('activo', 'pendiente_validacion')
              AND (
                    a.grupo_id IS NULL
                    OR g.id IS NULL
                    OR COALESCE(g.estado, '') = 'disuelto'
                    OR COALESCE(g.tipo, 'territorial') = ?
                    OR TRIM(COALESCE(g.codigo_postal, '')) = ?
                    OR TRIM(COALESCE(g.codigo_postal, '')) = ''
                  )
            ORDER BY a.codigo
            """,
            (TIPO_GRUPO_MADRE, CP_POSTAL_SENTINEL_MADRE),
        )
        return cursor.fetchall() or []

    def listar_estado_territorial_aliados(self, cursor, limite: int = 500) -> List[Any]:
        cursor.execute(
            """
            SELECT a.codigo, a.nombre, a.oficio, a.estado,
                   TRIM(COALESCE(a.codigo_postal, '')) AS codigo_postal,
                   a.grupo_id, g.nombre AS grupo_nombre,
                   COALESCE(g.tipo, 'territorial') AS grupo_tipo,
                   g.estado AS grupo_estado,
                   TRIM(COALESCE(g.codigo_postal, '')) AS grupo_cp
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            ORDER BY a.codigo_postal, a.grupo_id, a.codigo
            LIMIT ?
            """,
            (int(limite),),
        )
        return cursor.fetchall() or []

    def insertar_backup(
        self,
        cursor,
        aliado_id: int,
        codigo: str,
        grupo_id_anterior: Optional[int],
        grupo_tipo_anterior: str,
        codigo_postal: str,
        oficio: str,
        estado_anterior: str,
        grupo_id_nuevo: Optional[int],
        caso: str,
        detalle: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO migracion_territorio_backup (
                aliado_id, codigo, grupo_id_anterior, grupo_tipo_anterior,
                codigo_postal, oficio, estado_anterior, grupo_id_nuevo, caso, detalle
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aliado_id,
                codigo,
                grupo_id_anterior,
                grupo_tipo_anterior,
                codigo_postal,
                oficio,
                estado_anterior,
                grupo_id_nuevo,
                caso,
                detalle,
            ),
        )

    def insertar_informe(
        self,
        cursor,
        aliado_id: Optional[int],
        codigo: str,
        caso: str,
        detalle: str,
        codigo_postal: str,
        oficio: str,
        grupo_id_anterior: Optional[int],
        grupo_id_nuevo: Optional[int],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO migracion_territorio_informe (
                aliado_id, codigo, caso, detalle, codigo_postal, oficio,
                grupo_id_anterior, grupo_id_nuevo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aliado_id,
                codigo,
                caso,
                detalle,
                codigo_postal,
                oficio,
                grupo_id_anterior,
                grupo_id_nuevo,
            ),
        )

    def listar_informe(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT aliado_id, codigo, caso, detalle, codigo_postal, oficio,
                   grupo_id_anterior, grupo_id_nuevo, creado_en
            FROM migracion_territorio_informe
            ORDER BY id
            """
        )
        return cursor.fetchall() or []

    def listar_backup_migrados(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT aliado_id, grupo_id_anterior, grupo_id_nuevo, caso
            FROM migracion_territorio_backup
            WHERE caso = 'migrado'
            ORDER BY id DESC
            """
        )
        return cursor.fetchall() or []

    def obtener_contador_desde_ultimo_grupo(self, cursor, codigo_postal: str) -> int:
        cursor.execute(
            "SELECT aliados_desde_ultimo_grupo FROM cp_estado WHERE codigo_postal = ?",
            (codigo_postal.strip(),),
        )
        row = cursor.fetchone()
        if not row:
            return 0
        val = row[0] if not hasattr(row, "keys") else row["aliados_desde_ultimo_grupo"]
        return int(val or 0)

    def incrementar_contador_desde_ultimo_grupo(
        self, cursor, codigo_postal: str, ciudad: str, incremento: int = 1
    ) -> int:
        cp = codigo_postal.strip()
        actual = self.obtener_contador_desde_ultimo_grupo(cursor, cp)
        nuevo = actual + incremento
        cursor.execute(
            """
            INSERT INTO cp_estado (codigo_postal, ciudad, modo, aliados_desde_ultimo_grupo, actualizado_en)
            VALUES (?, ?, 'territorial', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(codigo_postal) DO UPDATE SET
                aliados_desde_ultimo_grupo = excluded.aliados_desde_ultimo_grupo,
                modo = 'territorial',
                actualizado_en = CURRENT_TIMESTAMP
            """,
            (cp, ciudad, nuevo),
        )
        return nuevo

    def resetear_contador_desde_ultimo_grupo(self, cursor, codigo_postal: str) -> None:
        cursor.execute(
            """
            UPDATE cp_estado
            SET aliados_desde_ultimo_grupo = 0, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo_postal = ?
            """,
            (codigo_postal.strip(),),
        )

    def marcar_cp_territorial(self, cursor, codigo_postal: str, ciudad: str) -> None:
        cursor.execute(
            """
            INSERT INTO cp_estado (codigo_postal, ciudad, modo, actualizado_en)
            VALUES (?, ?, 'territorial', CURRENT_TIMESTAMP)
            ON CONFLICT(codigo_postal) DO UPDATE SET
                ciudad = excluded.ciudad,
                modo = 'territorial',
                actualizado_en = CURRENT_TIMESTAMP
            """,
            (codigo_postal.strip(), ciudad or codigo_postal.strip()),
        )

    def listar_profesionales_oficio_fuera_grupo(
        self, cursor, oficio: str, excluir_grupo_id: int, excluir_codigo: str
    ) -> List[Any]:
        cursor.execute(
            """
            SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.grupo_id, a.estado,
                   TRIM(COALESCE(g.codigo_postal, a.codigo_postal, '')) AS grupo_cp,
                   COALESCE(g.tipo, 'territorial') AS grupo_tipo
            FROM aliados a
            INNER JOIN grupos g ON g.id = a.grupo_id
            WHERE LOWER(TRIM(COALESCE(a.estado, ''))) IN ('activo', 'pendiente_validacion')
              AND a.grupo_id != ?
              AND TRIM(a.codigo) != ?
              AND COALESCE(g.tipo, 'territorial') = ?
              AND TRIM(COALESCE(g.codigo_postal, '')) != ?
              AND COALESCE(g.estado, 'activo') IN ('activo', 'en_competencia')
            """,
            (
                int(excluir_grupo_id),
                excluir_codigo.strip(),
                TIPO_GRUPO_TERRITORIAL,
                CP_POSTAL_SENTINEL_MADRE,
            ),
        )
        return cursor.fetchall() or []
