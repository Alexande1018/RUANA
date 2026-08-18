"""Hooks de integración ledger ↔ flujos existentes (FASE 08)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.services import financial_ledger_service as fls


def _safe(call) -> Optional[Dict[str, Any]]:
    try:
        return call()
    except Exception:
        return None


def on_pago_confirmado(
    db, *, contacto_id: int, payment_intent_id: str, importe_bruto_cents: int, event_id: str = "",
) -> None:
    _safe(lambda: fls.registrar_pago_confirmado(
        db,
        contacto_id=contacto_id,
        importe_bruto_cents=importe_bruto_cents,
        payment_intent_id=payment_intent_id,
        idempotency_key=f"ledger-pago-{contacto_id}-{payment_intent_id}",
        actor="webhook",
    ))


def on_transfer_creada(
    db, *, contacto_id: int, transfer_id: str, importe_cents: int, idempotency_key: str,
) -> None:
    _safe(lambda: fls.registrar_transferencia(
        db,
        contacto_id=contacto_id,
        importe_cents=importe_cents,
        transfer_id=transfer_id,
        idempotency_key=f"ledger-tr-{idempotency_key}",
        settled=False,
    ))


def on_transfer_completada(
    db, *, contacto_id: int, transfer_id: str, importe_cents: int,
) -> None:
    _safe(lambda: fls.registrar_transferencia(
        db,
        contacto_id=contacto_id,
        importe_cents=importe_cents,
        transfer_id=transfer_id,
        idempotency_key=f"ledger-tr-settled-{contacto_id}-{transfer_id}",
        settled=True,
    ))


def on_transfer_revertida(
    db, *, contacto_id: int, transfer_id: str, importe_cents: int, event_id: str = "",
) -> None:
    _safe(lambda: fls.registrar_reversion_transferencia(
        db,
        contacto_id=contacto_id,
        importe_cents=importe_cents,
        transfer_id=transfer_id,
        idempotency_key=f"ledger-tr-rev-{contacto_id}-{transfer_id}-{event_id or 'evt'}",
    ))


def on_refund_succeeded(
    db, *,
    contacto_id: int,
    refund_id: str,
    importe_cents: int,
    comision_devuelta_cents: int = 0,
    idempotency_key: str = "",
) -> None:
    key = idempotency_key or f"ledger-refund-{contacto_id}-{refund_id}"
    _safe(lambda: fls.registrar_refund(
        db,
        contacto_id=contacto_id,
        importe_cents=importe_cents,
        refund_id=refund_id,
        idempotency_key=key,
        comision_devuelta_cents=comision_devuelta_cents,
    ))


def on_disputa_creada(
    db, *, contacto_id: int, dispute_id: str, importe_cents: int, event_id: str = "",
) -> None:
    _safe(lambda: fls.registrar_disputa_abierta(
        db,
        contacto_id=contacto_id,
        dispute_id=dispute_id,
        importe_cents=importe_cents,
        idempotency_key=f"ledger-dp-open-{contacto_id}-{dispute_id}",
    ))


def on_disputa_cerrada(
    db, *,
    contacto_id: int,
    dispute_id: str,
    status: str,
    importe_perdido_cents: int = 0,
    importe_reinstated_cents: int = 0,
    event_id: str = "",
) -> None:
    st = (status or "").lower()
    if st == "lost" and importe_perdido_cents > 0:
        _safe(lambda: fls.registrar_disputa_perdida(
            db,
            contacto_id=contacto_id,
            dispute_id=dispute_id,
            importe_perdido_cents=importe_perdido_cents,
            idempotency_key=f"ledger-dp-lost-{contacto_id}-{dispute_id}",
        ))
    elif st == "won" and importe_reinstated_cents > 0:
        _safe(lambda: fls.registrar_disputa_ganada(
            db,
            contacto_id=contacto_id,
            dispute_id=dispute_id,
            importe_reinstated_cents=importe_reinstated_cents,
            idempotency_key=f"ledger-dp-won-{contacto_id}-{dispute_id}",
        ))
