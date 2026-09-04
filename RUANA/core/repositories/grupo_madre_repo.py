"""Repositorio SQL para Grupo Madre, cp_estado e independización."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from core.db_constants import (
    CP_POSTAL_SENTINEL_MADRE,
    ESTADOS_ENCARGO_VALIDO_MADUREZ,
    TIPO_GRUPO_MADRE,
    TIPO_GRUPO_TERRITORIAL,
)


class GrupoMadreRepo:
    def contar_territoriales_activos_por_cp(self, cursor, codigo_postal: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM grupos
            WHERE codigo_postal = ? AND estado = 'activo'
              AND COALESCE(tipo, 'territorial') = ?
            """,
            (codigo_postal.strip(), TIPO_GRUPO_TERRITORIAL),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def select_grupo_madre_por_ciudad(self, cursor, ciudad: str) -> Optional[Any]:
        ciudad_s = (ciudad or "").strip()
        if not ciudad_s:
            return None
        cursor.execute(
            """
            SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion, tipo
            FROM grupos
            WHERE LOWER(TRIM(ciudad)) = LOWER(?)
              AND tipo = ?
              AND estado = 'activo'
            ORDER BY id LIMIT 1
            """,
            (ciudad_s, TIPO_GRUPO_MADRE),
        )
        return cursor.fetchone()

    def insertar_grupo_madre(
        self,
        cursor,
        nombre: str,
        ciudad: str,
        provincia: Optional[str],
    ) -> int:
        cursor.execute(
            """
            INSERT INTO grupos (nombre, codigo_postal, ciudad, provincia, estado, tipo, fecha_creacion)
            VALUES (?, ?, ?, ?, 'activo', ?, CURRENT_TIMESTAMP)
            """,
            (nombre, CP_POSTAL_SENTINEL_MADRE, ciudad, provincia or None, TIPO_GRUPO_MADRE),
        )
        return int(cursor.lastrowid)

    def select_grupo_row(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion,
                   COALESCE(tipo, 'territorial') AS tipo, grupo_madre_id
            FROM grupos WHERE id = ?
            """,
            (grupo_id,),
        )
        return cursor.fetchone()

    def tiene_oficio_en_madre_por_cp(
        self, cursor, grupo_madre_id: int, oficio: str, codigo_postal: str
    ) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM aliados
            WHERE grupo_id = ? AND oficio = ? AND estado = 'activo'
              AND TRIM(codigo_postal) = ?
            LIMIT 1
            """,
            (grupo_madre_id, oficio.strip(), codigo_postal.strip()),
        )
        return cursor.fetchone() is not None

    def contar_oficio_en_madre(self, cursor, grupo_madre_id: int, oficio: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT TRIM(codigo_postal)) FROM aliados
            WHERE grupo_id = ? AND oficio = ? AND estado = 'activo'
            """,
            (grupo_madre_id, oficio.strip()),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def listar_aliados_activos_madre_por_cp(
        self, cursor, grupo_madre_id: int, codigo_postal: str
    ) -> List[Any]:
        cursor.execute(
            """
            SELECT id, codigo, oficio, codigo_postal, grupo_id, estado
            FROM aliados
            WHERE grupo_id = ? AND estado = 'activo'
              AND TRIM(codigo_postal) = ?
            """,
            (grupo_madre_id, codigo_postal.strip()),
        )
        return cursor.fetchall()

    def contar_aliados_activos_cp(self, cursor, codigo_postal: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM aliados
            WHERE TRIM(codigo_postal) = ? AND estado = 'activo'
            """,
            (codigo_postal.strip(),),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_encargos_validos_cp_profesional(self, cursor, codigo_postal: str) -> int:
        placeholders = ",".join("?" for _ in ESTADOS_ENCARGO_VALIDO_MADUREZ)
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT c.id)
            FROM contactos_ruana c
            INNER JOIN aliados a ON a.codigo = c.profesional_codigo
            WHERE TRIM(a.codigo_postal) = ?
              AND a.estado = 'activo'
              AND c.estado IN ({placeholders})
            """,
            (codigo_postal.strip(), *ESTADOS_ENCARGO_VALIDO_MADUREZ),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def upsert_cp_estado(
        self,
        cursor,
        codigo_postal: str,
        ciudad: str,
        modo: str,
        grupo_madre_id: Optional[int],
        aliados_activos: int,
        encargos_validos: int,
        listo: bool,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO cp_estado (
                codigo_postal, ciudad, modo, grupo_madre_id,
                aliados_activos, encargos_validos, listo_independizar, actualizado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(codigo_postal) DO UPDATE SET
                ciudad = excluded.ciudad,
                modo = excluded.modo,
                grupo_madre_id = COALESCE(excluded.grupo_madre_id, cp_estado.grupo_madre_id),
                aliados_activos = excluded.aliados_activos,
                encargos_validos = excluded.encargos_validos,
                listo_independizar = excluded.listo_independizar,
                actualizado_en = CURRENT_TIMESTAMP
            """,
            (
                codigo_postal.strip(),
                ciudad,
                modo,
                grupo_madre_id,
                aliados_activos,
                encargos_validos,
                1 if listo else 0,
            ),
        )

    def select_cp_estado(self, cursor, codigo_postal: str) -> Optional[Any]:
        cursor.execute("SELECT * FROM cp_estado WHERE codigo_postal = ?", (codigo_postal.strip(),))
        return cursor.fetchone()

    def existe_solicitud_pendiente_cp(self, cursor, codigo_postal: str) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM cp_independencia_solicitudes
            WHERE codigo_postal = ? AND estado = 'pendiente' LIMIT 1
            """,
            (codigo_postal.strip(),),
        )
        return cursor.fetchone() is not None

    def insertar_solicitud_independencia(
        self,
        cursor,
        codigo_postal: str,
        ciudad: str,
        aliados: int,
        encargos: int,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO cp_independencia_solicitudes
                (codigo_postal, ciudad, aliados_activos, encargos_validos, estado)
            VALUES (?, ?, ?, ?, 'pendiente')
            """,
            (codigo_postal.strip(), ciudad, aliados, encargos),
        )
        return int(cursor.lastrowid)

    def listar_solicitudes_pendientes(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT id, codigo_postal, ciudad, aliados_activos, encargos_validos,
                   estado, notas_admin, creado_en
            FROM cp_independencia_solicitudes
            WHERE estado = 'pendiente'
            ORDER BY creado_en ASC
            """
        )
        return cursor.fetchall()

    def listar_cp_madurez(self, cursor, modo: Optional[str] = None) -> List[Any]:
        if modo:
            cursor.execute(
                "SELECT * FROM cp_estado WHERE modo = ? ORDER BY ciudad, codigo_postal",
                (modo,),
            )
        else:
            cursor.execute("SELECT * FROM cp_estado ORDER BY ciudad, codigo_postal")
        return cursor.fetchall()

    def listar_grupos_madre(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT g.id, g.nombre, g.ciudad, g.provincia, g.estado, g.fecha_creacion,
                   (SELECT COUNT(*) FROM aliados a WHERE a.grupo_id = g.id AND a.estado = 'activo') AS n_aliados
            FROM grupos g
            WHERE g.tipo = ? AND g.estado = 'activo'
            ORDER BY g.ciudad
            """,
            (TIPO_GRUPO_MADRE,),
        )
        return cursor.fetchall()

    def marcar_solicitud(
        self,
        cursor,
        solicitud_id: int,
        estado: str,
        resuelto_por: str,
        notas: Optional[str] = None,
    ) -> None:
        cursor.execute(
            """
            UPDATE cp_independencia_solicitudes
            SET estado = ?, resuelto_en = CURRENT_TIMESTAMP, resuelto_por = ?,
                notas_admin = COALESCE(?, notas_admin)
            WHERE id = ?
            """,
            (estado, resuelto_por, notas, solicitud_id),
        )

    def marcar_cp_territorial(self, cursor, codigo_postal: str) -> None:
        cursor.execute(
            """
            UPDATE cp_estado
            SET modo = 'territorial', listo_independizar = 0,
                independizado_en = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo_postal = ?
            """,
            (codigo_postal.strip(),),
        )

    def aviso_visto(self, cursor, aliado_codigo: str, aviso_tipo: str) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO aliado_avisos_vistos (aliado_codigo, aviso_tipo)
            VALUES (?, ?)
            """,
            (aliado_codigo.strip(), aviso_tipo),
        )

    def tiene_aviso_visto(self, cursor, aliado_codigo: str, aviso_tipo: str) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM aliado_avisos_vistos
            WHERE aliado_codigo = ? AND aviso_tipo = ?
            """,
            (aliado_codigo.strip(), aviso_tipo),
        )
        return cursor.fetchone() is not None

    def listar_directorio_madre(
        self, cursor, grupo_madre_id: int, codigo_excluir: str, estados_ok: Tuple[str, ...],
        foto_col: str = "foto_perfil_url",
    ) -> List[Any]:
        placeholders = ",".join("?" for _ in estados_ok)
        cursor.execute(
            f"""
            SELECT a.id, a.codigo, a.nombre, a.marca, a.oficio, a.codigo_postal, a.grupo_id,
                   a.estado, a.score, a.descripcion_servicio, a.{foto_col}, a.creado_en
            FROM aliados a
            WHERE a.grupo_id = ? AND a.estado IN ({placeholders})
              AND TRIM(a.codigo) != ?
            ORDER BY a.codigo_postal, a.nombre
            """,
            (grupo_madre_id, *estados_ok, codigo_excluir.strip()),
        )
        return cursor.fetchall()
