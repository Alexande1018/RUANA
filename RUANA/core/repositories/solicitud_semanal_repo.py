"""
Repositorio de solicitudes semanales (Campamento Base).

Acceso a datos de solicitudes_semanales y solicitudes_semanales_respuestas.
Sin reglas de negocio.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class SolicitudSemanalRepo:
    """Operaciones de persistencia del dominio solicitud semanal."""

    def columnas(self, cursor, tabla: str) -> List[str]:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return [r[1] for r in cursor.fetchall()]

    def select_aliado_grupo_nombre(
        self, cursor, codigo: str
    ) -> Optional[Tuple[Any, Any, Any]]:
        cursor.execute(
            "SELECT grupo_id, nombre, oficio FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return (row[0], row[1] or "", row[2] or "")

    def select_solicitud(self, cursor, solicitud_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre,
                   oficio, descripcion, es_oficio_personalizado,
                   semana_inicio, estado, created_at, expira_at
            FROM solicitudes_semanales WHERE id = ?
            """,
            (int(solicitud_id),),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def existe_activa_semana(
        self, cursor, solicitante_codigo: str, semana_inicio: str
    ) -> Optional[int]:
        cursor.execute(
            """
            SELECT id FROM solicitudes_semanales
            WHERE solicitante_codigo = ? AND semana_inicio = ? AND estado = 'activa'
            """,
            (solicitante_codigo, semana_inicio),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else None

    def insertar(
        self,
        cursor,
        grupo_id: Any,
        solicitante_codigo: str,
        solicitante_nombre: str,
        oficio: str,
        descripcion: str,
        es_oficio_personalizado: int,
        semana_inicio: str,
        expira_at: str,
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO solicitudes_semanales (
                grupo_id, solicitante_codigo, solicitante_nombre,
                oficio, descripcion, es_oficio_personalizado,
                semana_inicio, estado, expira_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'activa', ?)
            """,
            (
                grupo_id,
                solicitante_codigo,
                solicitante_nombre,
                oficio,
                descripcion or "",
                es_oficio_personalizado,
                semana_inicio,
                expira_at,
            ),
        )
        return cursor.lastrowid

    def actualizar_oficio_descripcion(
        self,
        cursor,
        solicitud_id: int,
        oficio: str,
        descripcion: str,
        es_oficio_personalizado: int,
    ) -> int:
        cursor.execute(
            """
            UPDATE solicitudes_semanales
            SET oficio = ?, descripcion = ?, es_oficio_personalizado = ?
            WHERE id = ? AND estado = 'activa'
            """,
            (oficio, descripcion or "", es_oficio_personalizado, int(solicitud_id)),
        )
        return cursor.rowcount

    def marcar_expiradas_antes(
        self, cursor, semana_inicio_actual: str
    ) -> None:
        cursor.execute(
            """
            UPDATE solicitudes_semanales
            SET estado = 'expirada'
            WHERE estado = 'activa' AND semana_inicio < ?
            """,
            (semana_inicio_actual,),
        )

    def listar_activas_grupo(
        self, cursor, grupo_id: Any, semana_inicio: str, excluir_codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre,
                   oficio, descripcion, es_oficio_personalizado,
                   semana_inicio, estado, created_at, expira_at
            FROM solicitudes_semanales
            WHERE grupo_id = ? AND semana_inicio = ? AND estado = 'activa'
              AND solicitante_codigo != ?
            ORDER BY created_at DESC
            """,
            (grupo_id, semana_inicio, excluir_codigo),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_propia_semana(
        self, cursor, codigo: str, semana_inicio: str
    ) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre,
                   oficio, descripcion, es_oficio_personalizado,
                   semana_inicio, estado, created_at, expira_at
            FROM solicitudes_semanales
            WHERE solicitante_codigo = ? AND semana_inicio = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (codigo, semana_inicio),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def listar_historial_grupo(
        self, cursor, grupo_id: Any, limite: int = 50
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre,
                   oficio, descripcion, es_oficio_personalizado,
                   semana_inicio, estado, created_at, expira_at
            FROM solicitudes_semanales
            WHERE grupo_id = ? AND estado != 'activa'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (grupo_id, limite),
        )
        return [dict(r) for r in cursor.fetchall()]

    def insertar_respuesta(
        self,
        cursor,
        solicitud_id: int,
        aliado_codigo: str,
        aliado_nombre: str,
        tipo_respuesta: str,
        contacto_id: Optional[int] = None,
        invitacion_codigo: Optional[str] = None,
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO solicitudes_semanales_respuestas (
                solicitud_semanal_id, aliado_codigo, aliado_nombre,
                tipo_respuesta, contacto_id, invitacion_codigo
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(solicitud_id),
                aliado_codigo,
                aliado_nombre,
                tipo_respuesta,
                contacto_id,
                invitacion_codigo,
            ),
        )
        return cursor.lastrowid

    def select_respuesta(
        self, cursor, solicitud_id: int, aliado_codigo: str
    ) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, solicitud_semanal_id, aliado_codigo, aliado_nombre,
                   tipo_respuesta, contacto_id, invitacion_codigo, created_at
            FROM solicitudes_semanales_respuestas
            WHERE solicitud_semanal_id = ? AND aliado_codigo = ?
            """,
            (int(solicitud_id), aliado_codigo),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def listar_respuestas_por_solicitud(
        self, cursor, solicitud_id: int, tipo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if tipo:
            cursor.execute(
                """
                SELECT id, solicitud_semanal_id, aliado_codigo, aliado_nombre,
                       tipo_respuesta, contacto_id, invitacion_codigo, created_at
                FROM solicitudes_semanales_respuestas
                WHERE solicitud_semanal_id = ? AND tipo_respuesta = ?
                ORDER BY created_at ASC
                """,
                (int(solicitud_id), tipo),
            )
        else:
            cursor.execute(
                """
                SELECT id, solicitud_semanal_id, aliado_codigo, aliado_nombre,
                       tipo_respuesta, contacto_id, invitacion_codigo, created_at
                FROM solicitudes_semanales_respuestas
                WHERE solicitud_semanal_id = ?
                ORDER BY created_at ASC
                """,
                (int(solicitud_id),),
            )
        return [dict(r) for r in cursor.fetchall()]

    def contar_respuestas_tipo(
        self, cursor, solicitud_id: int, tipo: str
    ) -> int:
        cursor.execute(
            """
            SELECT COUNT(*) FROM solicitudes_semanales_respuestas
            WHERE solicitud_semanal_id = ? AND tipo_respuesta = ?
            """,
            (int(solicitud_id), tipo),
        )
        return cursor.fetchone()[0] or 0

    def contar_interesados(self, cursor, solicitud_id: int) -> int:
        return self.contar_respuestas_tipo(cursor, solicitud_id, "puedo_ayudar")

    def contar_recomendaciones(self, cursor, solicitud_id: int) -> int:
        return self.contar_respuestas_tipo(cursor, solicitud_id, "conozco_alguien")

    def listar_oficios_grupo_activos(self, cursor, grupo_id: Any) -> List[str]:
        cursor.execute(
            """
            SELECT DISTINCT oficio FROM aliados
            WHERE grupo_id = ? AND estado = 'activo' AND oficio IS NOT NULL AND TRIM(oficio) != ''
            ORDER BY oficio
            """,
            (grupo_id,),
        )
        return [r[0].strip() for r in cursor.fetchall() if r[0]]

    def listar_codigos_activos_grupo(
        self, cursor, grupo_id: Any, excluir_codigo: Optional[str] = None
    ) -> List[str]:
        if excluir_codigo:
            cursor.execute(
                """
                SELECT codigo FROM aliados
                WHERE grupo_id = ? AND estado = 'activo' AND codigo != ?
                ORDER BY nombre
                """,
                (grupo_id, excluir_codigo),
            )
        else:
            cursor.execute(
                """
                SELECT codigo FROM aliados
                WHERE grupo_id = ? AND estado = 'activo'
                ORDER BY nombre
                """,
                (grupo_id,),
            )
        return [str(r[0]).strip() for r in cursor.fetchall() if r[0]]

    def listar_todas_admin(self, cursor, limite: int = 300) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre,
                   s.oficio, s.descripcion, s.es_oficio_personalizado,
                   s.semana_inicio, s.estado, s.created_at, s.expira_at,
                   g.nombre AS grupo_nombre
            FROM solicitudes_semanales s
            LEFT JOIN grupos g ON g.id = s.grupo_id
            ORDER BY s.semana_inicio DESC, s.created_at DESC
            LIMIT ?
            """,
            (int(limite),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_respuestas_para_ids(
        self, cursor, solicitud_ids: List[int]
    ) -> List[Dict[str, Any]]:
        ids = [int(i) for i in (solicitud_ids or []) if i is not None]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        cursor.execute(
            f"""
            SELECT solicitud_semanal_id, aliado_codigo, aliado_nombre,
                   tipo_respuesta, contacto_id, invitacion_codigo, created_at
            FROM solicitudes_semanales_respuestas
            WHERE solicitud_semanal_id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            tuple(ids),
        )
        return [dict(r) for r in cursor.fetchall()]
