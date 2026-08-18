"""Reconciliación del ledger interno (FASE 08). Solo detecta — no autocorrige."""
from __future__ import annotations

from typing import Any, Dict, List

from core.financial.ledger_accounts import ALL_CUENTAS
from core.repositories.financial_ledger_repo import FinancialLedgerRepo

_repo = FinancialLedgerRepo()


def comprobar_equilibrio(db, *, limit: int = 100) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            desequilibrados = _repo.listar_desequilibrados(cursor, limit)
            huerfanos = _repo.listar_posted_sin_entries(cursor, limit)
            return {
                "status": "success",
                "desequilibrados": desequilibrados,
                "huerfanos": huerfanos,
                "ok": not desequilibrados and not huerfanos,
            }
        finally:
            conn.close()


def reconstruir_saldos_desde_entries(db, *, contacto_id: int | None = None) -> Dict[str, Any]:
    """Reconstruye ledger_account_balances desde entries POSTED (verificación)."""
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ledger_account_balances")
            cursor.execute(
                """
                SELECT e.account_code, t.contacto_id, e.currency,
                       SUM(e.debit_cents), SUM(e.credit_cents)
                FROM ledger_entries e
                JOIN ledger_transactions t ON t.id = e.ledger_transaction_id
                WHERE t.estado = 'POSTED'
                GROUP BY e.account_code, t.contacto_id, e.currency
                """
            )
            for row in cursor.fetchall():
                acc, cid, cur, deb, cred = row[0], row[1], row[2], int(row[3]), int(row[4])
                if contacto_id is not None and int(cid or 0) != int(contacto_id):
                    continue
                _repo.actualizar_balance(
                    cursor,
                    account_code=str(acc),
                    contacto_id=int(cid or 0) or None,
                    currency=str(cur or "eur"),
                    debit_delta=deb,
                    credit_delta=cred,
                )
            conn.commit()
            return {"status": "success"}
        finally:
            conn.close()


def detectar_cuentas_invalidas(db, *, limit: int = 50) -> List[Dict[str, Any]]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT e.account_code, e.ledger_transaction_id
                FROM ledger_entries e
                JOIN ledger_transactions t ON t.id = e.ledger_transaction_id
                WHERE t.estado = 'POSTED'
                LIMIT ?
                """,
                (limit * 10,),
            )
            invalidas = []
            for row in cursor.fetchall():
                code = row[0] if not hasattr(row, "keys") else row["account_code"]
                if code not in ALL_CUENTAS:
                    invalidas.append({
                        "account_code": code,
                        "ledger_transaction_id": row[1] if not hasattr(row, "keys") else row["ledger_transaction_id"],
                    })
            return invalidas[:limit]
        finally:
            conn.close()


def reconciliar_con_snapshot(
    db,
    contacto_id: int,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Compara importes del snapshot FASE 07 con saldos ledger derivados."""
    imp = snapshot.get("importes_cents") or {}
    bruto = int(imp.get("importe_bruto") or imp.get("importe_cobrado") or 0)
    comision = int(imp.get("comision_ruana") or 0)
    transferido = int(imp.get("importe_transferido") or 0)
    reembolsado = int(imp.get("total_reembolsado") or 0)
    discrepancias: List[str] = []

    rev = saldo_cuenta_local(db, "RUANA_COMMISSION_REVENUE", contacto_id=contacto_id)
    if comision and abs(rev["saldo_neto_cents"] - comision) > 1:
        discrepancias.append("COMMISSION_MISMATCH")

    payable = saldo_cuenta_local(db, "PROFESSIONAL_PAYABLE", contacto_id=contacto_id)
    expected_payable = max(0, bruto - comision - transferido)
    if transferido and payable["credit_cents"] and abs(payable["saldo_neto_cents"] + expected_payable) > transferido:
        discrepancias.append("PROFESSIONAL_PAYABLE_MISMATCH")

    if reembolsado:
        ref = saldo_cuenta_local(db, "CUSTOMER_REFUND_PAYABLE", contacto_id=contacto_id)
        if ref["debit_cents"] and abs(ref["debit_cents"] - reembolsado) > 1:
            discrepancias.append("REFUND_MISMATCH")

    return {
        "status": "success",
        "contacto_id": contacto_id,
        "discrepancias": discrepancias,
        "ok": not discrepancias,
    }


def saldo_cuenta_local(db, account_code: str, *, contacto_id: int) -> Dict[str, int]:
    from core.services import financial_ledger_service as fls
    r = fls.saldo_cuenta(db, account_code, contacto_id=contacto_id)
    return {
        "debit_cents": int(r.get("debit_cents") or 0),
        "credit_cents": int(r.get("credit_cents") or 0),
        "saldo_neto_cents": int(r.get("saldo_neto_cents") or 0),
    }
