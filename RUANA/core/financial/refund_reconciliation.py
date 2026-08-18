"""Reconciliación explícita RUANA ↔ Stripe Refund (FASE 05)."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple


class DecisionReconciliacionRefund(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    MISMATCH = "mismatch"
    BLOCKED = "blocked"
    MISSING_RUANA = "missing_ruana"
    MISSING_STRIPE = "missing_stripe"


def extraer_snapshot_refund_stripe(obj: Any) -> Dict[str, Any]:
    return {
        "id": str(_get(obj, "id") or ""),
        "amount": int(_get(obj, "amount") or 0),
        "currency": str(_get(obj, "currency") or "eur").lower(),
        "status": str(_get(obj, "status") or ""),
        "charge": str(_get(obj, "charge") or ""),
        "payment_intent": str(_get(obj, "payment_intent") or ""),
    }


def evaluar_reconciliacion_refund(
    *,
    financial_refund: Optional[Dict[str, Any]],
    stripe_snapshot: Dict[str, Any],
    importe_cobrado_cents: int,
    disputa_abierta: bool = False,
) -> Tuple[DecisionReconciliacionRefund, str]:
    if disputa_abierta:
        return DecisionReconciliacionRefund.BLOCKED, "disputa_stripe_abierta"
    if not financial_refund:
        if stripe_snapshot.get("id"):
            return DecisionReconciliacionRefund.MISSING_RUANA, "refund_stripe_sin_ruana"
        return DecisionReconciliacionRefund.PENDING, "sin_datos"

    stripe_id = stripe_snapshot.get("id") or ""
    ruana_stripe_id = (financial_refund.get("stripe_refund_id") or "").strip()
    if stripe_id and ruana_stripe_id and stripe_id != ruana_stripe_id:
        return DecisionReconciliacionRefund.MISMATCH, "refund_id"

    amount = int(stripe_snapshot.get("amount") or 0)
    solicitado = int(financial_refund.get("importe_solicitado_cents") or 0)
    confirmado = int(financial_refund.get("importe_confirmado_cents") or 0)
    if amount and confirmado and amount != confirmado:
        return DecisionReconciliacionRefund.MISMATCH, "importe_confirmado"
    if amount and solicitado and amount != solicitado and not confirmado:
        return DecisionReconciliacionRefund.MISMATCH, "importe_solicitado"

    currency = stripe_snapshot.get("currency") or "eur"
    if currency and (financial_refund.get("moneda") or "eur") != currency:
        return DecisionReconciliacionRefund.MISMATCH, "moneda"

    charge = stripe_snapshot.get("charge") or ""
    ruana_charge = (financial_refund.get("charge_id") or "").strip()
    if charge and ruana_charge and charge != ruana_charge:
        return DecisionReconciliacionRefund.MISMATCH, "charge"

    status = (stripe_snapshot.get("status") or "").lower()
    estado_ruana = (financial_refund.get("estado") or "").upper()
    if status == "succeeded" and estado_ruana not in ("SUCCEEDED", "PENDING_RECONCILIATION"):
        return DecisionReconciliacionRefund.MISMATCH, "estado"
    if status == "failed" and estado_ruana != "FAILED":
        return DecisionReconciliacionRefund.MISMATCH, "estado"

    if solicitado > importe_cobrado_cents:
        return DecisionReconciliacionRefund.MISMATCH, "supera_cobrado"

    if status == "succeeded":
        return DecisionReconciliacionRefund.CONFIRMED, "coherencia_stripe"
    return DecisionReconciliacionRefund.PENDING, f"stripe_status_{status or 'unknown'}"


def _get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    val = getattr(obj, key, None)
    return val if val is not None else default
