"""
Repositorio de Aliados (Campamento Base).

Acceso a datos de aliados, aliados_eliminados y aliado_accesos_dia.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.db_constants import ALIADO_FOTO_PERFIL_COLUMN, SQL_ESTADO_CONTACTO_OCUPADO


class AliadoRepo:
    """Operaciones de persistencia del dominio aliado."""

    # --- Lecturas simples ---

    def select_id_por_codigo(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
        return row[0] if row else None

    def select_id_estado_por_codigo(self, cursor, codigo: str) -> Optional[Tuple[Any, Any]]:
        cursor.execute("SELECT id, estado FROM aliados WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

    def existe_codigo(self, cursor, codigo: str) -> bool:
        cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (codigo,))
        return cursor.fetchone() is not None

    def existe_codigo_limit(self, cursor, codigo: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM aliados WHERE codigo = ? LIMIT 1",
            (codigo,),
        )
        return cursor.fetchone() is not None

    def select_id_por_email_ocupado(self, cursor, email: str) -> Optional[Any]:
        cursor.execute(
            f"SELECT id FROM aliados WHERE email = ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
            (email,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def select_id_por_telefono_ocupado(self, cursor, telefono: str) -> Optional[Any]:
        cursor.execute(
            f"SELECT id FROM aliados WHERE telefono = ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
            (telefono,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def select_id_por_email_ocupado_excluyendo(
        self, cursor, email: str, codigo: str
    ) -> Optional[Any]:
        cursor.execute(
            f"SELECT id FROM aliados WHERE email = ? AND codigo != ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
            (email, codigo),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def select_id_por_telefono_ocupado_excluyendo(
        self, cursor, telefono: str, codigo: str
    ) -> Optional[Any]:
        cursor.execute(
            f"SELECT id FROM aliados WHERE telefono = ? AND codigo != ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
            (telefono, codigo),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def select_fila_basica_por_id(self, cursor, aliado_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, descripcion_servicio, creado_en, actualizado_en FROM aliados WHERE id = ?",
            (aliado_id,),
        )
        return cursor.fetchone()

    def select_todo_por_codigo(self, cursor, codigo_str: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT * FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?
            """,
            (codigo_str,),
        )
        return cursor.fetchone()

    def select_todo_por_id(self, cursor, aliado_id: int) -> Optional[Any]:
        cursor.execute("SELECT * FROM aliados WHERE id = ?", (aliado_id,))
        return cursor.fetchone()

    def select_grupo_id_por_codigo(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
        return row[0] if row else None

    def select_activacion_por_id(self, cursor, aliado_id: int) -> Optional[Any]:
        cursor.execute(
            """SELECT id, codigo, oficio, codigo_postal, invitado_por_codigo, estado
               FROM aliados WHERE id = ?""",
            (int(aliado_id),),
        )
        return cursor.fetchone()

    def select_activacion_por_codigo(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            """SELECT id, codigo, oficio, codigo_postal, invitado_por_codigo, estado
               FROM aliados WHERE codigo = ?""",
            (codigo,),
        )
        return cursor.fetchone()

    def select_espera_por_codigo(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            "SELECT id, codigo, oficio, codigo_postal, estado FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone()

    def select_para_eliminar(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, estado, nombre, marca, oficio, codigo_postal, email, telefono
            FROM aliados WHERE codigo = ?
            """,
            (codigo,),
        )
        return cursor.fetchone()

    def select_nombre_grupo(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute("SELECT nombre FROM grupos WHERE id = ?", (grupo_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def select_codigo_postal_grupo(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT codigo_postal FROM grupos WHERE id = ?",
            (grupo_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def select_grupo_activo_por_id(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, estado FROM grupos WHERE id = ? AND estado = 'activo'",
            (grupo_id,),
        )
        return cursor.fetchone()

    # --- Escrituras ---

    def insertar(
        self,
        cursor,
        codigo: str,
        nombre: str,
        marca: str,
        oficio: str,
        codigo_postal: str,
        email: str,
        telefono: str,
        estado: str,
        score: int,
        descripcion_servicio: Optional[str],
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO aliados
            (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score, descripcion_servicio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                codigo,
                nombre,
                marca,
                oficio,
                codigo_postal,
                email,
                telefono,
                estado,
                score,
                descripcion_servicio,
            ),
        )
        return cursor.lastrowid

    def insertar_seed(
        self,
        cursor,
        codigo: str,
        nombre: str,
        marca: str,
        oficio: str,
        codigo_postal: str,
        email: str,
        telefono: str,
        estado: str,
        score: int,
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO aliados
            (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score),
        )
        return cursor.lastrowid

    def update_completar_pendiente(
        self,
        cursor,
        aliado_id: int,
        nombre: str,
        marca: str,
        oficio: str,
        codigo_postal: str,
        email: str,
        telefono: str,
        estado_final: str,
        score: int,
        descripcion_servicio: Optional[str],
    ) -> int:
        cursor.execute(
            """
            UPDATE aliados
            SET nombre = ?,
                marca = ?,
                oficio = ?,
                codigo_postal = ?,
                email = ?,
                telefono = ?,
                estado = ?,
                score = ?,
                grupo_id = NULL,
                descripcion_servicio = ?,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ? AND estado = 'pendiente_completar'
            """,
            (
                nombre,
                marca,
                oficio,
                codigo_postal,
                email,
                telefono,
                estado_final,
                score,
                descripcion_servicio,
                aliado_id,
            ),
        )
        return cursor.rowcount

    def update_grupo_id(self, cursor, grupo_id: Any, aliado_id: int) -> int:
        cursor.execute(
            "UPDATE aliados SET grupo_id = ? WHERE id = ?",
            (grupo_id, aliado_id),
        )
        return cursor.rowcount

    def update_campos_por_codigo(
        self, cursor, campos_update: Dict[str, Any], codigo: str
    ) -> int:
        set_clause = ", ".join([f"{k} = ?" for k in campos_update.keys()])
        values = list(campos_update.values()) + [codigo]
        cursor.execute(
            f"""
            UPDATE aliados
            SET {set_clause}, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
            """,
            values,
        )
        return cursor.rowcount

    def update_activar_con_grupo(self, cursor, grupo_id: int, aliado_id: int) -> int:
        cursor.execute(
            """UPDATE aliados
               SET estado = 'activo', grupo_id = ?, actualizado_en = CURRENT_TIMESTAMP
               WHERE id = ? AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'""",
            (grupo_id, int(aliado_id)),
        )
        return cursor.rowcount

    def update_activar_sin_grupo(self, cursor, aliado_id: int) -> int:
        cursor.execute(
            """UPDATE aliados
               SET estado = 'activo', actualizado_en = CURRENT_TIMESTAMP
               WHERE id = ? AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'""",
            (int(aliado_id),),
        )
        return cursor.rowcount

    def update_suspendido_temporal(self, cursor, codigo_aliado: str) -> int:
        cursor.execute(
            "UPDATE aliados SET estado = 'suspendido_temporal', actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?",
            (codigo_aliado,),
        )
        return cursor.rowcount

    def update_incorporar_espera(
        self, cursor, grupo_asignado: int, aliado_id: int
    ) -> int:
        cursor.execute(
            "UPDATE aliados SET estado = 'activo', grupo_id = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (grupo_asignado, aliado_id),
        )
        return cursor.rowcount

    def insertar_historico_pausa(self, cursor, razon: str, codigo_aliado: str) -> None:
        cursor.execute(
            """
            INSERT INTO evaluaciones_historico
            (codigo_aliado, estado_anterior, estado_nuevo, score_anterior, score_nuevo, razon_cambio)
            SELECT
                a.codigo,
                e.estado AS estado_anterior,
                'pausado_manual' AS estado_nuevo,
                e.score AS score_anterior,
                e.score AS score_nuevo,
                ?
            FROM aliados a
            LEFT JOIN evaluaciones e ON e.codigo_aliado = a.codigo
            WHERE a.codigo = ?
            """,
            (razon, codigo_aliado),
        )

    def insertar_eliminado(
        self,
        cursor,
        codigo: str,
        nombre: str,
        marca: str,
        oficio: str,
        codigo_postal: str,
        email: str,
        telefono: str,
        estado_anterior: str,
        motivo_txt: str,
        admin_codigo: Optional[str],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO aliados_eliminados
            (codigo, nombre, marca, oficio, codigo_postal, email, telefono,
             estado_anterior, motivo, admin_codigo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                codigo,
                nombre,
                marca,
                oficio,
                codigo_postal,
                email,
                telefono,
                estado_anterior,
                motivo_txt,
                admin_codigo,
            ),
        )

    def delete_por_codigo(self, cursor, codigo: str) -> int:
        cursor.execute("DELETE FROM aliados WHERE codigo = ?", (codigo,))
        return cursor.rowcount

    def soft_delete_por_codigo(self, cursor, codigo: str) -> int:
        """Marca perfil eliminado conservando código y linaje para el árbol."""
        cursor.execute(
            """
            UPDATE aliados
            SET estado = 'eliminado',
                nombre = '[Perfil eliminado]',
                email = NULL,
                telefono = NULL,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
              AND COALESCE(estado, '') != 'sistema'
            """,
            (codigo,),
        )
        return cursor.rowcount

    def insertar_acceso_dia(self, cursor, codigo_aliado: str, dia_val: str) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO aliado_accesos_dia (codigo_aliado, dia)
            VALUES (?, ?)
            """,
            (codigo_aliado, dia_val),
        )

    # --- Listados ---

    def listar_en_pool(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score,
                   COALESCE(derrotas_competencia, 0) AS derrotas_competencia, creado_en, actualizado_en
            FROM aliados
            WHERE estado = 'activo' AND COALESCE(derrotas_competencia, 0) = 1
            ORDER BY codigo
            """
        )
        return cursor.fetchall()

    def listar_admin(
        self, cursor, col_retador: str, filtro_postal: Optional[str] = None
    ) -> List[Any]:
        base_query = """
            SELECT
                a.*,
                g.nombre AS grupo_nombre,
                e.estado AS eval_estado,
                e.score AS eval_score,
                e.intencion AS eval_intencion,
                e.tasa_respuesta,
                e.tasa_confirmacion,
                e.meses_sin_trabajo,
                e.ciclos_consecutivos,
                e.razones AS eval_razones,
                e.severidad AS eval_severidad,
                e.actualizado_en AS eval_actualizado_en,
                inv.nombre AS invitado_por_nombre,
                inv.codigo AS invitado_por_codigo_join,
                (
                    SELECT COUNT(*)
                    FROM aliados h
                    WHERE h.invitado_por_codigo = a.codigo
                      AND COALESCE(h.estado, '') NOT IN (
                          'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                      )
                ) AS hijos_directos_count,
                (
                    SELECT COUNT(*)
                    FROM contactos_ruana c
                    WHERE c.solicitante_codigo = a.codigo OR c.profesional_codigo = a.codigo
                ) AS total_contactos,
                (
                    SELECT COUNT(*)
                    FROM contactos_ruana c
                    WHERE (c.solicitante_codigo = a.codigo OR c.profesional_codigo = a.codigo)
                      AND datetime(c.creado_en) >= datetime('now', '-30 day')
                ) AS contactos_30d,
                (
                    SELECT 1 FROM competencia c
                    WHERE c.""" + col_retador + """ = a.codigo AND c.estado = 'activa' LIMIT 1
                ) AS es_retador_activo,
                (
                    SELECT 1 FROM competencia c
                    WHERE c.aliado_original_codigo = a.codigo AND c.estado = 'activa' LIMIT 1
                ) AS es_titular_en_competencia
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            LEFT JOIN evaluaciones e ON e.codigo_aliado = a.codigo
            LEFT JOIN aliados inv ON inv.codigo = a.invitado_por_codigo
            WHERE (a.estado IS NULL OR (
                a.estado != 'expulsado'
                AND a.estado != 'suspendido_temporal'
                AND a.estado != 'sistema'
                AND a.estado != 'pendiente_completar'
            ))
        """
        params: Tuple[Any, ...] = ()
        if filtro_postal:
            base_query += " AND a.codigo_postal = ?"
            params = (filtro_postal,)
        base_query += " ORDER BY a.creado_en DESC"
        cursor.execute(base_query, params)
        return cursor.fetchall()

    def listar_directorio_grupo_con_cp(
        self,
        cursor,
        select_cols: str,
        codigo_excluir: str,
        grupo_id: int,
        cp_filtro: str,
        estados_ok: Sequence[str],
    ) -> List[Any]:
        cursor.execute(
            f"""
            SELECT {select_cols}
            FROM aliados a
            INNER JOIN grupos g ON g.id = a.grupo_id
            WHERE a.estado IN (?, ?) AND a.codigo != ?
              AND a.grupo_id = ?
              AND TRIM(COALESCE(g.codigo_postal, '')) = ?
              AND TRIM(COALESCE(a.codigo_postal, '')) = ?
            ORDER BY a.nombre
            """,
            (estados_ok[0], estados_ok[1], codigo_excluir, grupo_id, cp_filtro, cp_filtro),
        )
        return cursor.fetchall()

    def listar_directorio_solo_grupo(
        self,
        cursor,
        grupo_id: int,
        codigo_excluir: str,
        estados_ok: Sequence[str],
    ) -> List[Any]:
        cursor.execute(
            f"""
            SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score,
                   descripcion_servicio, {ALIADO_FOTO_PERFIL_COLUMN}, creado_en
            FROM aliados
            WHERE grupo_id = ? AND estado IN (?, ?) AND codigo != ?
            ORDER BY nombre
            """,
            (grupo_id, estados_ok[0], estados_ok[1], codigo_excluir),
        )
        return cursor.fetchall()

    def listar_directorio_por_cp(
        self,
        cursor,
        cp_filtro: str,
        codigo_excluir: str,
        estados_ok: Sequence[str],
    ) -> List[Any]:
        cursor.execute(
            f"""
            SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score,
                   descripcion_servicio, {ALIADO_FOTO_PERFIL_COLUMN}, creado_en
            FROM aliados
            WHERE TRIM(COALESCE(codigo_postal, '')) = ?
              AND estado IN (?, ?) AND codigo != ?
            ORDER BY nombre
            """,
            (cp_filtro, estados_ok[0], estados_ok[1], codigo_excluir),
        )
        return cursor.fetchall()

    def listar_pendiente_validacion(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT id, codigo, nombre, marca, oficio, codigo_postal, email, telefono, creado_en
            FROM aliados WHERE LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'
            ORDER BY creado_en DESC
            """
        )
        return cursor.fetchall()

    def listar_eliminados(self, cursor, limite: int) -> List[Any]:
        cursor.execute(
            """
            SELECT id, codigo, nombre, marca, oficio, codigo_postal,
                   email, telefono, estado_anterior, motivo, admin_codigo, eliminado_en
            FROM aliados_eliminados
            ORDER BY eliminado_en DESC
            LIMIT ?
            """,
            (max(1, min(limite, 500)),),
        )
        return cursor.fetchall()

    def listar_en_espera(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT id, codigo, nombre, marca, oficio, codigo_postal, email, telefono,
                   estado, score, descripcion_servicio, creado_en, actualizado_en
            FROM aliados WHERE estado = 'en_espera'
            ORDER BY creado_en ASC
            """
        )
        return cursor.fetchall()
