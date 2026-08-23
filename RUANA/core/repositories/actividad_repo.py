"""
Repositorio de lectura para la cinta de actividad RUANA.

Solo consultas sobre datos reales ya persistidos. Sin reglas de negocio de formato.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


class ActividadRepo:
    """Consultas de actividad reciente acotadas por grupo / código postal."""

    VENTANA_DIAS = 30

    def _ventana_sql(self) -> str:
        return f"-{int(self.VENTANA_DIAS)} days"

    def contexto_aliado(self, cursor, codigo: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT a.codigo, a.nombre, a.grupo_id, TRIM(a.codigo_postal) AS codigo_postal,
                   g.codigo_postal AS grupo_cp
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            WHERE TRIM(CAST(a.codigo AS TEXT)) = ?
            """,
            (codigo.strip(),),
        )
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        cp = (data.get("codigo_postal") or data.get("grupo_cp") or "").strip()
        data["codigo_postal"] = cp
        return data

    def listar_solicitudes_nuevas_grupo(
        self, cursor, grupo_id: int, excluir_codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, solicitante_codigo, solicitante_nombre, oficio, created_at AS creado_en
            FROM solicitudes
            WHERE grupo_id = ?
              AND created_at >= datetime('now', '-30 days')
            ORDER BY created_at DESC
            LIMIT 25
            """,
            (int(grupo_id),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_solicitudes_atendidas_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, atendido_por_codigo, atendido_por_nombre, atendido_at AS creado_en
            FROM solicitudes
            WHERE grupo_id = ?
              AND estado = 'atendida'
              AND atendido_at IS NOT NULL
              AND atendido_at >= datetime('now', '-30 days')
            ORDER BY atendido_at DESC
            LIMIT 25
            """,
            (int(grupo_id),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_solicitudes_asignadas_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, asignada_a_codigo, asignada_a_nombre, candidato_at AS creado_en
            FROM solicitudes
            WHERE grupo_id = ?
              AND asignada_a_codigo IS NOT NULL
              AND TRIM(asignada_a_codigo) != ''
              AND candidato_at >= datetime('now', '-30 days')
            ORDER BY candidato_at DESC
            LIMIT 25
            """,
            (int(grupo_id),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_propuestas_grupo(self, cursor, grupo_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, candidato_por_codigo, candidato_por_nombre,
                   solicitante_nombre, candidato_at AS creado_en
            FROM solicitudes
            WHERE grupo_id = ?
              AND estado = 'candidato_pendiente'
              AND candidato_por_codigo IS NOT NULL
              AND candidato_at >= datetime('now', '-30 days')
            ORDER BY candidato_at DESC
            LIMIT 25
            """,
            (int(grupo_id),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_contactos_nuevos_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio,
                   c.creado_en,
                   sol.nombre AS solicitante_nombre,
                   pro.nombre AS profesional_nombre,
                   sol.oficio AS solicitante_oficio
            FROM contactos_ruana c
            INNER JOIN aliados sol ON sol.codigo = c.solicitante_codigo
            INNER JOIN aliados pro ON pro.codigo = c.profesional_codigo
            WHERE sol.grupo_id = ?
              AND pro.grupo_id = ?
              AND c.creado_en >= datetime('now', '-30 days')
            ORDER BY c.creado_en DESC
            LIMIT 25
            """,
            (int(grupo_id), int(grupo_id)),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_acuerdos_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT c.id, c.solicitante_codigo, c.profesional_codigo,
                   c.importe_acordado, c.acuerdo_alcanzado_en AS creado_en,
                   sol.nombre AS solicitante_nombre,
                   pro.nombre AS profesional_nombre
            FROM contactos_ruana c
            INNER JOIN aliados sol ON sol.codigo = c.solicitante_codigo
            INNER JOIN aliados pro ON pro.codigo = c.profesional_codigo
            WHERE sol.grupo_id = ?
              AND pro.grupo_id = ?
              AND c.estado IN ('acuerdo_alcanzado', 'pendiente_de_pago', 'trabajo_en_progreso', 'trabajo_cerrado')
              AND c.acuerdo_alcanzado_en IS NOT NULL
              AND c.acuerdo_alcanzado_en >= datetime('now', '-30 days')
            ORDER BY c.acuerdo_alcanzado_en DESC
            LIMIT 25
            """,
            (int(grupo_id), int(grupo_id)),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_encargos_cerrados_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT c.id, c.solicitante_codigo, c.profesional_codigo,
                   c.fecha_cierre AS creado_en,
                   sol.nombre AS solicitante_nombre,
                   pro.nombre AS profesional_nombre
            FROM contactos_ruana c
            INNER JOIN aliados sol ON sol.codigo = c.solicitante_codigo
            INNER JOIN aliados pro ON pro.codigo = c.profesional_codigo
            WHERE sol.grupo_id = ?
              AND pro.grupo_id = ?
              AND c.estado = 'trabajo_cerrado'
              AND c.fecha_cierre IS NOT NULL
              AND c.fecha_cierre >= datetime('now', '-30 days')
            ORDER BY c.fecha_cierre DESC
            LIMIT 25
            """,
            (int(grupo_id), int(grupo_id)),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_aliados_nuevos_grupo(
        self, cursor, grupo_id: int, excluir_codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT codigo, nombre, oficio, creado_en
            FROM aliados
            WHERE grupo_id = ?
              AND estado = 'activo'
              AND TRIM(CAST(codigo AS TEXT)) != ?
              AND creado_en >= datetime('now', '-30 days')
            ORDER BY creado_en DESC
            LIMIT 25
            """,
            (int(grupo_id), excluir_codigo.strip()),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_invitaciones_recientes_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT i.codigo, i.creado_en, inv.nombre AS invitador_nombre,
                   ref.nombre AS invitado_nombre, ref.oficio AS invitado_oficio,
                   r.creado_en AS uso_en
            FROM invitaciones i
            INNER JOIN aliados inv ON inv.id = i.invitador_aliado_id
            LEFT JOIN referidos rf ON rf.codigo_invitador = inv.codigo
            LEFT JOIN aliados ref ON ref.codigo = rf.codigo_referido
            LEFT JOIN referidos r ON r.codigo_invitador = inv.codigo
            WHERE inv.grupo_id = ?
              AND i.creado_en >= datetime('now', '-30 days')
            ORDER BY i.creado_en DESC
            LIMIT 25
            """,
            (int(grupo_id),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_referidos_recientes_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT r.creado_en, inv.nombre AS invitador_nombre,
                   ref.nombre AS referido_nombre, ref.oficio AS referido_oficio
            FROM referidos r
            INNER JOIN aliados inv ON inv.codigo = r.codigo_invitador
            INNER JOIN aliados ref ON ref.codigo = r.codigo_referido
            WHERE inv.grupo_id = ?
              AND ref.grupo_id = ?
              AND r.creado_en >= datetime('now', '-30 days')
            ORDER BY r.creado_en DESC
            LIMIT 25
            """,
            (int(grupo_id), int(grupo_id)),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_catalogo_actualizado_grupo(
        self, cursor, grupo_id: int, excluir_codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT c.aliado_codigo, a.nombre, MAX(c.actualizado_en) AS creado_en
            FROM catalogo_servicios_aliado c
            INNER JOIN aliados a ON a.codigo = c.aliado_codigo
            WHERE a.grupo_id = ?
              AND TRIM(CAST(a.codigo AS TEXT)) != ?
              AND c.actualizado_en >= datetime('now', '-30 days')
              AND TRIM(COALESCE(c.descripcion, '')) != ''
            GROUP BY c.aliado_codigo, a.nombre
            ORDER BY creado_en DESC
            LIMIT 15
            """,
            (int(grupo_id), excluir_codigo.strip()),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_foto_actualizada_grupo(
        self, cursor, grupo_id: int, excluir_codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT codigo, nombre, actualizado_en AS creado_en
            FROM aliados
            WHERE grupo_id = ?
              AND estado = 'activo'
              AND TRIM(CAST(codigo AS TEXT)) != ?
              AND foto_perfil_url IS NOT NULL
              AND TRIM(foto_perfil_url) != ''
              AND actualizado_en >= datetime('now', '-30 days')
            ORDER BY actualizado_en DESC
            LIMIT 15
            """,
            (int(grupo_id), excluir_codigo.strip()),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_grupos_nuevos_cp(self, cursor, codigo_postal: str) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, nombre, fecha_creacion AS creado_en
            FROM grupos
            WHERE TRIM(codigo_postal) = ?
              AND estado = 'activo'
              AND fecha_creacion >= datetime('now', '-30 days')
            ORDER BY fecha_creacion DESC
            LIMIT 10
            """,
            (codigo_postal.strip(),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_competencias_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT c.id, c.oficio, c.fecha_inicio AS creado_en, c.estado,
                   c.ganador_codigo, c.aliado_original_codigo, c.retador_codigo,
                   tit.nombre AS titular_nombre, ret.nombre AS retador_nombre,
                   gan.nombre AS ganador_nombre
            FROM competencia c
            LEFT JOIN aliados tit ON tit.codigo = c.aliado_original_codigo
            LEFT JOIN aliados ret ON ret.codigo = c.retador_codigo
            LEFT JOIN aliados gan ON gan.codigo = c.ganador_codigo
            WHERE c.grupo_id = ?
              AND c.fecha_inicio >= datetime('now', '-30 days')
            ORDER BY c.fecha_inicio DESC
            LIMIT 20
            """,
            (int(grupo_id),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_score_cambios_grupo(
        self, cursor, grupo_id: int, excluir_codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT sm.id, sm.codigo_aliado, sm.delta, sm.creado_en, a.nombre
            FROM score_movimientos sm
            INNER JOIN aliados a ON a.codigo = sm.codigo_aliado
            WHERE a.grupo_id = ?
              AND TRIM(CAST(sm.codigo_aliado AS TEXT)) != ?
              AND sm.creado_en >= datetime('now', '-30 days')
            ORDER BY sm.creado_en DESC
            LIMIT 20
            """,
            (int(grupo_id), excluir_codigo.strip()),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_aliados_competencia_cp(
        self, cursor, codigo_postal: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT a.codigo, a.nombre, a.actualizado_en AS creado_en
            FROM aliados a
            INNER JOIN grupos g ON g.id = a.grupo_id
            WHERE TRIM(g.codigo_postal) = ?
              AND a.estado = 'en_competencia'
              AND a.actualizado_en >= datetime('now', '-30 days')
            ORDER BY a.actualizado_en DESC
            LIMIT 15
            """,
            (codigo_postal.strip(),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def contar_encargos_mes_cp(self, cursor, codigo_postal: str, anio_mes: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM contactos_ruana c
            INNER JOIN aliados a ON a.codigo IN (c.solicitante_codigo, c.profesional_codigo)
            INNER JOIN grupos g ON g.id = a.grupo_id
            WHERE TRIM(g.codigo_postal) = ?
              AND c.estado = 'trabajo_cerrado'
              AND strftime('%Y-%m', c.fecha_cierre) = ?
            """,
            (codigo_postal.strip(), anio_mes),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_encargos_mes_grupo(
        self, cursor, grupo_id: int, anio_mes: str
    ) -> int:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM contactos_ruana c
            INNER JOIN aliados sol ON sol.codigo = c.solicitante_codigo
            INNER JOIN aliados pro ON pro.codigo = c.profesional_codigo
            WHERE sol.grupo_id = ? AND pro.grupo_id = ?
              AND c.estado = 'trabajo_cerrado'
              AND strftime('%Y-%m', c.fecha_cierre) = ?
            """,
            (int(grupo_id), int(grupo_id), anio_mes),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_aliados_activos_cp(self, cursor, codigo_postal: str) -> int:
        cp = codigo_postal.strip()
        cursor.execute(
            """
            SELECT COUNT(DISTINCT a.codigo)
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            WHERE a.estado = 'activo'
              AND (
                TRIM(COALESCE(a.codigo_postal, '')) = ?
                OR TRIM(COALESCE(g.codigo_postal, '')) = ?
              )
            """,
            (cp, cp),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_aliados_activos_grupo(self, cursor, grupo_id: int) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM aliados
            WHERE estado = 'activo' AND grupo_id = ?
            """,
            (int(grupo_id),),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_recomendaciones_contacto_mes_grupo(
        self, cursor, grupo_id: int, anio_mes: str
    ) -> int:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM contactos_ruana c
            INNER JOIN aliados sol ON sol.codigo = c.solicitante_codigo
            INNER JOIN aliados pro ON pro.codigo = c.profesional_codigo
            WHERE sol.grupo_id = ? AND pro.grupo_id = ?
              AND strftime('%Y-%m', c.creado_en) = ?
            """,
            (int(grupo_id), int(grupo_id), anio_mes),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_solicitudes_atendidas_mes_grupo(
        self, cursor, grupo_id: int, anio_mes: str
    ) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM solicitudes
            WHERE grupo_id = ? AND estado = 'atendida'
              AND strftime('%Y-%m', atendido_at) = ?
            """,
            (int(grupo_id), anio_mes),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def listar_plazas_disponibles_cp(
        self, cursor, codigo_postal: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT DISTINCT g.id AS grupo_id, a.oficio, a.actualizado_en AS creado_en
            FROM aliados a
            INNER JOIN grupos g ON g.id = a.grupo_id
            WHERE TRIM(g.codigo_postal) = ?
              AND a.oficio IS NOT NULL AND TRIM(a.oficio) != ''
              AND a.estado IN ('en_competencia', 'en_espera', 'expulsado')
              AND a.actualizado_en >= datetime('now', '-30 days')
              AND NOT EXISTS (
                  SELECT 1 FROM aliados ax
                  WHERE ax.grupo_id = a.grupo_id
                    AND ax.oficio = a.oficio
                    AND ax.estado = 'activo'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM grupo_oficio_cerrado goc
                  WHERE goc.grupo_id = a.grupo_id AND goc.oficio = a.oficio
              )
            ORDER BY a.actualizado_en DESC
            LIMIT 15
            """,
            (codigo_postal.strip(),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def contar_nuevos_aliados_mes_total(self, cursor, anio_mes: str) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM aliados
            WHERE estado = 'activo'
              AND strftime('%Y-%m', creado_en) = ?
            """,
            (anio_mes,),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_nuevos_aliados_mes_cp(self, cursor, codigo_postal: str, anio_mes: str) -> int:
        cp = codigo_postal.strip()
        cursor.execute(
            """
            SELECT COUNT(DISTINCT a.codigo)
            FROM aliados a
            LEFT JOIN grupos g ON g.id = a.grupo_id
            WHERE a.estado = 'activo'
              AND strftime('%Y-%m', a.creado_en) = ?
              AND (
                TRIM(COALESCE(a.codigo_postal, '')) = ?
                OR TRIM(COALESCE(g.codigo_postal, '')) = ?
              )
            """,
            (anio_mes, cp, cp),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def contar_negociaciones_iniciadas_semana_grupo(
        self, cursor, grupo_id: int
    ) -> int:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM contactos_ruana c
            INNER JOIN aliados sol ON sol.codigo = c.solicitante_codigo
            INNER JOIN aliados pro ON pro.codigo = c.profesional_codigo
            WHERE sol.grupo_id = ? AND pro.grupo_id = ?
              AND c.creado_en >= datetime('now', '-7 days')
            """,
            (int(grupo_id), int(grupo_id)),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def ranking_actividad_grupos_cp(
        self, cursor, codigo_postal: str, grupo_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            WITH act AS (
              SELECT g.id AS grupo_id, g.nombre,
                (SELECT COUNT(*) FROM solicitudes s
                 WHERE s.grupo_id = g.id AND s.created_at >= datetime('now', '-30 days')) AS sol_nuevas,
                (SELECT COUNT(*) FROM solicitudes s
                 WHERE s.grupo_id = g.id AND s.estado = 'atendida'
                   AND s.atendido_at >= datetime('now', '-30 days')) AS sol_atendidas,
                (SELECT COUNT(*) FROM contactos_ruana c
                 INNER JOIN aliados a ON a.codigo = c.solicitante_codigo
                 WHERE a.grupo_id = g.id AND c.creado_en >= datetime('now', '-30 days')) AS contactos_nuevos
              FROM grupos g
              WHERE TRIM(g.codigo_postal) = ? AND g.estado = 'activo'
            )
            SELECT grupo_id, nombre,
                   (sol_nuevas + sol_atendidas + contactos_nuevos) AS actividad_score
            FROM act
            ORDER BY actividad_score DESC, grupo_id ASC
            LIMIT 5
            """,
            (codigo_postal.strip(),),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        if not rows or grupo_id is None:
            return None
        top = rows[0]
        if int(top.get("grupo_id") or 0) == int(grupo_id) and int(top.get("actividad_score") or 0) > 0:
            return top
        return None

    def columnas_tabla(self, cursor, tabla: str) -> List[str]:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return [r[1] for r in cursor.fetchall()]
