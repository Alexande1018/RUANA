"""
Repositorio de Chat (Campamento Base).

Acceso a datos de chat_mensajes, ruana_soporte_* y lecturas de contactos
ligadas al chat. Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional


class ChatRepo:
    """Operaciones de persistencia del dominio chat."""

    def conversacion_soporte_visible_aliado(
        self, cursor, conversacion_id: int, codigo: str
    ) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM ruana_soporte_conversaciones
            WHERE id = ? AND TRIM(CAST(aliado_codigo AS TEXT)) = ? AND COALESCE(eliminada_por_aliado, 0) = 0
            """,
            (int(conversacion_id), codigo),
        )
        return cursor.fetchone() is not None

    def select_id_conversacion_soporte_aliado(
        self, cursor, conversacion_id: int, codigo: str
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id FROM ruana_soporte_conversaciones
            WHERE id = ? AND TRIM(CAST(aliado_codigo AS TEXT)) = ? AND COALESCE(eliminada_por_aliado, 0) = 0
            """,
            (int(conversacion_id), codigo),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def listar_mensajes_soporte(self, cursor, conversacion_id: int) -> List[Any]:
        cursor.execute(
            """
            SELECT id, conversacion_id, emisor_tipo, emisor_codigo, mensaje, creado_en, leido_por_aliado, leido_por_admin
            FROM ruana_soporte_mensajes
            WHERE conversacion_id = ?
            ORDER BY creado_en ASC, id ASC
            """,
            (int(conversacion_id),),
        )
        return cursor.fetchall()

    def insertar_mensaje_soporte_aliado(
        self, cursor, conversacion_id: int, codigo: str, msg: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO ruana_soporte_mensajes
                (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
            VALUES (?, 'aliado', ?, ?, 1, 0)
            """,
            (int(conversacion_id), codigo, msg),
        )

    def update_conversacion_tras_mensaje_aliado(
        self, cursor, preview: str, conversacion_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE ruana_soporte_conversaciones
            SET estado = CASE WHEN estado = 'cerrado' THEN 'reabierto' ELSE estado END,
                ultimo_mensaje_preview = ?, ultimo_mensaje_en = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP,
                tiene_no_leido_admin = 1, tiene_no_leido_aliado = 0
            WHERE id = ?
            """,
            (preview, int(conversacion_id)),
        )

    def listar_mensajes_contacto(self, cursor, contacto_id: int) -> List[Any]:
        cursor.execute(
            """
            SELECT m.id, m.contacto_id, m.emisor_codigo, m.texto, m.creado_en,
                   COALESCE(a.nombre, m.emisor_codigo) AS emisor_nombre
            FROM chat_mensajes m
            LEFT JOIN aliados a ON a.codigo = m.emisor_codigo
            WHERE m.contacto_id = ?
            ORDER BY m.creado_en ASC
            """,
            (contacto_id,),
        )
        return cursor.fetchall()

    def max_creado_en_mensajes(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT MAX(creado_en) FROM chat_mensajes WHERE contacto_id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        return (row[0] if row else None)

    def select_fechas_contacto(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT fecha_aceptacion, creado_en FROM contactos_ruana WHERE id = ?",
            (contacto_id,),
        )
        return cursor.fetchone()

    def select_contacto_id_estado(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, estado FROM contactos_ruana WHERE id = ?",
            (contacto_id,),
        )
        return cursor.fetchone()

    def contar_mensajes(self, cursor, contacto_id: int) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM chat_mensajes WHERE contacto_id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        return (row[0] if row else 0) or 0

    def select_contacto_chat(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, solicitante_codigo, profesional_codigo, estado FROM contactos_ruana WHERE id = ?",
            (contacto_id,),
        )
        return cursor.fetchone()

    def columnas_chat_mensajes(self, cursor) -> List[str]:
        cursor.execute("PRAGMA table_info(chat_mensajes)")
        return [r[1] for r in cursor.fetchall()]

    def insertar_mensaje_con_receptor(
        self,
        cursor,
        contacto_id: int,
        emisor_norm: str,
        receptor_codigo: Optional[str],
        texto_clean: str,
    ) -> Any:
        cursor.execute(
            "INSERT INTO chat_mensajes (contacto_id, emisor_codigo, receptor_codigo, texto) VALUES (?, ?, ?, ?)",
            (contacto_id, emisor_norm, receptor_codigo or None, texto_clean),
        )
        return cursor.lastrowid

    def insertar_mensaje_sin_receptor(
        self,
        cursor,
        contacto_id: int,
        emisor_norm: str,
        texto_clean: str,
    ) -> Any:
        cursor.execute(
            "INSERT INTO chat_mensajes (contacto_id, emisor_codigo, texto) VALUES (?, ?, ?)",
            (contacto_id, emisor_norm, texto_clean),
        )
        return cursor.lastrowid

    def update_contacto_chat_agotado(self, cursor, contacto_id: int) -> int:
        cursor.execute(
            """UPDATE contactos_ruana SET estado = 'chat_agotado', actualizado_en = CURRENT_TIMESTAMP
               WHERE id = ? AND estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso', 'en_conversacion')""",
            (contacto_id,),
        )
        return cursor.rowcount or 0

    def select_mensaje_por_id(self, cursor, msg_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, contacto_id, emisor_codigo, texto, creado_en FROM chat_mensajes WHERE id = ?",
            (msg_id,),
        )
        return cursor.fetchone()

    def columnas_contactos_ruana(self, cursor) -> List[str]:
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        return [r[1] for r in cursor.fetchall()]

    def listar_contactos_recientes_con_chat(
        self, cursor, motivo_col: str, urgente_col: str, limite: int
    ) -> List[Any]:
        cursor.execute(
            f"""
            SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio, c.estado, c.creado_en,
                   c.fecha_cierre, c.fecha_no_concretado, c.importe_final, c.comision, {motivo_col}{urgente_col}
                   (SELECT COUNT(*) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS num_mensajes,
                   (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS ultimo_mensaje_en
            FROM contactos_ruana c
            ORDER BY c.creado_en DESC
            LIMIT ?
            """,
            (limite,),
        )
        return cursor.fetchall()

    def listar_chat_messages_admin(
        self, cursor, limit: int, offset: int
    ) -> List[Any]:
        cursor.execute(
            """
            SELECT cm.id, cm.texto AS content, cm.creado_en AS created_at,
                   s.codigo AS sender_codigo, s.nombre AS sender_nombre,
                   r.codigo AS receiver_codigo, r.nombre AS receiver_nombre
            FROM chat_mensajes cm
            JOIN contactos_ruana c ON c.id = cm.contacto_id
            JOIN aliados s ON s.codigo = cm.emisor_codigo
            LEFT JOIN aliados r ON r.codigo = (
                CASE WHEN cm.emisor_codigo = c.solicitante_codigo THEN c.profesional_codigo
                     ELSE c.solicitante_codigo END
            )
            ORDER BY cm.creado_en DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return cursor.fetchall()
