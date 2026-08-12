"""
Repositorio de Pagos / Apoyo RUANA (Campamento Base).

Acceso a datos de payment_conflicts, contactos_ruana (estado_pago / disputa)
e ingresos_ruana. Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, List, Optional


class PagoRepo:
    """Operaciones de persistencia del dominio pago."""

    def tabla_payment_conflicts_existe(self, cursor) -> bool:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'"
        )
        return cursor.fetchone() is not None

    def select_aliado_id_por_codigo(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
        return row[0] if row else None

    def select_qr_bizum_aliado(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute(
            "SELECT qr_paypal_path, bizum_num FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone()

    def listar_contactos_conflicto_pago(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT id, solicitante_codigo, profesional_codigo, servicio,
                   importe_solicitante, importe_profesional, comprobante_ruta,
                   estado, fecha_disputa, creado_en
            FROM contactos_ruana
            WHERE estado = 'importe_en_disputa'
              AND importe_solicitante IS NOT NULL AND importe_profesional IS NOT NULL
              AND importe_solicitante != importe_profesional
            ORDER BY fecha_disputa DESC, id DESC
            """
        )
        return cursor.fetchall()

    def listar_payment_conflicts_admin(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT pc.id, pc.trabajo_id, pc.contratante_id, pc.profesional_id,
                   pc.importe_contratante, pc.importe_profesional, pc.estado,
                   pc.prueba_url, pc.comentario_admin, pc.created_at, pc.updated_at,
                   a_cont.nombre AS contratante_nombre, a_cont.codigo AS contratante_codigo,
                   a_prof.nombre AS profesional_nombre, a_prof.codigo AS profesional_codigo
            FROM payment_conflicts pc
            JOIN aliados a_cont ON a_cont.id = pc.contratante_id
            JOIN aliados a_prof ON a_prof.id = pc.profesional_id
            WHERE pc.estado IN ('PENDIENTE_PRUEBA', 'EN_REVISION')
            ORDER BY pc.created_at DESC
            """
        )
        return cursor.fetchall()

    def select_conflict_por_trabajo_y_aliado(
        self, cursor, trabajo_id: int, aliado_id: int
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, trabajo_id, contratante_id, profesional_id, importe_contratante, importe_profesional,
                   estado, prueba_url, comentario_admin, created_at, updated_at
            FROM payment_conflicts
            WHERE trabajo_id = ? AND (contratante_id = ? OR profesional_id = ?)
            """,
            (trabajo_id, aliado_id, aliado_id),
        )
        return cursor.fetchone()

    def select_conflict_detalle(self, cursor, conflict_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT pc.id, pc.trabajo_id, pc.contratante_id, pc.profesional_id,
                   pc.importe_contratante, pc.importe_profesional, pc.estado,
                   pc.prueba_url, pc.comentario_admin, pc.created_at, pc.updated_at,
                   a_cont.nombre AS contratante_nombre, a_cont.codigo AS contratante_codigo,
                   a_prof.nombre AS profesional_nombre, a_prof.codigo AS profesional_codigo
            FROM payment_conflicts pc
            JOIN aliados a_cont ON a_cont.id = pc.contratante_id
            JOIN aliados a_prof ON a_prof.id = pc.profesional_id
            WHERE pc.id = ?
            """,
            (conflict_id,),
        )
        return cursor.fetchone()

    def select_conflict_basico(self, cursor, conflict_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, trabajo_id, importe_contratante, importe_profesional, estado
            FROM payment_conflicts WHERE id = ?
            """,
            (conflict_id,),
        )
        return cursor.fetchone()

    def update_conflict_resuelto(
        self, cursor, nuevo_estado: str, comentario: str, conflict_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE payment_conflicts SET estado = ?, comentario_admin = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (nuevo_estado, comentario, conflict_id),
        )

    def select_contacto_partes(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id, solicitante_codigo, profesional_codigo, estado FROM contactos_ruana WHERE id = ?",
            (contacto_id,),
        )
        return cursor.fetchone()

    def update_contacto_cerrar_disputa(
        self,
        cursor,
        importe_valido: float,
        apoyo: float,
        comision_pct: float,
        estado_pago_final: str,
        pendiente_pago_final: int,
        trabajo_id: int,
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'trabajo_cerrado', pendiente_resolucion = 0,
                importe_final = ?, comision = ?, comision_porcentaje = ?,
                apoyo_ruana = ?, estado_pago = ?, pendiente_pago = ?,
                fecha_cierre = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                importe_valido,
                apoyo,
                comision_pct,
                apoyo,
                estado_pago_final,
                pendiente_pago_final,
                trabajo_id,
            ),
        )

    def insertar_ingreso_ruana(
        self, cursor, contacto_id: int, importe_final: float, apoyo: float
    ) -> None:
        cursor.execute(
            "INSERT INTO ingresos_ruana (contacto_id, importe_final, apoyo_ruana_2pct) VALUES (?, ?, ?)",
            (contacto_id, importe_final, apoyo),
        )

    def insertar_notif_apoyo(
        self, cursor, prof_codigo: str, mensaje: str, meta: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, 'apoyo_ruana', 'Apoyo a RUANA', ?, ?, 0)
            """,
            (prof_codigo, mensaje, meta),
        )

    def update_contacto_resolver_conflicto(
        self,
        cursor,
        imp: float,
        apoyo: float,
        comision_pct: float,
        contacto_id: int,
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'trabajo_cerrado', pendiente_resolucion = 0,
                importe_final = ?, comision = ?, comision_porcentaje = ?,
                apoyo_ruana = ?, estado_pago = 'pendiente_pago', pendiente_pago = 1,
                fecha_cierre = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (imp, apoyo, comision_pct, apoyo, contacto_id),
        )

    def listar_contactos_pagos_apoyo(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio,
                   c.importe_final, c.apoyo_ruana, c.estado_pago, c.pendiente_pago, c.fecha_cierre,
                   c.comprobante_ruta,
                   COALESCE(c.es_urgente, 0) AS es_urgente, c.urgente_marcado_en, c.creado_en,
                   a_sol.nombre AS solicitante_nombre, a_prof.nombre AS profesional_nombre
            FROM contactos_ruana c
            LEFT JOIN aliados a_sol ON a_sol.codigo = c.solicitante_codigo
            LEFT JOIN aliados a_prof ON a_prof.codigo = c.profesional_codigo
            WHERE c.estado = 'trabajo_cerrado' AND c.importe_final IS NOT NULL
              AND COALESCE(c.apoyo_ruana, 0) > 0
            ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
            """
        )
        return cursor.fetchall()

    def listar_contactos_pagos_en_revision(self, cursor) -> List[Any]:
        cursor.execute(
            """
            SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio,
                   c.importe_final, c.apoyo_ruana, c.estado_pago, c.comprobante_ruta, c.fecha_cierre,
                   a_prof.nombre AS profesional_nombre
            FROM contactos_ruana c
            LEFT JOIN aliados a_prof ON a_prof.codigo = c.profesional_codigo
            WHERE c.estado = 'trabajo_cerrado' AND c.importe_final IS NOT NULL
              AND c.estado_pago = 'en_revision'
              AND COALESCE(c.apoyo_ruana, 0) > 0
            ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
            """
        )
        return cursor.fetchall()

    def select_contacto_estado_pago(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, estado, importe_final, estado_pago, pendiente_pago,
                   solicitante_codigo, profesional_codigo
            FROM contactos_ruana WHERE id = ?
            """,
            (contacto_id,),
        )
        return cursor.fetchone()

    def update_estado_pago_pagado(
        self, cursor, admin_codigo: Optional[str], contacto_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado_pago = 'pagado', pendiente_pago = 0,
                fecha_validacion_pago = CURRENT_TIMESTAMP,
                admin_validacion_codigo = ?,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (admin_codigo or None, contacto_id),
        )

    def insertar_notif_pago_aceptado(
        self, cursor, prof_codigo: str, mensaje: str, meta: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, 'pago_aceptado', 'Pago aceptado', ?, ?, 1)
            """,
            (prof_codigo, mensaje, meta),
        )

    def update_estado_pago_rechazado(
        self, cursor, motivo: str, contacto_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado_pago = 'pendiente_pago', pendiente_pago = 1,
                motivo_rechazo_pago = ?, comprobante_ruta = NULL,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (motivo, contacto_id),
        )

    def insertar_notif_pago_rechazado(
        self, cursor, prof_codigo: str, mensaje: str, meta: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, 'pago_rechazado', 'Comprobante de pago rechazado', ?, ?, 0)
            """,
            (prof_codigo, mensaje, meta),
        )

    def update_estado_pago_generico(
        self, cursor, nuevo_estado: str, pendiente_pago: int, contacto_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado_pago = ?, pendiente_pago = ?,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (nuevo_estado, pendiente_pago, contacto_id),
        )

    def tiene_pagos_pendientes(self, cursor, codigo_profesional: str) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM contactos_ruana
            WHERE profesional_codigo = ? AND estado = 'trabajo_cerrado'
              AND importe_final IS NOT NULL AND estado_pago = 'pendiente_pago'
              AND COALESCE(apoyo_ruana, 0) > 0
            LIMIT 1
            """,
            (codigo_profesional,),
        )
        return cursor.fetchone() is not None

    def select_contacto_impugnar(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, solicitante_codigo, profesional_codigo, estado, importe_final,
                   estado_pago, pendiente_pago
            FROM contactos_ruana
            WHERE id = ?
            """,
            (contacto_id,),
        )
        return cursor.fetchone()

    def update_contacto_impugnar(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'importe_en_disputa', pendiente_resolucion = 1,
                estado_pago = 'no_generado', pendiente_pago = 0,
                fecha_disputa = COALESCE(fecha_disputa, CURRENT_TIMESTAMP),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contacto_id,),
        )

    def select_conflict_id_por_trabajo(
        self, cursor, contacto_id: int
    ) -> Optional[Any]:
        cursor.execute(
            "SELECT id FROM payment_conflicts WHERE trabajo_id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def update_conflict_impugnacion(
        self,
        cursor,
        contratante_id: int,
        profesional_id: int,
        importe_final: float,
        comentario: Optional[str],
        conflict_id: int,
    ) -> None:
        cursor.execute(
            """
            UPDATE payment_conflicts
            SET contratante_id = ?, profesional_id = ?, importe_contratante = ?,
                importe_profesional = 0, estado = 'PENDIENTE_PRUEBA',
                prueba_url = NULL, comentario_admin = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contratante_id, profesional_id, importe_final, comentario, conflict_id),
        )

    def insertar_conflict_impugnacion(
        self,
        cursor,
        contacto_id: int,
        contratante_id: int,
        profesional_id: int,
        importe_final: float,
        comentario: Optional[str],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO payment_conflicts (trabajo_id, contratante_id, profesional_id,
                importe_contratante, importe_profesional, estado, comentario_admin,
                created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, 'PENDIENTE_PRUEBA', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (contacto_id, contratante_id, profesional_id, importe_final, comentario),
        )

    def insertar_notif_importe_impugnado(
        self, cursor, solicitante_codigo: str, mensaje: str, meta: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, 'importe_impugnado', 'Importe impugnado', ?, ?, 0)
            """,
            (solicitante_codigo, mensaje, meta),
        )

    def listar_pago_pendiente_profesional(self, cursor, codigo_norm: str) -> List[Any]:
        cursor.execute(
            """
            SELECT c.id, c.servicio, c.importe_final, c.apoyo_ruana, c.estado_pago, c.pendiente_pago,
                   c.fecha_cierre, c.solicitante_codigo,
                   a_sol.nombre AS solicitante_nombre
            FROM contactos_ruana c
            LEFT JOIN aliados a_sol ON a_sol.codigo = c.solicitante_codigo
            WHERE TRIM(CAST(c.profesional_codigo AS TEXT)) = ? AND c.estado = 'trabajo_cerrado'
              AND c.importe_final IS NOT NULL AND c.estado_pago = 'pendiente_pago'
              AND COALESCE(c.apoyo_ruana, 0) > 0
            ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
            """,
            (codigo_norm,),
        )
        return cursor.fetchall()

    def select_contacto_comprobante(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, profesional_codigo, estado_pago, apoyo_ruana
            FROM contactos_ruana
            WHERE id = ? AND estado = 'trabajo_cerrado' AND importe_final IS NOT NULL
            """,
            (contacto_id,),
        )
        return cursor.fetchone()

    def update_comprobante_en_revision(
        self, cursor, comprobante_ruta: str, contacto_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET comprobante_ruta = ?, estado_pago = 'en_revision', actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (comprobante_ruta, contacto_id),
        )

    def select_conflict_para_prueba(self, cursor, conflict_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT pc.id, pc.trabajo_id, pc.contratante_id, a.codigo AS contratante_codigo
            FROM payment_conflicts pc
            JOIN aliados a ON a.id = pc.contratante_id
            WHERE pc.id = ?
            """,
            (conflict_id,),
        )
        return cursor.fetchone()

    def update_conflict_prueba(
        self, cursor, prueba_url: str, conflict_id: int
    ) -> None:
        cursor.execute(
            """
            UPDATE payment_conflicts SET estado = 'EN_REVISION', prueba_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (prueba_url, conflict_id),
        )

    def insertar_notif_prueba_revision(
        self, cursor, contratante_norm: str, mensaje: str, meta: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, 'prueba_conflicto_en_revision', 'Documentacion en revision', ?, ?, 0)
            """,
            (contratante_norm, mensaje, meta),
        )
