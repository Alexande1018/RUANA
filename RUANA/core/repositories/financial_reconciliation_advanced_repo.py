"""Repositorio de reconciliación avanzada (FASE 07)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


class FinancialReconciliationAdvancedRepo:
    RECONCILER_VERSION = "fase07-1"

    def tabla_existe(self, cursor, nombre: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (nombre,),
        )
        return cursor.fetchone() is not None

    def reclamar_ejecucion(
        self,
        cursor,
        *,
        contacto_id: Optional[int],
        payment_intent_id: str,
        transfer_id: str,
        operacion: str,
        idempotency_key: str,
        actor_codigo: str,
        permiso_usado: str,
        motivo: str = "",
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        cursor.execute(
            """
            INSERT OR IGNORE INTO financial_reconciliation_executions (
                contacto_id, payment_intent_id, transfer_id, operacion,
                estado, reconciler_version, idempotency_key,
                actor_codigo, permiso_usado, motivo
            ) VALUES (?, ?, ?, ?, 'NOT_STARTED', ?, ?, ?, ?, ?)
            """,
            (
                contacto_id, payment_intent_id or None, transfer_id or None,
                operacion, self.RECONCILER_VERSION, idempotency_key,
                actor_codigo, permiso_usado, motivo or None,
            ),
        )
        row = self.select_por_idempotency(cursor, idempotency_key)
        if cursor.rowcount > 0:
            return "claimed", row
        return "existing", row

    def select_por_idempotency(self, cursor, key: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_reconciliation_executions WHERE idempotency_key = ?",
            (key,),
        )
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def select_por_id(self, cursor, execution_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_reconciliation_executions WHERE id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def actualizar_estado(
        self,
        cursor,
        execution_id: int,
        estado: str,
        *,
        metricas: Optional[Dict] = None,
        error_stripe: str = "",
        finalizar: bool = False,
    ) -> None:
        sets = ["estado = ?", "actualizado_en = CURRENT_TIMESTAMP"]
        params: list = [estado]
        if metricas is not None:
            sets.append("metricas_json = ?")
            params.append(json.dumps(metricas, ensure_ascii=False))
        if error_stripe:
            sets.append("error_stripe = ?")
            params.append(error_stripe[:2000])
        if finalizar:
            sets.append("finalizado_en = CURRENT_TIMESTAMP")
        params.append(execution_id)
        cursor.execute(
            f"UPDATE financial_reconciliation_executions SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )

    def guardar_snapshot(
        self,
        cursor,
        *,
        execution_id: int,
        contacto_id: int,
        snapshot: Dict[str, Any],
        origen: str = "stripe_api",
    ) -> int:
        ident = snapshot.get("identidad") or {}
        imp = snapshot.get("importes_cents") or {}
        ctrl = snapshot.get("control") or {}
        cursor.execute(
            """
            INSERT INTO financial_reconciliation_snapshots (
                execution_id, contacto_id, payment_intent_id, charge_id,
                balance_transaction_id, transfer_id, connected_account_id,
                moneda, importe_bruto_cents, importe_cobrado_cents, fee_stripe_cents,
                neto_ruana_cents, importe_transferido_cents, total_reembolsado_cents,
                importe_disputado_cents, comision_ruana_cents, obligacion_profesional_cents,
                estado_ruana, estado_stripe, origen, reconciler_version, snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id, contacto_id,
                ident.get("payment_intent_id") or None,
                ident.get("charge_id") or None,
                ident.get("balance_transaction_id") or None,
                ident.get("transfer_id") or None,
                ident.get("connected_account_id") or None,
                ctrl.get("moneda") or "eur",
                int(imp.get("importe_bruto") or 0),
                int(imp.get("importe_cobrado") or 0),
                int(imp.get("fee_stripe") or 0),
                int(imp.get("neto_ruana") or 0),
                int(imp.get("importe_transferido") or 0),
                int(imp.get("total_reembolsado") or 0),
                int(imp.get("importe_disputado") or 0),
                int(imp.get("comision_ruana") or 0),
                int(imp.get("obligacion_profesional") or 0),
                ctrl.get("estado_ruana") or None,
                ctrl.get("estado_stripe") or None,
                origen,
                self.RECONCILER_VERSION,
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid or 0)

    def registrar_recurso(
        self,
        cursor,
        execution_id: int,
        *,
        resource_type: str,
        resource_id: str,
        fetch_status: str,
        error_code: str = "",
        http_status: int = 0,
        metadata: Optional[Dict] = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO financial_reconciliation_resource_results (
                execution_id, resource_type, resource_id, fetch_status,
                error_code, http_status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id, resource_type, resource_id or None, fetch_status,
                error_code or None, http_status or None,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def listar_pendientes_lote(self, cursor, limit: int) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, stripe_payment_intent_id, stripe_transfer_id, estado_financiero
            FROM contactos_ruana
            WHERE modo_pago = 'stripe'
              AND stripe_payment_intent_id IS NOT NULL
              AND stripe_payment_intent_id != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def _row_dict(self, row, cursor) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            return dict(row)
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}
