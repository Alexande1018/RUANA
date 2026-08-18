"""Reconciliación RUANA ↔ Stripe Dispute (FASE 06)."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple


class DecisionReconciliacionDispute(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    MISMATCH = "mismatch"
    BLOCKED = "blocked"
    MISSING_RUANA = "missing_ruana"
    MISSING_STRIPE = "missing_stripe"


def extraer_snapshot_dispute_stripe(obj: Any) -> Dict[str, Any]:
    evidence = _get(obj, "evidence_details") or {}
    due_by = None
    if isinstance(evidence, dict):
        due_by = evidence.get("due_by")
    elif hasattr(evidence, "due_by"):
        due_by = evidence.due_by
    return {
        "id": str(_get(obj, "id") or ""),
        "amount": int(_get(obj, "amount") or 0),
        "currency": str(_get(obj, "currency") or "eur").lower(),
        "status": str(_get(obj, "status") or ""),
        "reason": str(_get(obj, "reason") or ""),
        "charge": str(_get(obj, "charge") or ""),
        "payment_intent": str(_get(obj, "payment_intent") or ""),
        "evidence_due_by": due_by,
        "network_reason_code": str(_get(obj, "network_reason_code") or ""),
        "balance_transaction": str(_get(obj, "balance_transaction") or ""),
    }


def evaluar_reconciliacion_dispute(
    *,
    financial_dispute: Optional[Dict[str, Any]],
    stripe_snapshot: Dict[str, Any],
    importe_cobrado_cents: int = 0,
) -> Tuple[DecisionReconciliacionDispute, str]:
    if not financial_dispute:
        if stripe_snapshot.get("id"):
            return DecisionReconciliacionDispute.MISSING_RUANA, "dispute_stripe_sin_ruana"
        return DecisionReconciliacionDispute.PENDING, "sin_datos"

    stripe_id = stripe_snapshot.get("id") or ""
    ruana_id = (financial_dispute.get("stripe_dispute_id") or "").strip()
    if stripe_id and ruana_id and stripe_id != ruana_id:
        return DecisionReconciliacionDispute.MISMATCH, "dispute_id"

    amount = int(stripe_snapshot.get("amount") or 0)
    ruana_amount = int(financial_dispute.get("amount_cents") or 0)
    if amount and ruana_amount and amount != ruana_amount:
        return DecisionReconciliacionDispute.MISMATCH, "importe"

    currency = stripe_snapshot.get("currency") or "eur"
    if currency and (financial_dispute.get("currency") or "eur") != currency:
        return DecisionReconciliacionDispute.MISMATCH, "moneda"

    charge = stripe_snapshot.get("charge") or ""
    ruana_charge = (financial_dispute.get("charge_id") or "").strip()
    if charge and ruana_charge and charge != ruana_charge:
        return DecisionReconciliacionDispute.MISMATCH, "charge"

    pi = stripe_snapshot.get("payment_intent") or ""
    ruana_pi = (financial_dispute.get("payment_intent_id") or "").strip()
    if pi and ruana_pi and pi != ruana_pi:
        return DecisionReconciliacionDispute.MISMATCH, "payment_intent"

    status = (stripe_snapshot.get("status") or "").lower()
    ruana_status = (financial_dispute.get("status_stripe") or "").lower()
    if status and ruana_status and status != ruana_status:
        return DecisionReconciliacionDispute.MISMATCH, "estado_stripe"

    if ruana_amount > importe_cobrado_cents > 0:
        return DecisionReconciliacionDispute.MISMATCH, "supera_cobrado"

    if status in ("won", "lost", "charge_refunded", "warning_closed"):
        return DecisionReconciliacionDispute.CONFIRMED, "coherencia_stripe"
    if status:
        return DecisionReconciliacionDispute.PENDING, f"stripe_status_{status}"
    return DecisionReconciliacionDispute.PENDING, "sin_status"


def _get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    val = getattr(obj, key, None)
    return val if val is not None else default
