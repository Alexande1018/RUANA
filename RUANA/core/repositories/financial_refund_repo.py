"""Repositorio de reembolsos Stripe blindados (FASE 05)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


class FinancialRefundRepo:
    def tabla_existe(self, cursor) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_refunds' LIMIT 1"
        )
        return cursor.fetchone() is not None

    def reclamar_refund(
        self,
        cursor,
        *,
        contacto_id: int,
        idempotency_key: str,
        importe_solicitado_cents: int,
        moneda: str,
        causa_ruana: str,
        actor_codigo: str,
        permiso_usado: str,
        payment_intent_id: str,
        charge_id: str,
        conflicto_id: Optional[int],
        comision_total_cents: int,
        comision_conservada_cents: int,
        comision_devuelta_cents: int,
        parte_ejecutada_cents: int,
        parte_no_ejecutada_cents: int,
        motivo_stripe: str = "",
        metadata: Optional[Dict] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        cursor.execute(
            """
            INSERT OR IGNORE INTO financial_refunds (
                contacto_id, conflicto_id, payment_intent_id, charge_id,
                importe_solicitado_cents, moneda, estado, causa_ruana,
                comision_total_cents, comision_conservada_cents, comision_devuelta_cents,
                parte_ejecutada_cents, parte_no_ejecutada_cents,
                actor_codigo, permiso_usado, idempotency_key, motivo_stripe, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, 'REQUESTED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contacto_id, conflicto_id, payment_intent_id or None, charge_id or None,
                importe_solicitado_cents, moneda, causa_ruana,
                comision_total_cents, comision_conservada_cents, comision_devuelta_cents,
                parte_ejecutada_cents, parte_no_ejecutada_cents,
                actor_codigo, permiso_usado, idempotency_key, motivo_stripe or None,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        if cursor.rowcount > 0:
            return "claimed", self.select_por_idempotency_key(cursor, idempotency_key)
        return "existing", self.select_por_idempotency_key(cursor, idempotency_key)

    def select_por_idempotency_key(self, cursor, idempotency_key: str) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM financial_refunds WHERE idempotency_key = ?", (idempotency_key,))
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def select_por_id(self, cursor, refund_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM financial_refunds WHERE id = ?", (refund_id,))
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def select_por_stripe_refund_id(self, cursor, stripe_refund_id: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_refunds WHERE stripe_refund_id = ?", (stripe_refund_id,),
        )
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def sum_confirmados_contacto(
        self, cursor, contacto_id: int, *, exclude_refund_id: Optional[int] = None,
    ) -> int:
        sql = """
            SELECT COALESCE(SUM(importe_confirmado_cents), 0)
            FROM financial_refunds
            WHERE contacto_id = ? AND estado IN ('SUCCEEDED', 'PENDING_RECONCILIATION', 'STRIPE_PROCESSING')
        """
        params: list = [contacto_id]
        if exclude_refund_id:
            sql += " AND id <> ?"
            params.append(exclude_refund_id)
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def sum_pendientes_contacto(
        self, cursor, contacto_id: int, *, exclude_refund_id: Optional[int] = None,
    ) -> int:
        sql = """
            SELECT COALESCE(SUM(importe_solicitado_cents), 0)
            FROM financial_refunds
            WHERE contacto_id = ? AND estado IN ('REQUESTED', 'STRIPE_PROCESSING', 'PENDING_RECONCILIATION')
        """
        params = [contacto_id]
        if exclude_refund_id:
            sql += " AND id <> ?"
            params.append(exclude_refund_id)
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def tiene_refund_pendiente(self, cursor, contacto_id: int) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM financial_refunds
            WHERE contacto_id = ? AND estado IN ('REQUESTED', 'STRIPE_PROCESSING', 'PENDING_RECONCILIATION')
            LIMIT 1
            """,
            (contacto_id,),
        )
        return cursor.fetchone() is not None

    def intentar_stripe_processing(self, cursor, refund_id: int) -> bool:
        cursor.execute(
            """
            UPDATE financial_refunds
            SET estado = 'STRIPE_PROCESSING', actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ? AND estado = 'REQUESTED' AND stripe_refund_id IS NULL
            """,
            (refund_id,),
        )
        return cursor.rowcount == 1

    def marcar_stripe_resultado(
        self,
        cursor,
        refund_id: int,
        *,
        stripe_refund_id: str,
        estado: str,
        importe_confirmado_cents: int = 0,
        error_stripe: str = "",
    ) -> bool:
        cursor.execute(
            """
            UPDATE financial_refunds
            SET stripe_refund_id = COALESCE(NULLIF(?, ''), stripe_refund_id),
                estado = ?, importe_confirmado_cents = CASE WHEN ? > 0 THEN ? ELSE importe_confirmado_cents END,
                error_stripe = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                stripe_refund_id or "", estado, importe_confirmado_cents,
                importe_confirmado_cents, error_stripe or None, refund_id,
            ),
        )
        return cursor.rowcount == 1

    def actualizar_desde_webhook(
        self,
        cursor,
        refund_id: int,
        *,
        importe_confirmado_cents: int,
        estado: str,
    ) -> bool:
        cursor.execute(
            """
            UPDATE financial_refunds
            SET importe_confirmado_cents = ?, estado = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (importe_confirmado_cents, estado, refund_id),
        )
        return cursor.rowcount == 1

    def registrar_intento(
        self, cursor, refund_id: int, operacion: str, actor: str, resultado: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO financial_refund_attempts (
                refund_id, operacion, actor_codigo, resultado, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (refund_id, operacion, actor, resultado, json.dumps(metadata or {}, ensure_ascii=False)),
        )

    def listar_por_contacto(self, cursor, contacto_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_refunds WHERE contacto_id = ? ORDER BY id ASC",
            (contacto_id,),
        )
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def _row_dict(self, row, cursor) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            return dict(row)
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}
