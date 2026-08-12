"""
Repositorio de Negociación (Campamento Base).

Acceso a datos de contactos_ruana (negociacion_json / acuerdos) y negociacion_eventos.
Sin reglas de negocio: solo lectura/escritura.
No incluye las reglas de negociacion_domain (antes negociacion_manager).
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

_COLS_TIMESTAMP_CONTACTO = frozenset({
    "cierre_confirmado_solicitante_en",
    "cierre_confirmado_profesional_en",
    "resumen_dismiss_solicitante_en",
    "resumen_dismiss_profesional_en",
})


class NegociacionRepo:
    """Operaciones de persistencia del dominio negociación."""

    def update_negociacion_json(self, cursor, neg_json: str, contacto_id: int) -> None:
        cursor.execute(
            "UPDATE contactos_ruana SET negociacion_json = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (neg_json, contacto_id),
        )

    def insertar_evento(
        self,
        cursor,
        contacto_id: int,
        tipo: str,
        campo: Optional[str],
        valor: Optional[str],
        emisor_codigo: Optional[str],
        mensaje: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO negociacion_eventos (contacto_id, tipo, campo, valor, emisor_codigo, mensaje)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (contacto_id, tipo, campo or None, valor or None, emisor_codigo or None, mensaje),
        )

    def select_contacto(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute("SELECT * FROM contactos_ruana WHERE id = ?", (contacto_id,))
        return cursor.fetchone()

    def listar_eventos(self, cursor, contacto_id: int) -> List[Any]:
        cursor.execute(
            """
            SELECT id, contacto_id, tipo, campo, valor, emisor_codigo, mensaje, creado_en
            FROM negociacion_eventos
            WHERE contacto_id = ?
            ORDER BY id ASC
            """,
            (contacto_id,),
        )
        return cursor.fetchall()

    def update_negociacion_json_y_estado(
        self, cursor, neg_json: str, estado: str, contacto_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET negociacion_json = ?, estado = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (neg_json, estado, contacto_id),
        )

    def set_fecha_trabajo_en_progreso_si_null(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            "UPDATE contactos_ruana SET fecha_trabajo_en_progreso = COALESCE(fecha_trabajo_en_progreso, CURRENT_TIMESTAMP) WHERE id = ?",
            (contacto_id,),
        )

    def update_acuerdo_completo(
        self,
        cursor,
        neg_json: str,
        nuevo_estado: str,
        resumen_json: str,
        importe_oficial: Any,
        contacto_id: int,
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET negociacion_json = ?, estado = ?,
                acuerdo_resumen_json = COALESCE(acuerdo_resumen_json, ?),
                acuerdo_alcanzado_en = COALESCE(acuerdo_alcanzado_en, CURRENT_TIMESTAMP),
                importe_acordado = COALESCE(importe_acordado, ?),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (neg_json, nuevo_estado, resumen_json, importe_oficial, contacto_id),
        )

    def set_timestamp_col(self, cursor, col: str, contacto_id: int) -> None:
        if col not in _COLS_TIMESTAMP_CONTACTO:
            raise ValueError(f"Columna no permitida: {col}")
        cursor.execute(
            f"""
            UPDATE contactos_ruana
            SET {col} = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contacto_id,),
        )

    def marcar_acuerdo_alcanzado(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'acuerdo_alcanzado',
                acuerdo_alcanzado_en = COALESCE(acuerdo_alcanzado_en, CURRENT_TIMESTAMP),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contacto_id,),
        )

    def set_acuerdo_resumen_si_vacio(
        self, cursor, resumen_json: str, contacto_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET acuerdo_resumen_json = ?,
                acuerdo_alcanzado_en = COALESCE(acuerdo_alcanzado_en, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (resumen_json, contacto_id),
        )

    def marcar_cerrado_no_concretado(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'cerrado_no_concretado',
                pendiente_resolucion = 0,
                fecha_no_concretado = CURRENT_TIMESTAMP,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contacto_id,),
        )

    def listar_admin(self, cursor, limite: int, offset: int) -> List[Any]:
        cursor.execute(
            """
            SELECT c.id AS contacto_id, c.solicitante_codigo, c.profesional_codigo,
                   c.servicio, c.estado, COALESCE(c.es_urgente, 0) AS es_urgente,
                   c.negociacion_json, c.creado_en, c.actualizado_en,
                   (SELECT mensaje FROM negociacion_eventos e
                    WHERE e.contacto_id = c.id ORDER BY e.id DESC LIMIT 1) AS ultimo_evento,
                   (SELECT creado_en FROM negociacion_eventos e
                    WHERE e.contacto_id = c.id ORDER BY e.id DESC LIMIT 1) AS fecha_ultimo,
                   (SELECT COUNT(*) FROM negociacion_eventos e WHERE e.contacto_id = c.id) AS num_eventos
            FROM contactos_ruana c
            WHERE EXISTS (SELECT 1 FROM negociacion_eventos e WHERE e.contacto_id = c.id)
              AND c.estado NOT IN ('cerrado_no_concretado', 'no_concretado', 'trabajo_cerrado')
            ORDER BY c.actualizado_en DESC
            LIMIT ? OFFSET ?
            """,
            (limite, offset),
        )
        return cursor.fetchall()

    def existe_contacto(self, cursor, contacto_id: int) -> bool:
        cursor.execute("SELECT id FROM contactos_ruana WHERE id = ?", (contacto_id,))
        return cursor.fetchone() is not None

    def delete_relacionados_por_contacto(self, cursor, tabla: str, contacto_id: int) -> None:
        cursor.execute(f"DELETE FROM {tabla} WHERE contacto_id = ?", (contacto_id,))

    def delete_notificaciones_contacto(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            "DELETE FROM notificaciones_aliado WHERE metadata LIKE ?",
            (f'%"contacto_id": {contacto_id}%',),
        )

    def delete_contacto(self, cursor, contacto_id: int) -> None:
        cursor.execute("DELETE FROM contactos_ruana WHERE id = ?", (contacto_id,))

    def listar_acuerdos_aliado(
        self, cursor, where_sql: str, params: Sequence[Any]
    ) -> List[Any]:
        fecha_ref_sql = (
            "COALESCE(acuerdo_alcanzado_en, fecha_cierre, actualizado_en, creado_en)"
        )
        cursor.execute(
            f"""
            SELECT id, solicitante_codigo, profesional_codigo, servicio, estado,
                   acuerdo_resumen_json, acuerdo_alcanzado_en, fecha_cierre,
                   importe_final, apoyo_ruana, creado_en, actualizado_en,
                   cierre_confirmado_solicitante_en, cierre_confirmado_profesional_en,
                   {fecha_ref_sql} AS fecha_referencia
            FROM contactos_ruana
            WHERE {where_sql}
            ORDER BY {fecha_ref_sql} DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return cursor.fetchall()

    def listar_resumenes_visibles(self, cursor, codigo: str) -> List[Any]:
        cursor.execute(
            """
            SELECT id, solicitante_codigo, profesional_codigo, servicio, estado,
                   acuerdo_resumen_json, acuerdo_alcanzado_en,
                   cierre_confirmado_solicitante_en, cierre_confirmado_profesional_en,
                   resumen_dismiss_solicitante_en, resumen_dismiss_profesional_en
            FROM contactos_ruana
            WHERE acuerdo_resumen_json IS NOT NULL
              AND TRIM(CAST(acuerdo_resumen_json AS TEXT)) != ''
              AND estado IN ('acuerdo_alcanzado', 'trabajo_cerrado')
              AND (
                (TRIM(CAST(solicitante_codigo AS TEXT)) = ? AND resumen_dismiss_solicitante_en IS NULL)
                OR (TRIM(CAST(profesional_codigo AS TEXT)) = ? AND resumen_dismiss_profesional_en IS NULL)
              )
            ORDER BY COALESCE(acuerdo_alcanzado_en, actualizado_en) DESC
            LIMIT 20
            """,
            (codigo, codigo),
        )
        return cursor.fetchall()
