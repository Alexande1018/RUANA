"""Hooks de integración ledger ↔ flujos existentes (FASE 08)."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from core.services import financial_ledger_service as fls


class LedgerHookError(RuntimeError):
    """Fallo al registrar movimiento contable; requiere alerta y/o reintento."""


def _registrar_alerta_ledger_inmediata(
    db,
    *,
    hook: str,
    contacto_id: Optional[int],
    error: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Alerta financiera inmediata cuando un hook de ledger falla (B4)."""
    alert_key = f"ledger:{hook}:{contacto_id or 0}"
    meta = {"hook": hook, "error": (error or "")[:500], **(metadata or {})}
    try:
        from core.repositories.financial_automation_repo import FinancialAutomationRepo

        repo = FinancialAutomationRepo()
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                if repo.tabla_existe(cursor, "financial_alerts"):
                    repo.upsert_alerta(
                        cursor,
                        alert_key=alert_key,
                        tipo="ledger_hook_fallido",
                        severidad="critical",
                        contacto_id=contacto_id,
                        accion_recomendada="Revisar ledger y reconciliar contacto afectado",
                        accion_disponible="financial.monitoring.view",
                        fuente="financial_ledger_hooks",
                        run_id="ledger-hook-immediate",
                        metadata=meta,
                    )
                    conn.commit()
            finally:
                conn.close()
    except Exception:
        pass
    try:
        db.registrar_evento_sistema(
            "ledger_hook_fallido",
            json.dumps(meta, ensure_ascii=False)[:500],
            actor_tipo="sistema",
        )
    except Exception:
        pass


def _run_ledger(
    db,
    *,
    hook: str,
    contacto_id: Optional[int],
    call: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    """Ejecuta hook contable; alerta inmediata y propaga error si falla (B4)."""
    try:
        result = call()
    except Exception as exc:
        _registrar_alerta_ledger_inmediata(
            db, hook=hook, contacto_id=contacto_id, error=str(exc),
        )
        raise LedgerHookError(f"Ledger {hook} falló: {exc}") from exc
    if isinstance(result, dict) and result.get("status") == "error":
        msg = str(result.get("message") or "error ledger")
        _registrar_alerta_ledger_inmediata(
            db, hook=hook, contacto_id=contacto_id, error=msg, metadata=result,
        )
        raise LedgerHookError(f"Ledger {hook}: {msg}")
    return result


def on_pago_confirmado(
    db, *, contacto_id: int, payment_intent_id: str, importe_bruto_cents: int, event_id: str = "",
) -> None:
    _run_ledger(
        db,
        hook="on_pago_confirmado",
        contacto_id=contacto_id,
        call=lambda: fls.registrar_pago_confirmado(
            db,
            contacto_id=contacto_id,
            importe_bruto_cents=importe_bruto_cents,
            payment_intent_id=payment_intent_id,
            idempotency_key=f"ledger-pago-{contacto_id}-{payment_intent_id}",
            actor="webhook",
        ),
    )


def on_transfer_creada(
    db, *, contacto_id: int, transfer_id: str, importe_cents: int, idempotency_key: str,
) -> None:
    _run_ledger(
        db,
        hook="on_transfer_creada",
        contacto_id=contacto_id,
        call=lambda: fls.registrar_transferencia(
            db,
            contacto_id=contacto_id,
            importe_cents=importe_cents,
            transfer_id=transfer_id,
            idempotency_key=f"ledger-tr-{idempotency_key}",
            settled=False,
        ),
    )


def on_transfer_completada(
    db, *, contacto_id: int, transfer_id: str, importe_cents: int,
) -> None:
    _run_ledger(
        db,
        hook="on_transfer_completada",
        contacto_id=contacto_id,
        call=lambda: fls.registrar_transferencia(
            db,
            contacto_id=contacto_id,
            importe_cents=importe_cents,
            transfer_id=transfer_id,
            idempotency_key=f"ledger-tr-settled-{contacto_id}-{transfer_id}",
            settled=True,
        ),
    )


def on_transfer_revertida(
    db, *, contacto_id: int, transfer_id: str, importe_cents: int, event_id: str = "",
) -> None:
    _run_ledger(
        db,
        hook="on_transfer_revertida",
        contacto_id=contacto_id,
        call=lambda: fls.registrar_reversion_transferencia(
            db,
            contacto_id=contacto_id,
            importe_cents=importe_cents,
            transfer_id=transfer_id,
            idempotency_key=f"ledger-tr-rev-{contacto_id}-{transfer_id}-{event_id or 'evt'}",
        ),
    )


def on_refund_succeeded(
    db, *,
    contacto_id: int,
    refund_id: str,
    importe_cents: int,
    comision_devuelta_cents: int = 0,
    idempotency_key: str = "",
) -> None:
    key = idempotency_key or f"ledger-refund-{contacto_id}-{refund_id}"
    _run_ledger(
        db,
        hook="on_refund_succeeded",
        contacto_id=contacto_id,
        call=lambda: fls.registrar_refund(
            db,
            contacto_id=contacto_id,
            importe_cents=importe_cents,
            refund_id=refund_id,
            idempotency_key=key,
            comision_devuelta_cents=comision_devuelta_cents,
        ),
    )


def on_disputa_creada(
    db, *, contacto_id: int, dispute_id: str, importe_cents: int, event_id: str = "",
) -> None:
    _run_ledger(
        db,
        hook="on_disputa_creada",
        contacto_id=contacto_id,
        call=lambda: fls.registrar_disputa_abierta(
            db,
            contacto_id=contacto_id,
            dispute_id=dispute_id,
            importe_cents=importe_cents,
            idempotency_key=f"ledger-dp-open-{contacto_id}-{dispute_id}",
        ),
    )


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
        _run_ledger(
            db,
            hook="on_disputa_cerrada_lost",
            contacto_id=contacto_id,
            call=lambda: fls.registrar_disputa_perdida(
                db,
                contacto_id=contacto_id,
                dispute_id=dispute_id,
                importe_perdido_cents=importe_perdido_cents,
                idempotency_key=f"ledger-dp-lost-{contacto_id}-{dispute_id}",
            ),
        )
    elif st == "won" and importe_reinstated_cents > 0:
        _run_ledger(
            db,
            hook="on_disputa_cerrada_won",
            contacto_id=contacto_id,
            call=lambda: fls.registrar_disputa_ganada(
                db,
                contacto_id=contacto_id,
                dispute_id=dispute_id,
                importe_reinstated_cents=importe_reinstated_cents,
                idempotency_key=f"ledger-dp-won-{contacto_id}-{dispute_id}",
            ),
        )
