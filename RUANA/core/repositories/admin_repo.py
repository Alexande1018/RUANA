"""
Repositorio de Admin (Campamento Base).

Acceso a datos de soporte, métricas, eventos_sistema y agregados del panel.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence


class AdminRepo:
    """Operaciones de persistencia del dominio admin / panel."""

    def insertar_invitador_admin(self, cursor, admin_codigo: str, nombre_final: str) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO aliados (codigo, nombre, marca, oficio, estado, score)
            VALUES (?, ?, 'RUANA', 'Administración', 'sistema', 0)
            """,
            (admin_codigo, nombre_final),
        )

    def listar_conversaciones_soporte(
        self, cursor, where_sql: str, params: Sequence[Any]
    ) -> List[Any]:
        cursor.execute(
            f"""
            SELECT c.id, c.aliado_codigo, a.nombre AS aliado_nombre, c.asunto, c.categoria, c.estado,
                   c.ultimo_mensaje_preview, c.ultimo_mensaje_en, c.tiene_no_leido_admin, c.tiene_no_leido_aliado,
                   c.creado_en, c.actualizado_en,
                   (SELECT COUNT(1) FROM ruana_soporte_mensajes m WHERE m.conversacion_id = c.id) AS total_mensajes
            FROM ruana_soporte_conversaciones c
            LEFT JOIN aliados a ON TRIM(CAST(a.codigo AS TEXT)) = TRIM(CAST(c.aliado_codigo AS TEXT))
            WHERE {where_sql}
            ORDER BY c.ultimo_mensaje_en DESC, c.id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )
        return cursor.fetchall()

    def select_soporte_aliado_codigo(self, cursor, conversacion_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT aliado_codigo FROM ruana_soporte_conversaciones WHERE id = ? AND COALESCE(eliminada_por_admin, 0) = 0",
            (int(conversacion_id),),
        )
        return cursor.fetchone()

    def update_estado_soporte(self, cursor, estado: str, conversacion_id: int) -> None:
        cursor.execute(
            """
            UPDATE ruana_soporte_conversaciones
            SET estado = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (estado, int(conversacion_id)),
        )

    def insertar_notif_estado_soporte(
        self, cursor, aliado_codigo: str, mensaje: str, metadata_json: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, 'ruana_soporte_estado', '✅ Estado de tu consulta actualizado', ?, ?, 0)
            """,
            (aliado_codigo, mensaje, metadata_json),
        )

    def soft_delete_soporte(self, cursor, conversacion_id: int) -> None:
        cursor.execute(
            """
            UPDATE ruana_soporte_conversaciones
            SET eliminada_por_admin = 1, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (int(conversacion_id),),
        )

    def listar_contactos_chats(self, cursor, limite: int, offset: int) -> List[Any]:
        cursor.execute(
            """
            SELECT c.id AS contacto_id,
                   c.creado_en AS contacto_creado_en,
                   COALESCE(sol.nombre, c.solicitante_codigo) AS solicitante,
                   COALESCE(prof.nombre, c.profesional_codigo) AS profesional,
                   c.solicitante_codigo,
                   c.profesional_codigo,
                   COALESCE(c.es_urgente, 0) AS es_urgente,
                   c.urgente_marcado_en,
                   c.motivo_contacto,
                   (SELECT m.texto FROM chat_mensajes m WHERE m.contacto_id = c.id ORDER BY m.creado_en DESC LIMIT 1) AS ultimo_mensaje,
                   (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS fecha_ultimo,
                   (SELECT COUNT(*) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS num_mensajes
            FROM contactos_ruana c
            LEFT JOIN aliados sol ON sol.codigo = c.solicitante_codigo
            LEFT JOIN aliados prof ON prof.codigo = c.profesional_codigo
            ORDER BY COALESCE((SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id), c.creado_en) DESC,
                     c.id DESC
            LIMIT ? OFFSET ?
            """,
            (limite, offset),
        )
        return cursor.fetchall()

    def listar_mensajes_contactos(self, cursor, ids: Sequence[Any]) -> List[Any]:
        placeholders = ",".join("?" * len(ids))
        cursor.execute(
            f"""
            SELECT m.id, m.contacto_id, m.emisor_codigo, m.texto, m.creado_en
            FROM chat_mensajes m
            WHERE m.contacto_id IS NOT NULL AND m.contacto_id IN ({placeholders})
            ORDER BY m.contacto_id, m.creado_en ASC
            """,
            list(ids),
        )
        return cursor.fetchall()

    def contar(self, cursor, sql: str, params: Sequence[Any] = ()) -> int:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def fetchall(self, cursor, sql: str, params: Sequence[Any] = ()) -> List[Any]:
        cursor.execute(sql, params)
        return cursor.fetchall()

    def fetchone(self, cursor, sql: str, params: Sequence[Any] = ()) -> Optional[Any]:
        cursor.execute(sql, params)
        return cursor.fetchone()

    def columnas_tabla(self, cursor, tabla: str) -> List[str]:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return [r[1] for r in cursor.fetchall()]

    def select_estados_profesional(self, cursor, codigo: str) -> List[Any]:
        cursor.execute(
            "SELECT estado FROM contactos_ruana WHERE profesional_codigo = ?",
            (codigo,),
        )
        return cursor.fetchall()

    def select_meses_sin_trabajo(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT (julianday('now', 'localtime') - julianday(MAX(fecha_cierre))) / 30.44 AS meses
            FROM contactos_ruana
            WHERE (profesional_codigo = ? OR solicitante_codigo = ?) AND estado = 'trabajo_cerrado' AND fecha_cierre IS NOT NULL
            """,
            (codigo, codigo),
        )
        return cursor.fetchone()

    def select_nombre_aliado(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute("SELECT nombre FROM aliados WHERE codigo = ?", (codigo or "",))
        return cursor.fetchone()

    def select_evento_reciente_idem(
        self, cursor, tipo: str, descripcion: str, actor_codigo: Optional[str]
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT creado_en FROM eventos_sistema
            WHERE tipo = ? AND descripcion = ?
              AND ((CAST(? AS TEXT) IS NULL AND actor_codigo IS NULL) OR (actor_codigo = ?))
            ORDER BY id DESC LIMIT 1
            """,
            (tipo, descripcion, actor_codigo, actor_codigo),
        )
        return cursor.fetchone()

    def insertar_evento_sistema(
        self,
        cursor,
        tipo: str,
        descripcion: str,
        actor_tipo: Optional[str],
        actor_codigo: Optional[str],
        meta_json: Optional[str],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO eventos_sistema (tipo, descripcion, actor_tipo, actor_codigo, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tipo, descripcion, actor_tipo, actor_codigo, meta_json),
        )

    def execute(self, cursor, *args) -> Any:
        """Ejecuta SQL del panel (agregados dinámicos / fallback)."""
        return cursor.execute(*args)

    def listar_eventos_recientes(self, cursor, limite: int) -> List[Any]:
        cursor.execute(
            """
            SELECT id, tipo, descripcion, actor_tipo, actor_codigo, metadata, creado_en
            FROM eventos_sistema
            ORDER BY datetime(creado_en) DESC, id DESC
            LIMIT ?
            """,
            (limite,),
        )
        return cursor.fetchall()
