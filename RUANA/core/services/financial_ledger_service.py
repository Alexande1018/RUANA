"""Servicio del ledger financiero interno (FASE 08). Append-only, doble partida."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Sequence

from core.financial.ledger_accounts import CuentaLedger, cuenta_valida
from core.financial.ledger_estados import EstadoLedgerTransaction
from core.financial.ledger_types import TipoLedgerTransaction
from core.financial.reconciliation_snapshot import comision_ruana_cents
from core.repositories.financial_ledger_repo import FinancialLedgerRepo

_repo = FinancialLedgerRepo()

LEDGER_VERSION = "fase08-1"


class LedgerValidationError(ValueError):
    pass


def _validar_lineas(
    lineas: Sequence[Dict[str, Any]],
    moneda: str,
) -> tuple[int, int]:
    if len(lineas) < 2:
        raise LedgerValidationError("Una transacción requiere al menos dos líneas")
    total_debe = 0
    total_haber = 0
    for i, ln in enumerate(lineas):
        cuenta = str(ln.get("account_code") or ln.get("account") or "")
        if not cuenta_valida(cuenta):
            raise LedgerValidationError(f"Cuenta inválida en línea {i}: {cuenta}")
        debit = int(ln.get("debit_cents") or 0)
        credit = int(ln.get("credit_cents") or 0)
        if debit < 0 or credit < 0:
            raise LedgerValidationError("Importes negativos no permitidos")
        if debit > 0 and credit > 0:
            raise LedgerValidationError("Una línea no puede tener debe y haber simultáneos")
        if debit + credit <= 0:
            raise LedgerValidationError("Cada línea debe tener importe positivo")
        cur = str(ln.get("currency") or moneda).lower()
        if cur != moneda.lower():
            raise LedgerValidationError("Moneda inconsistente entre líneas")
        total_debe += debit
        total_haber += credit
    if total_debe != total_haber:
        raise LedgerValidationError(
            f"Transacción desequilibrada: debe={total_debe} haber={total_haber}"
        )
    if total_debe <= 0:
        raise LedgerValidationError("Transacción con importe cero")
    return total_debe, total_haber


def publicar_transaccion(
    db,
    *,
    idempotency_key: str,
    contacto_id: Optional[int],
    tipo: TipoLedgerTransaction,
    moneda: str,
    lineas: Sequence[Dict[str, Any]],
    actor_origen: str = "sistema",
    evento_origen: str = "",
    referencia_stripe: str = "",
    event_links: Optional[List[Dict[str, str]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    reversa_de_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Publica una transacción contable equilibrada. Idempotente por idempotency_key.
    No edita POSTED; las correcciones usan transacciones compensatorias.
    """
    key = (idempotency_key or "").strip()
    if not key:
        return {"status": "error", "message": "idempotency_key obligatoria"}
    moneda = (moneda or "eur").lower()
    try:
        _validar_lineas(lineas, moneda)
    except LedgerValidationError as e:
        return {"status": "error", "message": str(e), "code": "validation"}

    tx_key = hashlib.sha256(f"{key}:{tipo.value}".encode()).hexdigest()[:40]

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            prev = _repo.select_por_idempotency(cursor, key)
            if prev and prev.get("estado") in (
                EstadoLedgerTransaction.POSTED.value,
                EstadoLedgerTransaction.VOIDED.value,
            ):
                conn.commit()
                return {
                    "status": "success",
                    "idempotent": True,
                    "transaction_id": prev["id"],
                    "estado": prev["estado"],
                }

            tx_id = _repo.insert_transaction(
                cursor,
                transaction_key=tx_key,
                contacto_id=contacto_id,
                tipo=tipo.value,
                moneda=moneda,
                estado=EstadoLedgerTransaction.DRAFT.value,
                actor_origen=actor_origen,
                evento_origen=evento_origen,
                referencia_stripe=referencia_stripe,
                idempotency_key=key,
                reversa_de_id=reversa_de_id,
                metadata=metadata,
            )
            if not tx_id:
                prev = _repo.select_por_idempotency(cursor, key)
                conn.commit()
                return {
                    "status": "success",
                    "idempotent": True,
                    "transaction_id": (prev or {}).get("id"),
                    "estado": (prev or {}).get("estado"),
                }

            existing_entries = _repo.listar_entries(cursor, tx_id)
            if not existing_entries:
                for ln in lineas:
                    _repo.insert_entry(
                        cursor,
                        ledger_transaction_id=tx_id,
                        account_code=str(ln.get("account_code") or ln.get("account")),
                        debit_cents=int(ln.get("debit_cents") or 0),
                        credit_cents=int(ln.get("credit_cents") or 0),
                        currency=moneda,
                        descripcion=str(ln.get("descripcion") or ""),
                        referencia=str(ln.get("referencia") or referencia_stripe or ""),
                    )

            debe, haber = _repo.sumas_transaction(cursor, tx_id)
            if debe != haber or debe <= 0:
                conn.rollback()
                return {"status": "error", "message": "Transacción desequilibrada tras insertar líneas"}

            for link in event_links or []:
                _repo.insert_event_link(
                    cursor,
                    ledger_transaction_id=tx_id,
                    resource_type=str(link.get("resource_type") or ""),
                    resource_id=str(link.get("resource_id") or ""),
                    metadata=link.get("metadata"),
                )

            _repo.marcar_posted(cursor, tx_id)
            for ln in _repo.listar_entries(cursor, tx_id):
                _repo.actualizar_balance(
                    cursor,
                    account_code=str(ln["account_code"]),
                    contacto_id=contacto_id,
                    currency=moneda,
                    debit_delta=int(ln["debit_cents"] or 0),
                    credit_delta=int(ln["credit_cents"] or 0),
                )
            conn.commit()
            return {
                "status": "success",
                "transaction_id": tx_id,
                "estado": EstadoLedgerTransaction.POSTED.value,
                "debit_cents": debe,
                "credit_cents": haber,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)[:300]}
        finally:
            if conn:
                conn.close()


def anular_transaccion(
    db,
    transaction_id: int,
    *,
    actor: str,
    idempotency_key: str,
    motivo: str,
) -> Dict[str, Any]:
    """VOID mediante transacción compensatoria inversa vinculada."""
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            orig = _repo.select_por_id(cursor, transaction_id)
            if not orig:
                return {"status": "error", "message": "Transacción no encontrada"}
            if orig.get("estado") != EstadoLedgerTransaction.POSTED.value:
                return {"status": "error", "message": "Solo se anulan transacciones POSTED"}
            entries = _repo.listar_entries(cursor, transaction_id)
            if not entries:
                return {"status": "error", "message": "Transacción sin líneas"}
            lineas_inversas = [
                {
                    "account_code": e["account_code"],
                    "debit_cents": int(e["credit_cents"] or 0),
                    "credit_cents": int(e["debit_cents"] or 0),
                    "descripcion": f"Anulación: {motivo}",
                }
                for e in entries
            ]
            conn.commit()
        finally:
            conn.close()

    inv = publicar_transaccion(
        db,
        idempotency_key=idempotency_key,
        contacto_id=orig.get("contacto_id"),
        tipo=TipoLedgerTransaction.VOID_COMPENSATION,
        moneda=str(orig.get("moneda") or "eur"),
        lineas=lineas_inversas,
        actor_origen=actor,
        evento_origen="void",
        referencia_stripe=str(orig.get("referencia_stripe") or ""),
        reversa_de_id=transaction_id,
        metadata={"motivo": motivo, "original_id": transaction_id},
    )
    if inv.get("status") != "success":
        return inv

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _repo.marcar_voided(cursor, transaction_id)
            conn.commit()
        finally:
            conn.close()
    return {
        "status": "success",
        "voided_id": transaction_id,
        "compensation_id": inv.get("transaction_id"),
        "estado": EstadoLedgerTransaction.VOIDED.value,
    }


def _linea(cuenta: CuentaLedger, *, debit: int = 0, credit: int = 0, desc: str = "") -> Dict[str, Any]:
    return {
        "account_code": cuenta.value,
        "debit_cents": int(debit),
        "credit_cents": int(credit),
        "descripcion": desc,
    }


def registrar_pago_confirmado(
    db,
    *,
    contacto_id: int,
    importe_bruto_cents: int,
    payment_intent_id: str,
    idempotency_key: str,
    actor: str = "webhook",
    stripe_fee_cents: int = 0,
) -> Dict[str, Any]:
    """Cadena contable de pago recibido + obligación profesional/comisión."""
    if importe_bruto_cents <= 0:
        return {"status": "ignored", "message": "importe cero"}
    comision = comision_ruana_cents(importe_bruto_cents)
    neto_pro = max(0, importe_bruto_cents - comision)

    r1 = publicar_transaccion(
        db,
        idempotency_key=f"{idempotency_key}:recv",
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.STRIPE_RECEIVABLE, debit=importe_bruto_cents, desc="PI cobrado"),
            _linea(CuentaLedger.CLEARING_PAYMENTS, credit=importe_bruto_cents),
        ],
        actor_origen=actor,
        evento_origen="payment_intent.succeeded",
        referencia_stripe=payment_intent_id,
        event_links=[{"resource_type": "payment_intent", "resource_id": payment_intent_id}],
    )
    if r1.get("status") != "success":
        return r1

    r2 = publicar_transaccion(
        db,
        idempotency_key=f"{idempotency_key}:settle",
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.PAYMENT_SETTLED,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.STRIPE_BALANCE, debit=importe_bruto_cents),
            _linea(CuentaLedger.STRIPE_RECEIVABLE, credit=importe_bruto_cents),
        ],
        actor_origen=actor,
        evento_origen="payment_settled",
        referencia_stripe=payment_intent_id,
    )
    if r2.get("status") != "success":
        return r2

    oblig_lines = [
        _linea(CuentaLedger.CLEARING_PAYMENTS, debit=importe_bruto_cents),
        _linea(CuentaLedger.PROFESSIONAL_PAYABLE, credit=neto_pro),
        _linea(CuentaLedger.RUANA_COMMISSION_REVENUE, credit=comision),
    ]
    r3 = publicar_transaccion(
        db,
        idempotency_key=f"{idempotency_key}:obligation",
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.OBLIGATION_RECOGNIZED,
        moneda="eur",
        lineas=oblig_lines,
        actor_origen=actor,
        evento_origen="obligation_recognized",
        referencia_stripe=payment_intent_id,
    )
    if r3.get("status") != "success":
        return r3

    if stripe_fee_cents > 0:
        publicar_transaccion(
            db,
            idempotency_key=f"{idempotency_key}:fee",
            contacto_id=contacto_id,
            tipo=TipoLedgerTransaction.STRIPE_FEE,
            moneda="eur",
            lineas=[
                _linea(CuentaLedger.STRIPE_PROCESSING_FEE, debit=stripe_fee_cents),
                _linea(CuentaLedger.STRIPE_BALANCE, credit=stripe_fee_cents),
            ],
            actor_origen=actor,
            evento_origen="stripe_fee",
            referencia_stripe=payment_intent_id,
        )
    return {"status": "success", "transactions": [r1, r2, r3]}


def registrar_transferencia(
    db,
    *,
    contacto_id: int,
    importe_cents: int,
    transfer_id: str,
    idempotency_key: str,
    actor: str = "sistema",
    settled: bool = False,
) -> Dict[str, Any]:
    if importe_cents <= 0:
        return {"status": "ignored"}
    r1 = publicar_transaccion(
        db,
        idempotency_key=f"{idempotency_key}:out",
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.TRANSFER_OUT,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.PROFESSIONAL_PAYABLE, debit=importe_cents),
            _linea(CuentaLedger.CLEARING_TRANSFERS, credit=importe_cents),
        ],
        actor_origen=actor,
        evento_origen="transfer.created",
        referencia_stripe=transfer_id,
        event_links=[{"resource_type": "transfer", "resource_id": transfer_id}],
    )
    if r1.get("status") != "success" or not settled:
        return r1
    return publicar_transaccion(
        db,
        idempotency_key=f"{idempotency_key}:settled",
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.TRANSFER_SETTLED,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.CLEARING_TRANSFERS, debit=importe_cents),
            _linea(CuentaLedger.STRIPE_BALANCE, credit=importe_cents),
        ],
        actor_origen=actor,
        evento_origen="transfer.paid",
        referencia_stripe=transfer_id,
        event_links=[{"resource_type": "transfer", "resource_id": transfer_id}],
    )


def registrar_reversion_transferencia(
    db,
    *,
    contacto_id: int,
    importe_cents: int,
    transfer_id: str,
    idempotency_key: str,
    actor: str = "webhook",
) -> Dict[str, Any]:
    if importe_cents <= 0:
        return {"status": "ignored"}
    return publicar_transaccion(
        db,
        idempotency_key=idempotency_key,
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.TRANSFER_REVERSED,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.CLEARING_TRANSFERS, debit=importe_cents, desc="Reversión transfer"),
            _linea(CuentaLedger.PROFESSIONAL_PAYABLE, credit=importe_cents),
        ],
        actor_origen=actor,
        evento_origen="transfer.reversed",
        referencia_stripe=transfer_id,
        event_links=[{"resource_type": "transfer", "resource_id": transfer_id}],
    )


def registrar_refund(
    db,
    *,
    contacto_id: int,
    importe_cents: int,
    refund_id: str,
    idempotency_key: str,
    comision_devuelta_cents: int = 0,
    actor: str = "sistema",
    settled: bool = True,
) -> Dict[str, Any]:
    if importe_cents <= 0:
        return {"status": "ignored"}
    r1 = publicar_transaccion(
        db,
        idempotency_key=f"{idempotency_key}:obligation",
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.REFUND_OBLIGATION,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.CUSTOMER_REFUND_PAYABLE, debit=importe_cents),
            _linea(CuentaLedger.CLEARING_REFUNDS, credit=importe_cents),
        ],
        actor_origen=actor,
        evento_origen="refund.succeeded",
        referencia_stripe=refund_id,
        event_links=[{"resource_type": "refund", "resource_id": refund_id}],
        metadata={"comision_devuelta_cents": comision_devuelta_cents},
    )
    if r1.get("status") != "success" or not settled:
        return r1
    lines = [
        _linea(CuentaLedger.CLEARING_REFUNDS, debit=importe_cents),
        _linea(CuentaLedger.STRIPE_BALANCE, credit=importe_cents),
    ]
    if comision_devuelta_cents > 0:
        lines.extend([
            _linea(CuentaLedger.RUANA_COMMISSION_REVENUE, debit=comision_devuelta_cents),
            _linea(CuentaLedger.REFUND_LOSS, credit=comision_devuelta_cents),
        ])
    return publicar_transaccion(
        db,
        idempotency_key=f"{idempotency_key}:settled",
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.REFUND_SETTLED,
        moneda="eur",
        lineas=lines,
        actor_origen=actor,
        evento_origen="refund.settled",
        referencia_stripe=refund_id,
    )


def registrar_disputa_abierta(
    db,
    *,
    contacto_id: int,
    dispute_id: str,
    importe_cents: int,
    idempotency_key: str,
    actor: str = "webhook",
) -> Dict[str, Any]:
    """Registra el hecho sin reconocer pérdida."""
    return publicar_transaccion(
        db,
        idempotency_key=idempotency_key,
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.DISPUTE_OPENED,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.DISPUTE_PAYABLE, debit=importe_cents, desc="Disputa abierta"),
            _linea(CuentaLedger.FUNDS_HELD, credit=importe_cents),
        ],
        actor_origen=actor,
        evento_origen="charge.dispute.created",
        referencia_stripe=dispute_id,
        event_links=[{"resource_type": "dispute", "resource_id": dispute_id}],
    )


def registrar_disputa_perdida(
    db,
    *,
    contacto_id: int,
    dispute_id: str,
    importe_perdido_cents: int,
    idempotency_key: str,
    actor: str = "webhook",
) -> Dict[str, Any]:
    if importe_perdido_cents <= 0:
        return {"status": "ignored"}
    return publicar_transaccion(
        db,
        idempotency_key=idempotency_key,
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.DISPUTE_LOSS,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.DISPUTE_LOSS, debit=importe_perdido_cents),
            _linea(CuentaLedger.STRIPE_BALANCE, credit=importe_perdido_cents),
        ],
        actor_origen=actor,
        evento_origen="charge.dispute.closed.lost",
        referencia_stripe=dispute_id,
        event_links=[{"resource_type": "dispute", "resource_id": dispute_id}],
    )


def registrar_disputa_ganada(
    db,
    *,
    contacto_id: int,
    dispute_id: str,
    importe_reinstated_cents: int,
    idempotency_key: str,
    actor: str = "webhook",
) -> Dict[str, Any]:
    if importe_reinstated_cents <= 0:
        return {"status": "ignored"}
    return publicar_transaccion(
        db,
        idempotency_key=idempotency_key,
        contacto_id=contacto_id,
        tipo=TipoLedgerTransaction.DISPUTE_FUNDS_REINSTATED,
        moneda="eur",
        lineas=[
            _linea(CuentaLedger.STRIPE_BALANCE, debit=importe_reinstated_cents),
            _linea(CuentaLedger.FUNDS_HELD, credit=importe_reinstated_cents),
        ],
        actor_origen=actor,
        evento_origen="charge.dispute.closed.won",
        referencia_stripe=dispute_id,
        event_links=[{"resource_type": "dispute", "resource_id": dispute_id}],
    )


def obtener_transaccion(db, transaction_id: int) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            tx = _repo.select_por_id(cursor, transaction_id)
            if not tx:
                return {"status": "error", "message": "No encontrada"}
            entries = _repo.listar_entries(cursor, transaction_id)
            return {"status": "success", "transaction": tx, "entries": entries}
        finally:
            conn.close()


def saldo_cuenta(
    db, account_code: str, *, contacto_id: Optional[int] = None, currency: str = "eur",
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            saldo = _repo.saldo_cuenta(cursor, account_code, contacto_id=contacto_id, currency=currency)
            return {"status": "success", "account_code": account_code, **saldo}
        finally:
            conn.close()
