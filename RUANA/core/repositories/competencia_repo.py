"""
Repositorio de Competencia (Campamento Base).

Acceso a datos de competencia, competencia_pendiente y purgas asociadas.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence


class CompetenciaRepo:
    """Operaciones de persistencia del dominio competencia."""

    def cancelar_pendiente(self, cursor, codigo: str) -> int:
        cursor.execute(
            "UPDATE competencia_pendiente SET estado = 'cancelada' "
            "WHERE aliado_codigo = ? AND estado = 'pendiente'",
            (codigo,),
        )
        return cursor.rowcount

    def tiene_pendiente(self, cursor, codigo: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM competencia_pendiente WHERE aliado_codigo = ? AND estado = 'pendiente' LIMIT 1",
            (codigo,),
        )
        return cursor.fetchone() is not None

    def listar_pendientes(
        self, cursor, codigo_postal: Optional[str] = None, oficio: Optional[str] = None
    ) -> List[Any]:
        q = "SELECT id, aliado_codigo, grupo_id, oficio, codigo_postal FROM competencia_pendiente WHERE estado = 'pendiente'"
        params: List[Any] = []
        if codigo_postal:
            q += " AND codigo_postal = ?"
            params.append(codigo_postal.strip())
        if oficio:
            q += " AND oficio = ?"
            params.append(oficio.strip())
        q += " ORDER BY creado_en ASC"
        cursor.execute(q, params)
        return cursor.fetchall()

    def en_competencia_activa(self, cursor, col_retador: str, codigo: str) -> bool:
        cursor.execute(
            f"SELECT 1 FROM competencia WHERE estado = 'activa' "
            f"AND (aliado_original_codigo = ? OR {col_retador} = ?) LIMIT 1",
            (codigo, codigo),
        )
        return cursor.fetchone() is not None

    def listar_pendientes_admin(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT p.id, p.aliado_codigo, p.grupo_id, p.oficio, p.codigo_postal,
                   p.score_al_crear, p.creado_en, a.nombre AS aliado_nombre, g.nombre AS grupo_nombre
            FROM competencia_pendiente p
            JOIN aliados a ON a.codigo = p.aliado_codigo
            LEFT JOIN grupos g ON g.id = p.grupo_id
            WHERE p.estado = 'pendiente'
            ORDER BY p.creado_en ASC
            """
        )
        return cursor.fetchall()

    def listar_historial_admin(self, cursor, col_ret: str, limite: int) -> List[Any]:
        cursor.execute(
            f"""
            SELECT c.id, c.grupo_id, c.oficio, c.aliado_original_codigo, c.{col_ret} AS retador_codigo,
                   c.fecha_inicio, c.fecha_fin_prevista, c.fecha_cierre, c.ganador_codigo,
                   c.score_titular_inicio, c.score_retador_inicio,
                   c.score_titular_final, c.score_retador_final,
                   t.nombre AS titular_nombre, r.nombre AS retador_nombre, g.nombre AS grupo_nombre
            FROM competencia c
            JOIN aliados t ON t.codigo = c.aliado_original_codigo
            JOIN aliados r ON r.codigo = c.{col_ret}
            LEFT JOIN grupos g ON g.id = c.grupo_id
            WHERE c.estado = 'finalizada'
            ORDER BY COALESCE(c.fecha_cierre, c.fecha_fin_prevista) DESC
            LIMIT ?
            """,
            (limite,),
        )
        return cursor.fetchall()

    def listar_activas_admin(self, cursor, cols: dict) -> List[Any]:
        cursor.execute(
            """
            SELECT c.id, c.grupo_id, c.oficio, c.aliado_original_codigo,
                   c.""" + cols["retador_codigo"] + """ AS retador_codigo,
                   c.""" + cols["retador_grupo_anterior_id"] + """ AS retador_grupo_anterior_id,
                   c.fecha_inicio, c.fecha_fin_prevista,
                   c.score_titular_inicio, c.""" + cols["score_retador_inicio"] + """ AS score_retador_inicio,
                   c.score_titular_actual, c.""" + cols["score_retador_actual"] + """ AS score_retador_actual, c.motivo,
                   t.id AS titular_id, t.nombre AS titular_nombre, t.score AS titular_score_actual,
                   s.id AS retador_id, s.nombre AS retador_nombre, s.score AS retador_score_actual,
                   g.nombre AS grupo_nombre, g_origen.nombre AS grupo_origen_nombre
            FROM competencia c
            JOIN aliados t ON t.codigo = c.aliado_original_codigo
            JOIN aliados s ON s.codigo = c.""" + cols["retador_codigo"] + """
            JOIN grupos g ON g.id = c.grupo_id
            LEFT JOIN grupos g_origen ON g_origen.id = c.""" + cols["retador_grupo_anterior_id"] + """
            WHERE c.estado = 'activa'
            ORDER BY c.fecha_inicio ASC
            """
        )
        return cursor.fetchall()

    def select_aliado_activo_con_grupo(self, cursor, codigo_aliado: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT a.grupo_id, a.oficio, a.score, g.codigo_postal, g.ciudad, g.provincia
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            WHERE a.codigo = ? AND a.estado = 'activo'
            """,
            (codigo_aliado,),
        )
        return cursor.fetchone()

    def insertar_competencia(
        self,
        cursor,
        grupo_id: int,
        oficio: str,
        codigo_aliado: str,
        retador_codigo: str,
        retador_grupo_anterior_id: Optional[int],
        score_titular_inicio: int,
        score_retador_inicio: int,
        fecha_fin: str,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO competencia (grupo_id, oficio, aliado_original_codigo, retador_codigo, retador_grupo_anterior_id,
                score_titular_inicio, score_retador_inicio, score_titular_actual, score_retador_actual,
                fecha_fin_prevista, estado, motivo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa', 'score bajo')
            """,
            (
                grupo_id,
                oficio,
                codigo_aliado,
                retador_codigo,
                retador_grupo_anterior_id,
                score_titular_inicio,
                score_retador_inicio,
                score_titular_inicio,
                score_retador_inicio,
                fecha_fin,
            ),
        )
        return int(cursor.lastrowid)

    def activar_retador_en_grupo(self, cursor, grupo_id: int, retador_codigo: str) -> None:
        cursor.execute(
            "UPDATE aliados SET estado = 'activo', grupo_id = ? WHERE codigo = ?",
            (grupo_id, retador_codigo),
        )

    def mover_retador_a_grupo(self, cursor, grupo_id: int, retador_codigo: str) -> None:
        cursor.execute(
            "UPDATE aliados SET grupo_id = ? WHERE codigo = ?",
            (grupo_id, retador_codigo),
        )

    def marcar_grupo_en_competencia(self, cursor, grupo_id: int) -> None:
        cursor.execute("UPDATE grupos SET estado = 'en_competencia' WHERE id = ?", (grupo_id,))

    def listar_vencidas(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT id, grupo_id, oficio, aliado_original_codigo, retador_codigo, retador_grupo_anterior_id
            FROM competencia WHERE estado = 'activa' AND fecha_fin_prevista <= datetime('now')
            """
        )
        return cursor.fetchall()

    def select_score_oficio(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute("SELECT score, oficio FROM aliados WHERE codigo = ?", (codigo,))
        return cursor.fetchone()

    def select_score(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (codigo,))
        return cursor.fetchone()

    def select_grupo_ubicacion(self, cursor, grupo_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT codigo_postal, ciudad, provincia FROM grupos WHERE id = ?",
            (grupo_id,),
        )
        return cursor.fetchone()

    def set_grupo_aliado(self, cursor, grupo_id: int, codigo: str) -> None:
        cursor.execute(
            "UPDATE aliados SET grupo_id = ? WHERE codigo = ?",
            (grupo_id, codigo),
        )

    def select_derrotas(self, cursor, codigo: str) -> int:
        cursor.execute(
            "SELECT COALESCE(derrotas_competencia, 0) FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        return int((cursor.fetchone() or [0])[0] or 0)

    def mover_perdedor_con_reinicio(
        self, cursor, gid_perdedor: int, score_reinicio: int, perdedor: str
    ) -> None:
        cursor.execute(
            """UPDATE aliados SET grupo_id = ?, score = ?,
               derrotas_competencia = COALESCE(derrotas_competencia, 0) + 1,
               actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?""",
            (gid_perdedor, score_reinicio, perdedor),
        )

    def sacar_perdedor_con_reinicio(
        self, cursor, score_reinicio: int, perdedor: str
    ) -> None:
        cursor.execute(
            """UPDATE aliados SET grupo_id = NULL, score = ?,
               derrotas_competencia = COALESCE(derrotas_competencia, 0) + 1,
               actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?""",
            (score_reinicio, perdedor),
        )

    def expulsar_si_dos_derrotas(self, cursor, perdedor: str) -> None:
        cursor.execute(
            "UPDATE aliados SET estado = 'expulsado' WHERE codigo = ? AND COALESCE(derrotas_competencia, 0) >= 2",
            (perdedor,),
        )

    def finalizar_competencia(
        self,
        cursor,
        ganador: str,
        score_orig: int,
        score_ret: int,
        competencia_id: int,
    ) -> None:
        cursor.execute(
            """UPDATE competencia SET estado = 'finalizada', ganador_codigo = ?,
               score_titular_final = ?, score_retador_final = ?,
               score_titular_actual = ?, score_retador_actual = ?,
               fecha_cierre = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (ganador, score_orig, score_ret, score_orig, score_ret, competencia_id),
        )

    def marcar_grupo_activo(self, cursor, grupo_id: int) -> None:
        cursor.execute("UPDATE grupos SET estado = 'activo' WHERE id = ?", (grupo_id,))

    def existe_grupo_activo(self, cursor, grupo_id: int) -> bool:
        cursor.execute(
            "SELECT id FROM grupos WHERE id = ? AND estado = 'activo'",
            (grupo_id,),
        )
        return cursor.fetchone() is not None

    def existe_aliado(self, cursor, codigo: str) -> bool:
        cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (codigo,))
        return cursor.fetchone() is not None

    def insertar_competencia_forzada(
        self,
        cursor,
        grupo_id: int,
        oficio_s: str,
        aliado_original_codigo: str,
        retador_codigo: str,
        fecha_fin: str,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO competencia (grupo_id, oficio, aliado_original_codigo, retador_codigo, fecha_fin_prevista, estado)
            VALUES (?, ?, ?, ?, ?, 'activa')
            """,
            (grupo_id, oficio_s, aliado_original_codigo, retador_codigo, fecha_fin),
        )
        return cursor.lastrowid

    def select_info_aliado(self, cursor, col_ret: str, codigo: str) -> Optional[Any]:
        cursor.execute(
            f"""
            SELECT c.id, c.grupo_id, c.oficio, c.aliado_original_codigo, c.{col_ret} AS retador_codigo,
                   c.fecha_inicio, c.fecha_fin_prevista, c.estado, g.nombre AS grupo_nombre
            FROM competencia c
            LEFT JOIN grupos g ON g.id = c.grupo_id
            WHERE c.estado = 'activa'
              AND (c.aliado_original_codigo = ? OR c.{col_ret} = ?)
            LIMIT 1
            """,
            (codigo, codigo),
        )
        return cursor.fetchone()

    def select_activa_grupo_oficio(self, cursor, cols: dict, grupo_id: int, oficio: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, grupo_id, oficio, aliado_original_codigo,
                   """ + cols["retador_codigo"] + """ AS retador_codigo,
                   """ + cols["retador_grupo_anterior_id"] + """ AS retador_grupo_anterior_id,
                   fecha_inicio, fecha_fin_prevista, estado
            FROM competencia WHERE grupo_id = ? AND oficio = ? AND estado = 'activa' LIMIT 1
            """,
            (grupo_id, (oficio or "").strip()),
        )
        return cursor.fetchone()

    def buscar_retador_en_espera(
        self, cursor, oficio: str, codigo_postal: str, codigo_aliado_en_riesgo: str
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT a.codigo, a.score, a.grupo_id, a.estado, a.codigo_postal,
                   0 AS n_aliados
            FROM aliados a
            WHERE a.estado = 'en_espera' AND a.oficio = ? AND a.codigo_postal = ?
              AND a.codigo != ?
            ORDER BY a.creado_en ASC
            LIMIT 1
            """,
            (oficio, codigo_postal, codigo_aliado_en_riesgo),
        )
        return cursor.fetchone()

    def buscar_retador_activo(
        self,
        cursor,
        oficio: str,
        codigo_postal: str,
        codigo_aliado_en_riesgo: str,
        grupo_id: int,
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT a.codigo, a.score, a.grupo_id, a.estado, g.codigo_postal,
                   (SELECT COUNT(*) FROM aliados a2
                    WHERE a2.grupo_id = a.grupo_id AND a2.estado = 'activo') AS n_aliados
            FROM aliados a
            JOIN grupos g ON g.id = a.grupo_id AND g.estado = 'activo'
            WHERE a.estado = 'activo' AND a.oficio = ? AND g.codigo_postal = ?
              AND a.codigo != ? AND (a.grupo_id IS NULL OR a.grupo_id != ?)
            ORDER BY n_aliados ASC, a.score DESC, a.codigo
            LIMIT 1
            """,
            (oficio, codigo_postal, codigo_aliado_en_riesgo, grupo_id),
        )
        return cursor.fetchone()

    def gano_ultimos_meses(self, cursor, codigo_aliado: str, meses: int) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM competencia
            WHERE estado = 'finalizada' AND ganador_codigo = ?
            AND date(fecha_fin_prevista) >= date('now', ?)
            LIMIT 1
            """,
            (codigo_aliado, f"-{meses} months"),
        )
        return cursor.fetchone() is not None

    def suspender_temporal(self, cursor, codigo: str) -> None:
        cursor.execute(
            "UPDATE aliados SET estado = 'suspendido_temporal', actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?",
            (codigo,),
        )

    def purga_datos_aliado(self, cursor, codigo: str, aliado_id: int, col_retador: str, backend: str) -> None:
        contacto_filter = (
            "SELECT id FROM contactos_ruana "
            "WHERE solicitante_codigo = ? OR profesional_codigo = ?"
        )
        cursor.execute(
            f"DELETE FROM negociacion_eventos WHERE contacto_id IN ({contacto_filter})",
            (codigo, codigo),
        )
        cursor.execute(
            f"DELETE FROM chat_mensajes WHERE contacto_id IN ({contacto_filter}) OR emisor_codigo = ?",
            (codigo, codigo, codigo),
        )
        cursor.execute(
            f"DELETE FROM contacto_panel_oculto WHERE codigo_aliado = ? "
            f"OR contacto_id IN ({contacto_filter})",
            (codigo, codigo, codigo),
        )
        cursor.execute(
            f"DELETE FROM contacto_penalizaciones_aplicadas WHERE contacto_id IN ({contacto_filter})",
            (codigo, codigo),
        )
        cursor.execute(
            f"DELETE FROM confirmaciones_trabajo WHERE aliado_id = ? "
            f"OR contacto_id IN ({contacto_filter})",
            (aliado_id, codigo, codigo),
        )
        cursor.execute(
            "DELETE FROM payment_conflicts WHERE contratante_id = ? OR profesional_id = ?",
            (aliado_id, aliado_id),
        )
        cursor.execute(
            f"DELETE FROM ingresos_ruana WHERE contacto_id IN ({contacto_filter})",
            (codigo, codigo),
        )
        cursor.execute(
            "DELETE FROM contactos_ruana WHERE solicitante_codigo = ? OR profesional_codigo = ?",
            (codigo, codigo),
        )
        cursor.execute(
            "DELETE FROM solicitudes WHERE solicitante_codigo = ? OR atendido_por_codigo = ?",
            (codigo, codigo),
        )
        try:
            cursor.execute("DELETE FROM solicitudes WHERE creado_por_codigo = ?", (codigo,))
        except Exception:
            pass
        cursor.execute(
            f"""
            DELETE FROM competencia
            WHERE aliado_original_codigo = ?
               OR {col_retador} = ?
               OR ganador_codigo = ?
            """,
            (codigo, codigo, codigo),
        )
        cursor.execute("DELETE FROM competencia_pendiente WHERE aliado_codigo = ?", (codigo,))
        cursor.execute("DELETE FROM score_movimientos WHERE codigo_aliado = ?", (codigo,))
        cursor.execute("DELETE FROM evaluaciones WHERE codigo_aliado = ?", (codigo,))
        cursor.execute("DELETE FROM evaluaciones_historico WHERE codigo_aliado = ?", (codigo,))
        cursor.execute("DELETE FROM catalogo_servicios_aliado WHERE aliado_codigo = ?", (codigo,))
        cursor.execute("DELETE FROM notificaciones_aliado WHERE aliado_codigo = ?", (codigo,))
        cursor.execute(
            """
            DELETE FROM ruana_soporte_mensajes
            WHERE conversacion_id IN (
                SELECT id FROM ruana_soporte_conversaciones WHERE aliado_codigo = ?
            )
            """,
            (codigo,),
        )
        cursor.execute("DELETE FROM ruana_soporte_conversaciones WHERE aliado_codigo = ?", (codigo,))
        cursor.execute("DELETE FROM aliado_accesos_dia WHERE codigo_aliado = ?", (codigo,))
        cursor.execute("DELETE FROM invitacion_campana_usos WHERE codigo_aliado = ?", (codigo,))
        cursor.execute(
            "DELETE FROM referidos WHERE codigo_referido = ? OR codigo_invitador = ?",
            (codigo, codigo),
        )
        cursor.execute(
            "DELETE FROM invitaciones WHERE codigo = ? OR invitador_aliado_id = ?",
            (codigo, aliado_id),
        )
        cursor.execute("DELETE FROM invitaciones_oficio WHERE aliado_id = ?", (aliado_id,))
        cursor.execute(
            """
            UPDATE aliados
            SET invitado_por_codigo = NULL, invitado_origen = NULL
            WHERE invitado_por_codigo = ?
            """,
            (codigo,),
        )
        if backend == "postgres":
            try:
                cursor.execute("DELETE FROM profiles WHERE aliado_codigo = ?", (codigo,))
            except Exception:
                pass
            try:
                cursor.execute(
                    "SELECT auth_user_id FROM aliados WHERE id = ?",
                    (aliado_id,),
                )
                auth_row = cursor.fetchone()
                auth_user_id = auth_row[0] if auth_row else None
                if auth_user_id:
                    cursor.execute("DELETE FROM auth.users WHERE id = ?", (auth_user_id,))
            except Exception:
                pass
