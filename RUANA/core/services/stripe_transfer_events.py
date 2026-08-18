"""Lógica compartida para eventos reales de transferencias Stripe Connect (FASE 03.1).

API Stripe >= 2017-04-06 (Connect):
- transfer.created  → confirmación de transferencia exitosa → TRANSFERIDO
- transfer.updated    → sincronización metadata / detección reversed
- transfer.reversed   → reversión
- transfer.paid       → LEGACY (no se emite en API moderna)
- transfer.failed     → LEGACY (fallos son síncronos en Transfer.create)
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.financial.discrepancia import TipoDiscrepancia
from core.financial.estados import EstadoFinanciero, EstadoTransferencia
from core.financial.state_machine import FinancialStateMachine
from core.repositories.financial_transaction_repo import FinancialTransactionRepo
from core.repositories.financial_transfer_repo import FinancialTransferRepo
from core.services import financial_reconciliation_service as reconciliation
from core.services import financial_transaction_service as fts
from core.services import financial_transfer_service as transfer_svc

_fin_repo = FinancialTransactionRepo()
_transfer_repo = FinancialTransferRepo()
_sm = FinancialStateMachine()

_EVENTOS_CONFIRMACION = frozenset({"transfer.created", "transfer.paid"})
_EVENTOS_LEGACY = frozenset({"transfer.paid", "transfer.failed"})


def es_evento_legacy(event_type: str) -> bool:
    return event_type in _EVENTOS_LEGACY


def confirmar_transfer_desde_webhook(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_type: str,
    event_id: str,
) -> Tuple[str, str, str]:
    """
    Procesa transfer.created (real) o transfer.paid (legacy alias).

    Returns: (resultado, estado_anterior, estado_nuevo)
    """
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""

    if _transfer_revertida(obj):
        return manejar_reversion_transfer(
            db, contacto_id, transfer_id, obj, event_id=event_id, event_type=event_type
        )

    bloqueo = validar_coherencia_transfer(db, contacto_id, obj)
    if bloqueo:
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.AMOUNT_MISMATCH,
            stripe_transfer_id=transfer_id,
            ruana_estado=ant_val,
            stripe_estado=event_type,
            metadata={"event_id": event_id, "bloqueo": bloqueo},
        )
        return "bloqueado_coherencia", ant_val, ant_val

    if estado == EstadoFinanciero.TRANSFERIDO:
        _persistir_referencias_stripe(db, contacto_id, transfer_id, obj)
        return "idempotent", ant_val, ant_val

    _persistir_referencias_stripe(db, contacto_id, transfer_id, obj)
    _avanzar_hasta_enviada(db, contacto_id, transfer_id, event_type)

    fin = transfer_svc.finalizar_transferencia_completada(
        db, contacto_id, transfer_id, origen=f"stripe_webhook:{event_type}"
    )
    if fin.get("status") == "success":
        nuevo = fin.get("estado_financiero", EstadoFinanciero.TRANSFERIDO.value)
        res = "idempotent" if fin.get("idempotent") else "ok"
        if event_type in _EVENTOS_LEGACY and res == "ok":
            res = "ok_legacy_alias"
        return res, ant_val, nuevo

    est_final = fts.obtener_estado_financiero(db, contacto_id)
    nuevo_val = est_final.value if est_final else ant_val
    return fin.get("message", "transition_skipped"), ant_val, nuevo_val


def sincronizar_transfer_actualizada(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_id: str,
) -> Tuple[str, str, str]:
    """transfer.updated — sincroniza referencias; reversión si aplica."""
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""

    _persistir_referencias_stripe(db, contacto_id, transfer_id, obj)

    if _transfer_revertida(obj):
        return manejar_reversion_transfer(
            db, contacto_id, transfer_id, obj, event_id=event_id, event_type="transfer.updated"
        )

    return "ok_sync", ant_val, ant_val


def manejar_reversion_transfer(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_id: str,
    event_type: str,
) -> Tuple[str, str, str]:
    """transfer.reversed o transfer con reversed=true."""
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""

    _persistir_referencias_stripe(db, contacto_id, transfer_id, obj)

    if estado == EstadoFinanciero.TRANSFERENCIA_REVERTIDA:
        return "idempotent", ant_val, ant_val

    if estado == EstadoFinanciero.TRANSFERIDO:
        if _sm.puede_transicionar(estado, EstadoFinanciero.TRANSFERENCIA_REVERTIDA):
            res = fts.transicionar(
                db, contacto_id, EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
                actor_tipo="stripe_webhook",
                motivo=event_type,
                stripe_ref=transfer_id,
            )
            if res.get("status") == "success":
                with db._lock:
                    conn = db._connect()
                    cursor = conn.cursor()
                    _fin_repo.actualizar_solo_estado_transferencia(
                        cursor, contacto_id, EstadoTransferencia.REVERTIDA.value
                    )
                    conn.commit()
                    conn.close()
                return "ok", ant_val, EstadoFinanciero.TRANSFERENCIA_REVERTIDA.value
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
            stripe_transfer_id=transfer_id,
            ruana_estado=ant_val,
            stripe_estado="reversed",
            metadata={"event_id": event_id, "event_type": event_type},
        )
        return "discrepancia_registrada", ant_val, ant_val

    reconciliation.registrar_discrepancia(
        db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
        stripe_transfer_id=transfer_id,
        ruana_estado=ant_val,
        stripe_estado="reversed",
        metadata={"event_id": event_id, "nota": "reversión sin TRANSFERIDO previo"},
    )
    return "discrepancia_registrada", ant_val, ant_val


def manejar_transfer_failed_legacy(
    db,
    contacto_id: int,
    transfer_id: str,
    *,
    event_id: str,
    estado_terminal: bool,
    ant_val: str,
) -> Tuple[str, str, str]:
    """
    transfer.failed — solo API legacy (< 2017-04-06).

    En API moderna los fallos ocurren síncronamente en Transfer.create.
    """
    db.registrar_evento_sistema(
        "stripe_transfer_failed_legacy",
        f"Evento legacy transfer.failed en contacto #{contacto_id}",
        actor_tipo="sistema",
        metadata={"contacto_id": contacto_id, "transfer_id": transfer_id, "event_id": event_id},
    )

    if estado_terminal:
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
            stripe_transfer_id=transfer_id,
            ruana_estado=ant_val,
            stripe_estado="failed",
            metadata={"event_id": event_id, "nota": "transfer.failed legacy tras estado terminal"},
        )
        return "discrepancia_registrada", ant_val, ant_val

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _fin_repo.actualizar_solo_estado_transferencia(
            cursor, contacto_id, EstadoTransferencia.FALLIDA.value
        )
        conn.commit()
        conn.close()

    _, nuevo_val, res = _transicion_fallida(db, contacto_id, transfer_id)
    return res, ant_val, nuevo_val


def _transicion_fallida(db, contacto_id: int, transfer_id: str) -> Tuple[str, str, str]:
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""
    if estado == EstadoFinanciero.TRANSFERENCIA_FALLIDA:
        return ant_val, ant_val, "idempotent"
    res = fts.transicionar(
        db, contacto_id, EstadoFinanciero.TRANSFERENCIA_FALLIDA,
        actor_tipo="stripe_webhook",
        motivo="transfer.failed (legacy)", stripe_ref=transfer_id,
    )
    if res.get("status") == "success":
        return ant_val, res.get("estado_nuevo", ant_val), "ok"
    if estado == EstadoFinanciero.TRANSFERENCIA_FALLIDA:
        return ant_val, ant_val, "idempotent"
    return ant_val, ant_val, res.get("message", "transition_skipped")


def validar_coherencia_transfer(db, contacto_id: int, obj: Any) -> Optional[str]:
    """Valida importe/destino/metadata. Devuelve motivo de bloqueo o None."""
    meta_contacto = _meta_contacto_id(obj)
    if meta_contacto and meta_contacto != contacto_id:
        return "metadata_contacto_id"

    amount = _get(obj, "amount")
    destination = str(_get(obj, "destination") or "")
    currency = str(_get(obj, "currency") or "eur").lower()

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        row = _transfer_repo.select_por_contacto(cursor, contacto_id)
        conn.close()

    if not row:
        return None

    tr = _transfer_repo._row_dict(row)
    if not tr:
        return None

    if amount is not None and int(tr.get("amount_cents") or 0) != int(amount):
        return "importe"
    if destination and tr.get("destination_account_id") and destination != tr.get("destination_account_id"):
        return "connect"
    if currency and (tr.get("currency") or "eur") != currency:
        return "moneda"
    return None


def _avanzar_hasta_enviada(db, contacto_id: int, transfer_id: str, event_type: str) -> None:
    estado = fts.obtener_estado_financiero(db, contacto_id)
    if estado in (EstadoFinanciero.TRANSFERENCIA_ENVIADA, EstadoFinanciero.TRANSFERIDO):
        return
    if estado == EstadoFinanciero.LIBERACION_AUTORIZADA:
        fts.transicionar(
            db, contacto_id, EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
            actor_tipo="stripe_webhook", motivo=event_type, stripe_ref=transfer_id,
        )
    estado = fts.obtener_estado_financiero(db, contacto_id)
    if estado in (EstadoFinanciero.TRANSFERENCIA_PENDIENTE, EstadoFinanciero.LIBERACION_AUTORIZADA):
        fts.transicionar(
            db, contacto_id, EstadoFinanciero.TRANSFERENCIA_ENVIADA,
            actor_tipo="stripe_webhook", motivo=event_type, stripe_ref=transfer_id,
        )


def _persistir_referencias_stripe(db, contacto_id: int, transfer_id: str, obj: Any) -> None:
    balance_txn = str(_get(obj, "balance_transaction") or "")
    dest_payment = str(_get(obj, "destination_payment") or "")
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        from core.repositories.stripe_webhook_repo import StripeWebhookRepo
        wh = StripeWebhookRepo()
        wh.actualizar_stripe_transfer_id(cursor, contacto_id, transfer_id)
        _transfer_repo.actualizar_referencias_stripe(
            cursor, contacto_id, transfer_id,
            balance_transaction_id=balance_txn,
            destination_payment_id=dest_payment,
        )
        conn.commit()
        conn.close()


def _transfer_revertida(obj: Any) -> bool:
    return bool(_get(obj, "reversed", False))


def _meta_contacto_id(obj: Any) -> Optional[int]:
    meta = _get(obj, "metadata") or {}
    if not isinstance(meta, dict):
        meta = dict(getattr(meta, "__dict__", {}) or {})
    raw = meta.get("contacto_id")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return None


def _get(obj, key: str, default=None):
    val = getattr(obj, key, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default
