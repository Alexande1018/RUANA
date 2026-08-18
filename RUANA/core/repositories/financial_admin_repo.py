"""Repositorio de consultas del panel administrativo financiero (FASE 09)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


class FinancialAdminRepo:
    MAX_LIMIT = 200
    DEFAULT_LIMIT = 50

    def clamp_pagination(self, limit: int, offset: int) -> Tuple[int, int]:
        lim = max(1, min(int(limit or self.DEFAULT_LIMIT), self.MAX_LIMIT))
        off = max(0, int(offset or 0))
        return lim, off

    def tabla_existe(self, cursor, nombre: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (nombre,),
        )
        return cursor.fetchone() is not None

    def count_query(self, cursor, sql: str, params: tuple = ()) -> int:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def dashboard_kpis(self, cursor) -> Dict[str, Any]:
        kpis: Dict[str, Any] = {}
        if self.tabla_existe(cursor, "contactos_ruana"):
            kpis["pagos_pendientes"] = self.count_query(
                cursor,
                """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE modo_pago = 'stripe'
                  AND estado_financiero IN ('PAGO_PENDIENTE', 'PAGO_NO_INICIADO')
                """,
            )
            kpis["pagos_confirmados"] = self.count_query(
                cursor,
                """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE modo_pago = 'stripe'
                  AND estado_financiero NOT IN ('PAGO_PENDIENTE', 'PAGO_NO_INICIADO', 'PAGO_FALLIDO', 'PAGO_CANCELADO')
                """,
            )
            kpis["transferencias_revertidas"] = self.count_query(
                cursor,
                "SELECT COUNT(*) FROM contactos_ruana WHERE estado_financiero = 'TRANSFERENCIA_REVERTIDA'",
            )
            kpis["operaciones_bloqueadas"] = self.count_query(
                cursor,
                """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE estado_financiero IN ('CONFLICTO_ABIERTO', 'DISPUTA_STRIPE', 'REEMBOLSO_PENDIENTE')
                """,
            )
            cursor.execute(
                """
                SELECT COALESCE(SUM(CAST(ROUND(importe_acordado * 100) AS INTEGER)), 0)
                FROM contactos_ruana
                WHERE modo_pago = 'stripe' AND estado_transferencia = 'RETENIDO'
                """
            )
            row = cursor.fetchone()
            kpis["dinero_retenido_cents"] = int(row[0] if row else 0)
            cursor.execute(
                """
                SELECT COALESCE(SUM(CAST(ROUND(importe_neto_profesional * 100) AS INTEGER)), 0)
                FROM contactos_ruana WHERE estado_financiero = 'TRANSFERIDO'
                """
            )
            row = cursor.fetchone()
            kpis["dinero_transferido_cents"] = int(row[0] if row else 0)
        if self.tabla_existe(cursor, "financial_refunds"):
            kpis["refunds_pendientes"] = self.count_query(
                cursor,
                "SELECT COUNT(*) FROM financial_refunds WHERE estado IN ('REQUESTED', 'STRIPE_PROCESSING', 'PENDING_RECONCILIATION')",
            )
            kpis["refunds_fallidos"] = self.count_query(
                cursor, "SELECT COUNT(*) FROM financial_refunds WHERE estado = 'FAILED'",
            )
        if self.tabla_existe(cursor, "financial_disputes"):
            kpis["disputas_abiertas"] = self.count_query(
                cursor,
                "SELECT COUNT(*) FROM financial_disputes WHERE estado_interno IN ('ABIERTO', 'EN_INVESTIGACION', 'PENDIENTE_EVIDENCIA')",
            )
        if self.tabla_existe(cursor, "payment_conflicts"):
            kpis["conflictos_abiertos"] = self.count_query(
                cursor,
                "SELECT COUNT(*) FROM payment_conflicts WHERE estado_conflicto NOT IN ('CERRADO', 'RESUELTO')",
            )
        if self.tabla_existe(cursor, "financial_reconciliation"):
            kpis["discrepancias_abiertas"] = self.count_query(
                cursor,
                "SELECT COUNT(*) FROM financial_reconciliation WHERE estado_reconciliacion = 'open'",
            )
        if self.tabla_existe(cursor, "stripe_webhook_events"):
            cols = {c[1] for c in cursor.execute("PRAGMA table_info(stripe_webhook_events)").fetchall()}
            if "procesado" in cols:
                wh_sql = "procesado = 0 OR estado = 'error'"
            elif "estado_procesamiento" in cols:
                wh_sql = "estado_procesamiento != 'completed' OR error_message IS NOT NULL"
            else:
                wh_sql = "resultado IS NOT NULL AND resultado != 'ok'"
            kpis["webhooks_fallidos"] = self.count_query(
                cursor, f"SELECT COUNT(*) FROM stripe_webhook_events WHERE {wh_sql}",
            )
        if self.tabla_existe(cursor, "ledger_transactions"):
            kpis["ledger_tx_posted"] = self.count_query(
                cursor, "SELECT COUNT(*) FROM ledger_transactions WHERE estado = 'POSTED'",
            )
        return kpis

    def listar_pagos(
        self, cursor, *, limit: int, offset: int,
        estado: str = "", contacto_id: Optional[int] = None, q: str = "",
    ) -> List[Dict[str, Any]]:
        lim, off = self.clamp_pagination(limit, offset)
        where = ["modo_pago = 'stripe'"]
        params: list = []
        if estado:
            where.append("estado_financiero = ?")
            params.append(estado)
        if contacto_id:
            where.append("id = ?")
            params.append(contacto_id)
        if q:
            where.append("(stripe_payment_intent_id LIKE ? OR stripe_charge_id LIKE ? OR CAST(id AS TEXT) = ?)")
            params.extend([f"%{q}%", f"%{q}%", q])
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, estado_financiero, estado_transferencia, importe_acordado,
                   stripe_payment_intent_id, stripe_charge_id, stripe_transfer_id,
                   fecha_cobro_confirmado, actualizado_en
            FROM contactos_ruana
            WHERE {' AND '.join(where)}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def listar_transfers(self, cursor, *, limit: int, offset: int, estado: str = "", q: str = "") -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "financial_transfers"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        where = ["1=1"]
        params: list = []
        if estado:
            where.append("estado = ?")
            params.append(estado)
        if q:
            where.append("(stripe_transfer_id LIKE ? OR CAST(contacto_id AS TEXT) = ?)")
            params.extend([f"%{q}%", q])
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, contacto_id, stripe_transfer_id, amount_cents, currency, estado,
                   destination_account_id, reconciliacion_estado, creado_en, actualizado_en
            FROM financial_transfers
            WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def listar_refunds(self, cursor, *, limit: int, offset: int, estado: str = "", q: str = "") -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "financial_refunds"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        where = ["1=1"]
        params: list = []
        if estado:
            where.append("estado = ?")
            params.append(estado)
        if q:
            where.append("(stripe_refund_id LIKE ? OR CAST(contacto_id AS TEXT) = ?)")
            params.extend([f"%{q}%", q])
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, contacto_id, stripe_refund_id, importe_confirmado_cents, moneda,
                   estado, causa_ruana, creado_en, actualizado_en
            FROM financial_refunds
            WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def listar_disputes(self, cursor, *, limit: int, offset: int, estado: str = "", q: str = "") -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "financial_disputes"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        where = ["1=1"]
        params: list = []
        if estado:
            where.append("estado_interno = ?")
            params.append(estado)
        if q:
            where.append("(stripe_dispute_id LIKE ? OR CAST(contacto_id AS TEXT) = ?)")
            params.extend([f"%{q}%", q])
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, contacto_id, stripe_dispute_id, amount_cents, currency,
                   estado_interno, status_stripe, evidence_due_by, creado_en, actualizado_en
            FROM financial_disputes
            WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def listar_conflicts(self, cursor, *, limit: int, offset: int, estado: str = "", q: str = "") -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "payment_conflicts"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        where = ["1=1"]
        params: list = []
        if estado:
            where.append("estado_conflicto = ?")
            params.append(estado)
        if q:
            where.append("(CAST(trabajo_id AS TEXT) = ? OR stripe_payment_intent_id LIKE ?)")
            params.extend([q, f"%{q}%"])
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, trabajo_id, tipo, estado_conflicto, bloqueo_financiero,
                   responsable_codigo, stripe_payment_intent_id, created_at, updated_at
            FROM payment_conflicts
            WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def listar_audit(self, cursor, *, limit: int, offset: int, entidad: str = "", q: str = "") -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "audit_log"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        where = ["1=1"]
        params: list = []
        if entidad:
            where.append("entidad = ?")
            params.append(entidad)
        if q:
            where.append("(CAST(entidad_id AS TEXT) = ? OR accion LIKE ?)")
            params.extend([q, f"%{q}%"])
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, entidad, entidad_id, accion, actor_tipo, actor_codigo, detalles, created_at
            FROM audit_log
            WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def ultima_reconciliacion(self, cursor) -> Optional[str]:
        if not self.tabla_existe(cursor, "financial_reconciliation_executions"):
            return None
        cursor.execute(
            "SELECT MAX(COALESCE(finalizado_en, creado_en)) FROM financial_reconciliation_executions"
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def generar_alertas(self, cursor, *, limit: int = 100) -> List[Dict[str, Any]]:
        alertas: List[Dict[str, Any]] = []
        lim = max(1, min(int(limit or 100), self.MAX_LIMIT))

        if self.tabla_existe(cursor, "financial_reconciliation"):
            cursor.execute(
                """
                SELECT id, contacto_id, tipo_discrepancia, estado_reconciliacion, detected_at
                FROM financial_reconciliation
                WHERE estado_reconciliacion = 'open'
                ORDER BY detected_at ASC LIMIT ?
                """,
                (lim,),
            )
            for row in self._rows(cursor):
                key = f"discrepancia:{row.get('id')}"
                if self.alerta_resuelta(cursor, key):
                    continue
                alertas.append({
                    "alert_key": key,
                    "severidad": "critical",
                    "tipo": "discrepancia_stripe_ruana",
                    "contacto_id": row.get("contacto_id"),
                    "fecha": row.get("detected_at"),
                    "estado": "open",
                    "accion_recomendada": "Revisar reconciliación y resolver discrepancia",
                    "accion_disponible": "financial.reconciliation.resolve",
                    "fuente": "financial_reconciliation",
                })

        if self.tabla_existe(cursor, "financial_disputes"):
            cursor.execute(
                """
                SELECT id, contacto_id, stripe_dispute_id, estado_interno, evidence_due_by, creado_en
                FROM financial_disputes
                WHERE estado_interno IN ('ABIERTO', 'EN_INVESTIGACION', 'PENDIENTE_EVIDENCIA')
                ORDER BY evidence_due_by IS NULL, evidence_due_by ASC LIMIT ?
                """,
                (lim,),
            )
            for row in self._rows(cursor):
                key = f"disputa:{row.get('id')}"
                if self.alerta_resuelta(cursor, key):
                    continue
                alertas.append({
                    "alert_key": key,
                    "severidad": "high",
                    "tipo": "disputa_abierta",
                    "contacto_id": row.get("contacto_id"),
                    "fecha": row.get("creado_en"),
                    "estado": row.get("estado_interno"),
                    "accion_recomendada": "Investigar disputa y preparar evidencia",
                    "accion_disponible": "financial.dispute.investigate",
                    "fuente": "financial_disputes",
                    "deadline": row.get("evidence_due_by"),
                })

        if self.tabla_existe(cursor, "payment_conflicts"):
            cursor.execute(
                """
                SELECT id, trabajo_id, estado_conflicto, bloqueo_financiero, responsable_codigo, created_at
                FROM payment_conflicts
                WHERE bloqueo_financiero = 1
                  AND estado_conflicto NOT IN ('CERRADO', 'RESUELTO')
                ORDER BY created_at ASC LIMIT ?
                """,
                (lim,),
            )
            for row in self._rows(cursor):
                key = f"conflicto:{row.get('id')}"
                if self.alerta_resuelta(cursor, key):
                    continue
                alertas.append({
                    "alert_key": key,
                    "severidad": "critical",
                    "tipo": "conflicto_bloqueante",
                    "contacto_id": row.get("trabajo_id"),
                    "fecha": row.get("created_at"),
                    "estado": row.get("estado_conflicto"),
                    "responsable": row.get("responsable_codigo"),
                    "accion_recomendada": "Investigar y resolver conflicto financiero",
                    "accion_disponible": "financial.conflict.resolve",
                    "fuente": "payment_conflicts",
                })

        if self.tabla_existe(cursor, "stripe_webhook_events"):
            cols = {c[1] for c in cursor.execute("PRAGMA table_info(stripe_webhook_events)").fetchall()}
            if "estado_procesamiento" in cols:
                wh = "estado_procesamiento != 'completed' OR error_message IS NOT NULL"
            elif "procesado" in cols:
                wh = "procesado = 0 OR estado = 'error'"
            else:
                wh = "resultado IS NOT NULL AND resultado != 'ok'"
            cursor.execute(
                f"""
                SELECT id, stripe_event_id, tipo, contacto_id, procesado_en, resultado
                FROM stripe_webhook_events
                WHERE {wh}
                ORDER BY id DESC LIMIT ?
                """,
                (lim,),
            )
            for row in self._rows(cursor):
                key = f"webhook:{row.get('id')}"
                if self.alerta_resuelta(cursor, key):
                    continue
                alertas.append({
                    "alert_key": key,
                    "severidad": "high",
                    "tipo": "webhook_fallido",
                    "contacto_id": None,
                    "fecha": row.get("creado_en"),
                    "estado": row.get("estado") or "pendiente",
                    "accion_recomendada": "Revisar evento webhook y reprocesar si procede",
                    "accion_disponible": None,
                    "fuente": "stripe_webhook_events",
                    "object_id": row.get("object_id"),
                })

        if self.tabla_existe(cursor, "contactos_ruana"):
            cursor.execute(
                """
                SELECT id, estado_financiero, actualizado_en
                FROM contactos_ruana
                WHERE modo_pago = 'stripe'
                  AND estado_financiero = 'TRANSFERENCIA_REVERTIDA'
                ORDER BY actualizado_en DESC LIMIT ?
                """,
                (lim,),
            )
            for row in self._rows(cursor):
                key = f"transfer_revertida:{row.get('id')}"
                if self.alerta_resuelta(cursor, key):
                    continue
                alertas.append({
                    "alert_key": key,
                    "severidad": "critical",
                    "tipo": "transferencia_revertida",
                    "contacto_id": row.get("id"),
                    "fecha": row.get("actualizado_en"),
                    "estado": row.get("estado_financiero"),
                    "accion_recomendada": "Investigar transferencia revertida",
                    "accion_disponible": "financial.reconciliation.execute",
                    "fuente": "contactos_ruana",
                })
            cursor.execute(
                """
                SELECT id, estado_financiero, actualizado_en
                FROM contactos_ruana
                WHERE modo_pago = 'stripe'
                  AND estado_financiero NOT IN ('PAGO_NO_INICIADO', 'PAGO_PENDIENTE')
                  AND (stripe_payment_intent_id IS NULL OR stripe_payment_intent_id = '')
                ORDER BY actualizado_en DESC LIMIT ?
                """,
                (lim,),
            )
            for row in self._rows(cursor):
                key = f"sin_pi:{row.get('id')}"
                if self.alerta_resuelta(cursor, key):
                    continue
                alertas.append({
                    "alert_key": key,
                    "severidad": "high",
                    "tipo": "operacion_sin_payment_intent",
                    "contacto_id": row.get("id"),
                    "fecha": row.get("actualizado_en"),
                    "estado": row.get("estado_financiero"),
                    "accion_recomendada": "Vincular PaymentIntent o reconciliar",
                    "accion_disponible": "financial.reconciliation.execute",
                    "fuente": "contactos_ruana",
                })

        if self.tabla_existe(cursor, "financial_reconciliation_executions"):
            cursor.execute(
                """
                SELECT id, contacto_id, estado, creado_en
                FROM financial_reconciliation_executions
                WHERE estado IN ('pending', 'running', 'PENDING', 'RUNNING')
                ORDER BY creado_en ASC LIMIT ?
                """,
                (lim,),
            )
            for row in self._rows(cursor):
                key = f"recon_pendiente:{row.get('id')}"
                if self.alerta_resuelta(cursor, key):
                    continue
                alertas.append({
                    "alert_key": key,
                    "severidad": "medium",
                    "tipo": "reconciliacion_pendiente",
                    "contacto_id": row.get("contacto_id"),
                    "fecha": row.get("creado_en"),
                    "estado": row.get("estado"),
                    "accion_recomendada": "Completar o resolver ejecución de reconciliación",
                    "accion_disponible": "financial.reconciliation.resolve",
                    "fuente": "financial_reconciliation_executions",
                })

        alertas.sort(key=lambda a: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.get("severidad", "low"), 9), str(a.get("fecha") or "")))
        return alertas[:lim]

    def listar_reconciliacion(self, cursor, *, limit: int, offset: int, estado: str = "") -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "financial_reconciliation_executions"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        where = ["1=1"]
        params: list = []
        if estado:
            where.append("estado = ?")
            params.append(estado)
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, contacto_id, payment_intent_id, transfer_id, operacion, estado,
                   reconciler_version, creado_en, finalizado_en
            FROM financial_reconciliation_executions
            WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def listar_ledger(self, cursor, *, limit: int, offset: int, estado: str = "") -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "ledger_transactions"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        where = ["1=1"]
        params: list = []
        if estado:
            where.append("estado = ?")
            params.append(estado)
        params.extend([lim, off])
        cursor.execute(
            f"""
            SELECT id, transaction_key, contacto_id, tipo, moneda, estado,
                   referencia_stripe, fecha_publicacion, creado_en
            FROM ledger_transactions
            WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return self._rows(cursor)

    def listar_webhooks(self, cursor, *, limit: int, offset: int, solo_fallidos: bool = False) -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor, "stripe_webhook_events"):
            return []
        lim, off = self.clamp_pagination(limit, offset)
        cols = {c[1] for c in cursor.execute("PRAGMA table_info(stripe_webhook_events)").fetchall()}
        select_cols = ["id", "stripe_event_id", "tipo", "contacto_id", "procesado_en", "resultado"]
        if "object_id" in cols:
            select_cols.insert(3, "object_id")
        if "estado_procesamiento" in cols:
            select_cols.append("estado_procesamiento")
        if "error_message" in cols:
            select_cols.append("error_message")
        where = ""
        if solo_fallidos:
            if "estado_procesamiento" in cols:
                where = "WHERE estado_procesamiento != 'completed' OR error_message IS NOT NULL"
            elif "procesado" in cols:
                where = "WHERE procesado = 0 OR estado = 'error'"
            else:
                where = "WHERE resultado IS NOT NULL AND resultado != 'ok'"
        cursor.execute(
            f"""
            SELECT {', '.join(select_cols)}
            FROM stripe_webhook_events {where}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (lim, off),
        )
        return self._rows(cursor)

    def operacion_detalle(self, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM contactos_ruana WHERE id = ?", (contacto_id,))
        row = cursor.fetchone()
        if not row:
            return None
        base = self._row_dict(row, cursor)
        detalle: Dict[str, Any] = {"contacto": base, "timeline": []}

        def _append(tipo: str, fecha, meta: Dict):
            detalle["timeline"].append({"tipo": tipo, "fecha": fecha, "meta": meta})

        if base.get("fecha_cobro_confirmado"):
            _append("pago_confirmado", base.get("fecha_cobro_confirmado"), {"pi": base.get("stripe_payment_intent_id")})
        if base.get("fecha_transferencia"):
            _append("transferencia", base.get("fecha_transferencia"), {"transfer": base.get("stripe_transfer_id")})

        if self.tabla_existe(cursor, "financial_transfers"):
            cursor.execute(
                "SELECT * FROM financial_transfers WHERE contacto_id = ? ORDER BY id DESC LIMIT 5",
                (contacto_id,),
            )
            detalle["transfers"] = self._rows(cursor)

        if self.tabla_existe(cursor, "financial_refunds"):
            cursor.execute(
                "SELECT * FROM financial_refunds WHERE contacto_id = ? ORDER BY id DESC LIMIT 20",
                (contacto_id,),
            )
            detalle["refunds"] = self._rows(cursor)

        if self.tabla_existe(cursor, "financial_disputes"):
            cursor.execute(
                "SELECT * FROM financial_disputes WHERE contacto_id = ? ORDER BY id DESC LIMIT 10",
                (contacto_id,),
            )
            detalle["disputes"] = self._rows(cursor)

        if self.tabla_existe(cursor, "payment_conflicts"):
            cursor.execute(
                "SELECT * FROM payment_conflicts WHERE trabajo_id = ? ORDER BY id DESC LIMIT 10",
                (contacto_id,),
            )
            detalle["conflicts"] = self._rows(cursor)

        if self.tabla_existe(cursor, "financial_reconciliation"):
            cursor.execute(
                "SELECT * FROM financial_reconciliation WHERE contacto_id = ? ORDER BY detected_at DESC LIMIT 20",
                (contacto_id,),
            )
            detalle["discrepancias"] = self._rows(cursor)

        if self.tabla_existe(cursor, "financial_reconciliation_executions"):
            cursor.execute(
                "SELECT * FROM financial_reconciliation_executions WHERE contacto_id = ? ORDER BY id DESC LIMIT 10",
                (contacto_id,),
            )
            detalle["reconciliaciones"] = self._rows(cursor)

        if self.tabla_existe(cursor, "ledger_transactions"):
            cursor.execute(
                "SELECT * FROM ledger_transactions WHERE contacto_id = ? ORDER BY id DESC LIMIT 30",
                (contacto_id,),
            )
            detalle["ledger"] = self._rows(cursor)

        if self.tabla_existe(cursor, "stripe_webhook_events") and base.get("stripe_payment_intent_id"):
            cursor.execute(
                """
                SELECT * FROM stripe_webhook_events
                WHERE object_id = ? OR object_id = ? OR object_id = ?
                ORDER BY id DESC LIMIT 30
                """,
                (
                    base.get("stripe_payment_intent_id"),
                    base.get("stripe_charge_id") or "",
                    base.get("stripe_transfer_id") or "",
                ),
            )
            detalle["webhooks"] = self._rows(cursor)

        detalle["timeline"].sort(key=lambda x: str(x.get("fecha") or ""))
        return detalle

    def registrar_alerta_resolucion(
        self, cursor, *, alert_key: str, contacto_id: Optional[int],
        motivo: str, actor: str, permiso: str,
    ) -> int:
        cursor.execute(
            """
            INSERT OR IGNORE INTO financial_admin_alert_actions (
                alert_key, contacto_id, accion, motivo, actor_codigo, permiso_usado
            ) VALUES (?, ?, 'resolved', ?, ?, ?)
            """,
            (alert_key, contacto_id, motivo, actor, permiso),
        )
        return int(cursor.lastrowid or 0)

    def alerta_resuelta(self, cursor, alert_key: str) -> bool:
        if not self.tabla_existe(cursor, "financial_admin_alert_actions"):
            return False
        cursor.execute(
            "SELECT 1 FROM financial_admin_alert_actions WHERE alert_key = ? AND accion = 'resolved' LIMIT 1",
            (alert_key,),
        )
        return cursor.fetchone() is not None

    def _rows(self, cursor) -> List[Dict[str, Any]]:
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def _row_dict(self, row, cursor) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            return dict(row)
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}
