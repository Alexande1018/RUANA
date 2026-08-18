"""Reconciliación explícita RUANA ↔ Stripe Transfer (FASE 03.2).

Decisión de dominio documentada en docs/flujos/financial-transfers.md:

- transfer.created NO implica automáticamente TRANSFERIDO.
- TRANSFERIDO requiere evaluación explícita que devuelva ``confirmed``.
- Stripe Connect (API >= 2017-04-06) no emite transfer.paid; la confirmación
  financiera se basa en coherencia del snapshot + evidencia Stripe
  (balance_transaction + destination_payment) sin inventar eventos.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple

from core.financial.estados import EstadoFinanciero


class DecisionReconciliacionTransfer(str, Enum):
  CONFIRMED = "confirmed"
  PENDING = "pending"
  REVERSED = "reversed"
  MISMATCH = "mismatch"


_ESTADOS_PRE_CONFIRMACION = frozenset({
    EstadoFinanciero.LIBERACION_AUTORIZADA,
    EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
    EstadoFinanciero.TRANSFERENCIA_ENVIADA,
})

_ESTADOS_YA_CERRADOS = frozenset({
    EstadoFinanciero.TRANSFERIDO,
})


def extraer_snapshot_stripe(obj: Any) -> Dict[str, Any]:
    """Normaliza campos relevantes del objeto Transfer Stripe."""
    meta = _get(obj, "metadata") or {}
    if not isinstance(meta, dict):
        meta = dict(getattr(meta, "__dict__", {}) or {})
    return {
        "id": str(_get(obj, "id") or ""),
        "amount": _get(obj, "amount"),
        "currency": str(_get(obj, "currency") or "").lower(),
        "destination": str(_get(obj, "destination") or ""),
        "reversed": bool(_get(obj, "reversed", False)),
        "amount_reversed": int(_get(obj, "amount_reversed") or 0),
        "balance_transaction": str(_get(obj, "balance_transaction") or ""),
        "destination_payment": str(_get(obj, "destination_payment") or ""),
        "metadata": dict(meta),
    }


def evaluar_reconciliacion_transfer(
    *,
    contacto_id: int,
    estado_financiero: Optional[EstadoFinanciero],
    financial_transfer: Optional[Dict[str, Any]],
    stripe_snapshot: Dict[str, Any],
    legacy_confirmacion: bool = False,
) -> Tuple[DecisionReconciliacionTransfer, str]:
    """
    Compara RUANA vs snapshot Stripe. No mueve dinero.

    Returns:
        (decisión, motivo)
    """
    if stripe_snapshot.get("reversed"):
        return DecisionReconciliacionTransfer.REVERSED, "stripe_transfer_reversed"

    meta_cid = stripe_snapshot.get("metadata", {}).get("contacto_id")
    if meta_cid is not None:
        try:
            if int(meta_cid) != contacto_id:
                return DecisionReconciliacionTransfer.MISMATCH, "metadata_contacto_id"
        except (TypeError, ValueError):
            return DecisionReconciliacionTransfer.MISMATCH, "metadata_contacto_id_invalida"

    tid = stripe_snapshot.get("id") or ""
    if not tid:
        return DecisionReconciliacionTransfer.MISMATCH, "transfer_id_ausente"

    if estado_financiero == EstadoFinanciero.TRANSFERENCIA_REVERTIDA:
        return DecisionReconciliacionTransfer.REVERSED, "operacion_revertida"

    if legacy_confirmacion:
        if estado_financiero in _ESTADOS_PRE_CONFIRMACION or estado_financiero in _ESTADOS_YA_CERRADOS:
            return DecisionReconciliacionTransfer.CONFIRMED, "legacy_transfer_paid"
        return DecisionReconciliacionTransfer.PENDING, f"legacy_estado_{estado_financiero.value if estado_financiero else 'none'}"

    if estado_financiero in _ESTADOS_YA_CERRADOS:
        ft_tid = (financial_transfer.get("stripe_transfer_id") or "").strip() if financial_transfer else ""
        if legacy_confirmacion and tid and (not ft_tid or ft_tid == tid):
            return DecisionReconciliacionTransfer.CONFIRMED, "ya_transferido_idempotente"
        if ft_tid and ft_tid == tid:
            return DecisionReconciliacionTransfer.CONFIRMED, "ya_transferido_idempotente"
        if not ft_tid and not financial_transfer and legacy_confirmacion and tid:
            return DecisionReconciliacionTransfer.CONFIRMED, "ya_transferido_idempotente"
        return DecisionReconciliacionTransfer.MISMATCH, "transfer_id_distinto_en_cerrado"

    if not financial_transfer:
        return DecisionReconciliacionTransfer.PENDING, "sin_registro_financial_transfers"

    ft_tid = (financial_transfer.get("stripe_transfer_id") or "").strip()
    if ft_tid and ft_tid != tid:
        return DecisionReconciliacionTransfer.MISMATCH, "transfer_id"

    amount = stripe_snapshot.get("amount")
    if amount is not None and int(financial_transfer.get("amount_cents") or 0) != int(amount):
        return DecisionReconciliacionTransfer.MISMATCH, "importe"

    currency = stripe_snapshot.get("currency") or "eur"
    if currency and (financial_transfer.get("currency") or "eur") != currency:
        return DecisionReconciliacionTransfer.MISMATCH, "moneda"

    destination = stripe_snapshot.get("destination") or ""
    if destination and financial_transfer.get("destination_account_id") and (
        destination != financial_transfer.get("destination_account_id")
    ):
        return DecisionReconciliacionTransfer.MISMATCH, "destination"

    if estado_financiero not in _ESTADOS_PRE_CONFIRMACION and estado_financiero not in _ESTADOS_YA_CERRADOS:
        return DecisionReconciliacionTransfer.PENDING, f"estado_financiero_{estado_financiero.value if estado_financiero else 'none'}"

    bt = stripe_snapshot.get("balance_transaction") or ""
    dp = stripe_snapshot.get("destination_payment") or ""
    if not bt or not dp:
        return DecisionReconciliacionTransfer.PENDING, "evidencia_stripe_incompleta"

    if (financial_transfer.get("reconciliacion_estado") or "") == DecisionReconciliacionTransfer.CONFIRMED.value:
        return DecisionReconciliacionTransfer.CONFIRMED, "ya_reconciliado"

    return DecisionReconciliacionTransfer.CONFIRMED, "coherencia_y_evidencia_stripe"


def comparar_snapshots(
    anterior: Dict[str, Any], nuevo: Dict[str, Any]
) -> Optional[str]:
    """Detecta cambios materiales entre snapshots. Devuelve tipo de cambio o None."""
    for campo in ("amount", "currency", "destination"):
        if anterior.get(campo) != nuevo.get(campo) and nuevo.get(campo) not in (None, ""):
            if anterior.get(campo) not in (None, "") and anterior.get(campo) != nuevo.get(campo):
                return campo
    if not anterior.get("reversed") and nuevo.get("reversed"):
        return "reversed"
    return None


def _get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    val = getattr(obj, key, None)
    return val if val is not None else default
