"""Repositorio de reconciliación financiera RUANA ↔ Stripe (FASE 02)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class FinancialReconciliationRepo:
    """Persistencia de discrepancias de reconciliación."""

    def existe_discrepancia_abierta(
        self, cursor, contacto_id: int, tipo_discrepancia: str
    ) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM financial_reconciliation
            WHERE contacto_id = ? AND tipo_discrepancia = ?
              AND estado_reconciliacion = 'open'
            LIMIT 1
            """,
            (contacto_id, tipo_discrepancia),
        )
        return cursor.fetchone() is not None

    def insertar_discrepancia(
        self,
        cursor,
        contacto_id: int,
        tipo_discrepancia: str,
        *,
        stripe_payment_intent_id: str = "",
        stripe_transfer_id: str = "",
        ruana_estado: str = "",
        stripe_estado: str = "",
        importe_ruana: Optional[float] = None,
        importe_stripe: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        if self.existe_discrepancia_abierta(cursor, contacto_id, tipo_discrepancia):
            return None
        cursor.execute(
            """
            INSERT INTO financial_reconciliation (
                contacto_id, stripe_payment_intent_id, stripe_transfer_id,
                ruana_estado, stripe_estado, tipo_discrepancia,
                importe_ruana, importe_stripe, estado_reconciliacion, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                contacto_id,
                stripe_payment_intent_id or None,
                stripe_transfer_id or None,
                ruana_estado or None,
                stripe_estado or None,
                tipo_discrepancia,
                importe_ruana,
                importe_stripe,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        return cursor.lastrowid

    def listar_contactos_stripe(self, cursor, limit: int = 200) -> List[Any]:
        cursor.execute(
            """
            SELECT id, estado_financiero, estado_transferencia,
                   stripe_payment_intent_id, stripe_transfer_id,
                   importe_acordado, importe_final, importe_neto_profesional,
                   modo_pago, estado_pago
            FROM contactos_ruana
            WHERE modo_pago = 'stripe'
              AND (stripe_payment_intent_id IS NOT NULL OR stripe_transfer_id IS NOT NULL
                   OR estado_financiero IS NOT NULL)
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    def listar_discrepancias_abiertas(self, cursor, contacto_id: Optional[int] = None) -> List[Any]:
        if contacto_id:
            cursor.execute(
                """
                SELECT * FROM financial_reconciliation
                WHERE contacto_id = ? AND estado_reconciliacion = 'open'
                ORDER BY detected_at DESC
                """,
                (contacto_id,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM financial_reconciliation
                WHERE estado_reconciliacion = 'open'
                ORDER BY detected_at DESC
                """
            )
        return cursor.fetchall()

    def marcar_resuelta(self, cursor, discrepancia_id: int, resolution: str) -> int:
        cursor.execute(
            """
            UPDATE financial_reconciliation
            SET estado_reconciliacion = 'resolved',
                resolved_at = CURRENT_TIMESTAMP,
                resolution = ?
            WHERE id = ?
            """,
            (resolution[:2000], discrepancia_id),
        )
        return cursor.rowcount
