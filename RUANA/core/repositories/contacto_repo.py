"""
Repositorio de Contacto RUANA.

Acceso a datos de contactos_ruana, contacto_panel_oculto, confirmaciones_trabajo
e ingresos/notificaciones ligados al ciclo de vida del contacto.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


class ContactoRepo:
    """Operaciones de persistencia del dominio contacto."""

    def columnas_contactos_ruana(self, cursor) -> List[str]:
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        return [row[1] for row in cursor.fetchall()]

    def existe_aliado(self, cursor, codigo: str) -> bool:
        cursor.execute("SELECT codigo FROM aliados WHERE codigo = ?", (codigo,))
        return cursor.fetchone() is not None

    def insertar_contacto_iniciado(
        self,
        cursor,
        solicitante_codigo: str,
        profesional_codigo: str,
        servicio: str,
        motivo_val: Optional[str],
        urgente_flag: int,
        tiene_motivo: bool,
        tiene_urgente: bool,
    ) -> Any:
        if tiene_motivo and tiene_urgente:
            cursor.execute(
                """
                INSERT INTO contactos_ruana (
                    solicitante_codigo, profesional_codigo, servicio, motivo_contacto,
                    es_urgente, urgente_marcado_en,
                    estado, pendiente_resolucion, contacto_externo_habilitado
                ) VALUES (?, ?, ?, ?, ?, CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END,
                          'iniciado', 1, 0)
                """,
                (
                    solicitante_codigo,
                    profesional_codigo,
                    servicio or "",
                    motivo_val,
                    urgente_flag,
                    urgente_flag,
                ),
            )
        elif tiene_motivo:
            cursor.execute(
                """
                INSERT INTO contactos_ruana (
                    solicitante_codigo, profesional_codigo, servicio, motivo_contacto,
                    estado, pendiente_resolucion, contacto_externo_habilitado
                ) VALUES (?, ?, ?, ?, 'iniciado', 1, 0)
                """,
                (solicitante_codigo, profesional_codigo, servicio or "", motivo_val),
            )
        else:
            cursor.execute(
                """
                INSERT INTO contactos_ruana (
                    solicitante_codigo, profesional_codigo, servicio,
                    estado, pendiente_resolucion, contacto_externo_habilitado
                ) VALUES (?, ?, ?, 'iniciado', 1, 0)
                """,
                (solicitante_codigo, profesional_codigo, servicio or ""),
            )
        return cursor.lastrowid

    def select_por_id(self, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM contactos_ruana WHERE id = ?", (contacto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def select_estado(self, cursor, contacto_id: int) -> Optional[str]:
        cursor.execute(
            "SELECT estado FROM contactos_ruana WHERE id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return row[0]

    def select_id_estado(self, cursor, contacto_id: int) -> Optional[Tuple[Any, Any]]:
        cursor.execute(
            "SELECT id, estado FROM contactos_ruana WHERE id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

    def select_para_cierre(self, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, estado, solicitante_codigo, profesional_codigo, importe_acordado
            FROM contactos_ruana WHERE id = ?
            """,
            (contacto_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def select_participantes(
        self, cursor, contacto_id: int
    ) -> Optional[Tuple[Any, Any, Any]]:
        cursor.execute(
            """
            SELECT id, solicitante_codigo, profesional_codigo
            FROM contactos_ruana WHERE id = ?
            """,
            (contacto_id,),
        )
        row = cursor.fetchone()
        return (row[0], row[1], row[2]) if row else None

    def update_aceptado(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'aceptado',
                contacto_externo_habilitado = 1,
                pendiente_resolucion = 1,
                fecha_aceptacion = CURRENT_TIMESTAMP,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contacto_id,),
        )

    def update_trabajo_en_progreso(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'trabajo_en_progreso',
                pendiente_resolucion = 1,
                fecha_trabajo_en_progreso = CURRENT_TIMESTAMP,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contacto_id,),
        )

    def update_cerrado_no_concretado(self, cursor, contacto_id: int) -> None:
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

    def update_en_conversacion(
        self, cursor, contacto_id: int, hasta: Optional[str] = None
    ) -> None:
        columnas = self.columnas_contactos_ruana(cursor)
        if "fecha_pospuesto_hasta" in columnas and hasta is not None:
            cursor.execute(
                """
                UPDATE contactos_ruana
                SET estado = 'en_conversacion',
                    posponer_recordatorio = 1,
                    fecha_pospuesto_hasta = ?,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (hasta, contacto_id),
            )
        else:
            cursor.execute(
                """
                UPDATE contactos_ruana
                SET estado = 'en_conversacion',
                    posponer_recordatorio = 1,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (contacto_id,),
            )

    def insertar_panel_oculto(
        self, cursor, contacto_id: int, codigo_aliado: str
    ) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO contacto_panel_oculto (contacto_id, codigo_aliado)
            VALUES (?, ?)
            """,
            (contacto_id, codigo_aliado),
        )

    def update_importe_acordado(
        self, cursor, contacto_id: int, importe_val: float
    ) -> None:
        cursor.execute(
            "UPDATE contactos_ruana SET importe_acordado = ? WHERE id = ?",
            (importe_val, contacto_id),
        )

    def existe_confirmacion_trabajo(
        self, cursor, contacto_id: int, aliado_id: Any
    ) -> bool:
        cursor.execute(
            "SELECT 1 FROM confirmaciones_trabajo WHERE contacto_id = ? AND aliado_id = ?",
            (contacto_id, aliado_id),
        )
        return cursor.fetchone() is not None

    def update_importe_solicitante(
        self,
        cursor,
        contacto_id: int,
        importe_val: float,
        moneda: str,
        usuario_str: str,
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET importe_solicitante = ?, importe_solicitante_moneda = ?,
                declarado_por_solicitante = ?, fecha_declaracion_solicitante = CURRENT_TIMESTAMP,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (importe_val, moneda, usuario_str, contacto_id),
        )

    def update_importe_profesional(
        self,
        cursor,
        contacto_id: int,
        importe_val: float,
        moneda: str,
        usuario_str: str,
    ) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET importe_profesional = ?, importe_profesional_moneda = ?,
                declarado_por_profesional = ?, fecha_declaracion_profesional = CURRENT_TIMESTAMP,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (importe_val, moneda, usuario_str, contacto_id),
        )

    def insertar_confirmacion_trabajo(
        self, cursor, contacto_id: int, aliado_id: Any, importe_val: float
    ) -> None:
        cursor.execute(
            """
            INSERT INTO confirmaciones_trabajo (contacto_id, aliado_id, importe_declarado)
            VALUES (?, ?, ?)
            """,
            (contacto_id, aliado_id, importe_val),
        )

    def update_trabajo_cerrado(
        self,
        cursor,
        contacto_id: int,
        importe_sol: Any,
        apoyo_ruana: float,
        comision_pct: float,
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
            (importe_sol, apoyo_ruana, comision_pct, apoyo_ruana, contacto_id),
        )

    def insertar_ingreso_ruana(
        self, cursor, contacto_id: int, importe_sol: Any, apoyo_ruana: float
    ) -> None:
        cursor.execute(
            "INSERT INTO ingresos_ruana (contacto_id, importe_final, apoyo_ruana_2pct) VALUES (?, ?, ?)",
            (contacto_id, importe_sol, apoyo_ruana),
        )

    def select_profesional_codigo(self, cursor, contacto_id: int) -> Optional[str]:
        cursor.execute(
            "SELECT profesional_codigo FROM contactos_ruana WHERE id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            return None
        return (row[0] or "").strip() if isinstance(row[0], str) else str(row[0] or "")

    def select_pago_aliado(
        self, cursor, codigo: str
    ) -> Tuple[Optional[str], Optional[str]]:
        cursor.execute(
            "SELECT qr_paypal_path, bizum_num FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        row = cursor.fetchone()
        qr_path = row[0] if row and row[0] else None
        bizum = row[1] if row and row[1] else None
        return qr_path, bizum

    def insertar_notificacion_apoyo(
        self, cursor, prof_codigo: str, mensaje: str, meta: str
    ) -> None:
        cursor.execute(
            """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, 'apoyo_ruana', 'Apoyo a RUANA', ?, ?, 0)
            """,
            (prof_codigo, mensaje, meta),
        )

    def update_importe_en_disputa(self, cursor, contacto_id: int) -> None:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado = 'importe_en_disputa', pendiente_resolucion = 1,
                importe_final = NULL, comision = NULL, estado_pago = 'no_generado',
                pendiente_pago = 0, fecha_disputa = COALESCE(fecha_disputa, CURRENT_TIMESTAMP),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (contacto_id,),
        )

    def insertar_payment_conflict_si_existe(
        self,
        cursor,
        contacto_id: int,
        solicitante_codigo: Any,
        profesional_codigo: Any,
        importe_sol: Any,
        importe_prof: Any,
    ) -> None:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'"
        )
        if not cursor.fetchone():
            return
        cursor.execute(
            "SELECT id FROM aliados WHERE codigo = ?", (solicitante_codigo,)
        )
        r_sol = cursor.fetchone()
        cursor.execute(
            "SELECT id FROM aliados WHERE codigo = ?", (profesional_codigo,)
        )
        r_prof = cursor.fetchone()
        if r_sol and r_prof:
            cursor.execute(
                """
                INSERT INTO payment_conflicts (trabajo_id, contratante_id, profesional_id,
                    importe_contratante, importe_profesional, estado, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'PENDIENTE_PRUEBA', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    contacto_id,
                    r_sol[0],
                    r_prof[0],
                    float(importe_sol),
                    float(importe_prof),
                ),
            )

    def select_contactos_abiertos(
        self,
        cursor,
        codigo_aliado: str,
        estados_abiertos: Sequence[str],
        posponer_sql: str,
    ) -> List[Dict[str, Any]]:
        placeholders = ",".join("?" for _ in estados_abiertos)
        columnas = self.columnas_contactos_ruana(cursor)
        pago_cols = ""
        if "modo_pago" in columnas:
            pago_cols += ", c.modo_pago"
        if "estado_pago" in columnas:
            pago_cols += ", c.estado_pago"
        if "precio_congelado" in columnas:
            pago_cols += ", COALESCE(c.precio_congelado, 0) AS precio_congelado"
        cursor.execute(
            f"""
            SELECT
                c.id,
                c.solicitante_codigo,
                c.profesional_codigo,
                c.servicio,
                c.estado,
                c.pendiente_resolucion,
                COALESCE(c.posponer_recordatorio, 0) AS posponer_recordatorio,
                c.fecha_pospuesto_hasta,
                c.fecha_aceptacion,
                c.fecha_trabajo_en_progreso,
                c.fecha_cierre,
                c.fecha_disputa,
                c.creado_en,
                c.actualizado_en,
                COALESCE(c.es_urgente, 0) AS es_urgente,
                c.urgente_marcado_en,
                c.motivo_contacto,
                c.negociacion_json,
                c.importe_acordado,
                c.acuerdo_resumen_json
                {pago_cols},
                (SELECT 1 FROM confirmaciones_trabajo ct
                 INNER JOIN aliados a ON a.id = ct.aliado_id
                 WHERE ct.contacto_id = c.id AND TRIM(CAST(a.codigo AS TEXT)) = ?) AS ya_declaraste_importe
            FROM contactos_ruana c
            WHERE (TRIM(COALESCE(c.solicitante_codigo, '')) = ? OR TRIM(COALESCE(c.profesional_codigo, '')) = ?)
              AND c.estado IN ({placeholders})
              AND ({posponer_sql})
              AND NOT EXISTS (
                  SELECT 1 FROM contacto_panel_oculto o
                  WHERE o.contacto_id = c.id AND TRIM(COALESCE(o.codigo_aliado, '')) = ?
              )
            ORDER BY c.actualizado_en DESC, c.creado_en DESC
            """,
            (codigo_aliado, codigo_aliado, codigo_aliado, *estados_abiertos, codigo_aliado),
        )
        return [dict(row) for row in cursor.fetchall()]

    def select_resumen(
        self, cursor, contacto_id: int
    ) -> Optional[Dict[str, Any]]:
        cols = self.columnas_contactos_ruana(cursor)
        motivo_col = ", motivo_contacto" if "motivo_contacto" in cols else ""
        apoyo_col = ", apoyo_ruana" if "apoyo_ruana" in cols else ""
        urgente_col = (
            ", COALESCE(es_urgente, 0) AS es_urgente, urgente_marcado_en"
            if "es_urgente" in cols
            else ""
        )
        neg_col = ", negociacion_json" if "negociacion_json" in cols else ""
        cursor.execute(
            f"""
            SELECT
                id, solicitante_codigo, profesional_codigo, servicio, estado,
                importe_final, comision, comision_porcentaje, estado_pago, pendiente_pago,
                fecha_cierre, fecha_no_concretado, creado_en, actualizado_en
                {apoyo_col}
                {motivo_col}
                {urgente_col}
                {neg_col}
            FROM contactos_ruana
            WHERE id = ?
            """,
            (contacto_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
