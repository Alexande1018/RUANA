"""Repositorio de eventos webhook Stripe con reclamación atómica (FASE 02)."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


class StripeWebhookRepo:
    """Persistencia segura de eventos webhook Stripe."""

    def reclamar_evento(self, cursor, event_id: str, event_type: str) -> str:
        """
        Intenta reclamar un evento de forma atómica.

        Returns:
            'claimed' — este proceso debe procesarlo (nuevo o reintento tras failed).
            'duplicate_ok' — ya procesado correctamente (completed).
            'duplicate_processing' — otro proceso lo está procesando.
        """
        cursor.execute(
            """
            INSERT OR IGNORE INTO stripe_webhook_events (
                stripe_event_id, tipo, resultado, estado_procesamiento
            ) VALUES (?, ?, 'processing', 'processing')
            """,
            (event_id, event_type),
        )
        if cursor.rowcount > 0:
            return "claimed"

        cursor.execute(
            """
            UPDATE stripe_webhook_events
            SET resultado = 'processing',
                estado_procesamiento = 'processing',
                error_message = NULL,
                tipo = ?
            WHERE stripe_event_id = ?
              AND estado_procesamiento = 'failed'
            """,
            (event_type, event_id),
        )
        if cursor.rowcount > 0:
            return "claimed"

        cursor.execute(
            """
            SELECT resultado, estado_procesamiento
            FROM stripe_webhook_events
            WHERE stripe_event_id = ?
            """,
            (event_id,),
        )
        row = cursor.fetchone()
        if not row:
            return "duplicate_processing"
        resultado = row[0] if not hasattr(row, "keys") else row["resultado"]
        estado = row[1] if not hasattr(row, "keys") else row["estado_procesamiento"]
        if estado == "processing" or resultado == "processing":
            return "duplicate_processing"
        return "duplicate_ok"

    def finalizar_evento(
        self,
        cursor,
        event_id: str,
        resultado: str,
        *,
        contacto_id: Optional[int] = None,
        object_id: str = "",
        estado_anterior: str = "",
        estado_nuevo: str = "",
        error_message: str = "",
    ) -> None:
        cursor.execute(
            """
            UPDATE stripe_webhook_events
            SET resultado = ?, estado_procesamiento = 'completed',
                contacto_id = COALESCE(?, contacto_id),
                object_id = COALESCE(NULLIF(?, ''), object_id),
                estado_anterior = COALESCE(NULLIF(?, ''), estado_anterior),
                estado_nuevo = COALESCE(NULLIF(?, ''), estado_nuevo),
                error_message = COALESCE(NULLIF(?, ''), error_message),
                procesado_en = CURRENT_TIMESTAMP
            WHERE stripe_event_id = ?
            """,
            (
                resultado,
                contacto_id,
                object_id,
                estado_anterior,
                estado_nuevo,
                error_message,
                event_id,
            ),
        )

    def marcar_evento_fallido(self, cursor, event_id: str, error_message: str) -> None:
        cursor.execute(
            """
            UPDATE stripe_webhook_events
            SET resultado = 'error', estado_procesamiento = 'failed',
                error_message = ?, procesado_en = CURRENT_TIMESTAMP
            WHERE stripe_event_id = ?
            """,
            (error_message[:2000], event_id),
        )

    def select_contacto_por_payment_intent(self, cursor, payment_intent_id: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id FROM contactos_ruana
            WHERE stripe_payment_intent_id = ?
            LIMIT 1
            """,
            (payment_intent_id,),
        )
        return cursor.fetchone()

    def select_contacto_por_transfer_id(self, cursor, transfer_id: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id FROM contactos_ruana
            WHERE stripe_transfer_id = ?
            LIMIT 1
            """,
            (transfer_id,),
        )
        return cursor.fetchone()

    def select_contacto_por_metadata(self, cursor, contacto_id: int) -> Optional[Any]:
        cursor.execute(
            "SELECT id FROM contactos_ruana WHERE id = ? AND modo_pago = 'stripe'",
            (contacto_id,),
        )
        return cursor.fetchone()

    def actualizar_checkout_session(
        self, cursor, contacto_id: int, session_id: str, payment_intent_id: str
    ) -> int:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET stripe_checkout_session_id = COALESCE(stripe_checkout_session_id, ?),
                stripe_payment_intent_id = COALESCE(stripe_payment_intent_id, ?),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ? AND modo_pago = 'stripe'
            """,
            (session_id, payment_intent_id, contacto_id),
        )
        return cursor.rowcount

    def actualizar_stripe_transfer_id(self, cursor, contacto_id: int, transfer_id: str) -> int:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET stripe_transfer_id = COALESCE(stripe_transfer_id, ?),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (transfer_id, contacto_id),
        )
        return cursor.rowcount

    def actualizar_stripe_charge_id(self, cursor, contacto_id: int, charge_id: str) -> int:
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET stripe_charge_id = COALESCE(stripe_charge_id, ?),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (charge_id, contacto_id),
        )
        return cursor.rowcount

    def insertar_refund(
        self,
        cursor,
        contacto_id: int,
        refund_id: str,
        charge_id: str,
        amount: float,
        currency: str,
        event_id: str,
        es_total: bool,
    ) -> bool:
        cursor.execute(
            """
            INSERT OR IGNORE INTO stripe_refunds (
                contacto_id, stripe_refund_id, stripe_charge_id,
                amount, currency, stripe_event_id, es_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (contacto_id, refund_id, charge_id, amount, currency, event_id, 1 if es_total else 0),
        )
        return cursor.rowcount > 0

    def sumar_reembolsos_contacto(self, cursor, contacto_id: int) -> float:
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM stripe_refunds WHERE contacto_id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        return float(row[0] if row else 0)

    def insertar_disputa(
        self,
        cursor,
        contacto_id: int,
        dispute_id: str,
        charge_id: str,
        amount: float,
        currency: str,
        reason: str,
        status: str,
        evidence_due_by: Optional[str],
        event_id: str,
    ) -> bool:
        cursor.execute(
            """
            INSERT OR IGNORE INTO stripe_disputes (
                contacto_id, stripe_dispute_id, stripe_charge_id,
                amount, currency, reason, status, evidence_due_by, stripe_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contacto_id, dispute_id, charge_id, amount, currency,
                reason, status, evidence_due_by, event_id,
            ),
        )
        return cursor.rowcount > 0

    def actualizar_contacto_disputa(
        self,
        cursor,
        contacto_id: int,
        dispute_id: str,
        charge_id: str,
        amount: float,
        reason: str,
        status: str,
    ) -> None:
        cols = self._columnas(cursor, "contactos_ruana")
        sets = ["actualizado_en = CURRENT_TIMESTAMP"]
        params = []
        mapping = {
            "stripe_dispute_id": dispute_id,
            "stripe_charge_id": charge_id,
            "stripe_dispute_amount": amount,
            "stripe_dispute_reason": reason,
            "stripe_dispute_status": status,
        }
        for col, val in mapping.items():
            if col in cols:
                sets.append(f"{col} = ?")
                params.append(val)
        params.append(contacto_id)
        cursor.execute(
            f"UPDATE contactos_ruana SET {', '.join(sets)} WHERE id = ?",
            params,
        )

    def _columnas(self, cursor, tabla: str) -> set:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return {row[1] for row in cursor.fetchall()}

    def actualizar_solo_estado_transferencia(
        self, cursor, contacto_id: int, estado_transferencia: str
    ) -> int:
        columnas = self._columnas(cursor, "contactos_ruana")
        if "estado_transferencia" not in columnas:
            return 0
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado_transferencia = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (estado_transferencia, contacto_id),
        )
        return cursor.rowcount

    def audit_webhook(
        self,
        db,
        cursor,
        contacto_id: Optional[int],
        accion: str,
        detalles: Dict[str, Any],
    ) -> None:
        db._audit_log(
            cursor,
            "contacto",
            contacto_id or 0,
            accion,
            "stripe_webhook",
            "",
            json.dumps(detalles, ensure_ascii=False),
        )
