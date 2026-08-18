"""Snapshot normalizado de reconciliación financiera (FASE 07)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

RECONCILER_VERSION = "fase07-1"


def comision_ruana_cents(importe_bruto_cents: int) -> int:
    return (int(importe_bruto_cents) * 12) // 100


def empty_snapshot() -> Dict[str, Any]:
    return {
        "identidad": {
            "contacto_id": None,
            "payment_intent_id": "",
            "charge_id": "",
            "balance_transaction_id": "",
            "transfer_id": "",
            "connected_account_id": "",
            "refund_ids": [],
            "dispute_ids": [],
        },
        "importes_cents": {
            "importe_bruto": 0,
            "importe_cobrado": 0,
            "fee_stripe": 0,
            "neto_ruana": 0,
            "importe_transferido": 0,
            "total_reembolsado": 0,
            "importe_disputado": 0,
            "comision_ruana": 0,
            "obligacion_profesional": 0,
        },
        "control": {
            "moneda": "eur",
            "estado_ruana": "",
            "estado_stripe": "",
            "event_ids": [],
            "origen": "",
            "reconciler_version": RECONCILER_VERSION,
        },
        "recursos": {},
    }


def build_ruana_snapshot(contacto: Dict[str, Any]) -> Dict[str, Any]:
    snap = empty_snapshot()
    cid = int(contacto.get("id") or 0)
    bruto = int(round(float(contacto.get("importe_acordado") or contacto.get("importe_final") or 0) * 100))
    neto_pro = int(round(float(contacto.get("importe_neto_profesional") or 0) * 100))
    comision = comision_ruana_cents(bruto)
    snap["identidad"]["contacto_id"] = cid
    snap["identidad"]["payment_intent_id"] = str(contacto.get("stripe_payment_intent_id") or "")
    snap["identidad"]["charge_id"] = str(contacto.get("stripe_charge_id") or "")
    snap["identidad"]["transfer_id"] = str(contacto.get("stripe_transfer_id") or "")
    snap["identidad"]["connected_account_id"] = str(contacto.get("stripe_account_id") or "")
    snap["importes_cents"]["importe_bruto"] = bruto
    snap["importes_cents"]["importe_cobrado"] = bruto
    snap["importes_cents"]["comision_ruana"] = comision
    snap["importes_cents"]["importe_transferido"] = neto_pro
    snap["importes_cents"]["obligacion_profesional"] = max(0, neto_pro)
    snap["control"]["estado_ruana"] = str(contacto.get("estado_financiero") or "")
    snap["control"]["moneda"] = "eur"
    snap["control"]["origen"] = "ruana_db"
    return snap


def merge_stripe_into_snapshot(
    snap: Dict[str, Any],
    *,
    payment_intent: Optional[Dict[str, Any]] = None,
    charge: Optional[Dict[str, Any]] = None,
    balance_transaction: Optional[Dict[str, Any]] = None,
    transfer: Optional[Dict[str, Any]] = None,
    account: Optional[Dict[str, Any]] = None,
    refunds: Optional[List[Dict[str, Any]]] = None,
    disputes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    out = dict(snap)
    ident = dict(out["identidad"])
    imp = dict(out["importes_cents"])
    ctrl = dict(out["control"])
    recursos = dict(out.get("recursos") or {})

    if payment_intent:
        ident["payment_intent_id"] = str(payment_intent.get("id") or ident.get("payment_intent_id") or "")
        imp["importe_cobrado"] = int(payment_intent.get("amount") or imp.get("importe_cobrado") or 0)
        ctrl["estado_stripe"] = str(payment_intent.get("status") or "")
        ctrl["moneda"] = str(payment_intent.get("currency") or ctrl.get("moneda") or "eur")
        recursos["payment_intent"] = payment_intent

    if charge:
        ident["charge_id"] = str(charge.get("id") or ident.get("charge_id") or "")
        imp["importe_bruto"] = int(charge.get("amount") or imp.get("importe_bruto") or 0)
        bt = charge.get("balance_transaction")
        if isinstance(bt, str):
            ident["balance_transaction_id"] = bt
        ctrl["moneda"] = str(charge.get("currency") or ctrl.get("moneda") or "eur")
        recursos["charge"] = charge

    if balance_transaction:
        ident["balance_transaction_id"] = str(balance_transaction.get("id") or ident.get("balance_transaction_id") or "")
        imp["fee_stripe"] = abs(int(balance_transaction.get("fee") or 0))
        imp["neto_ruana"] = int(balance_transaction.get("net") or imp.get("neto_ruana") or 0)
        recursos["balance_transaction"] = balance_transaction

    if transfer:
        ident["transfer_id"] = str(transfer.get("id") or ident.get("transfer_id") or "")
        ident["connected_account_id"] = str(transfer.get("destination") or ident.get("connected_account_id") or "")
        imp["importe_transferido"] = int(transfer.get("amount") or imp.get("importe_transferido") or 0)
        recursos["transfer"] = transfer

    if account:
        ident["connected_account_id"] = str(account.get("id") or ident.get("connected_account_id") or "")
        recursos["account"] = account

    if refunds is not None:
        refund_list = refunds
        ident["refund_ids"] = [str(r.get("id") or "") for r in refund_list if r.get("id")]
        imp["total_reembolsado"] = sum(int(r.get("amount") or 0) for r in refund_list)
        if refund_list:
            recursos["refunds"] = refund_list

    if disputes is not None:
        dispute_list = disputes
        ident["dispute_ids"] = [str(d.get("id") or "") for d in dispute_list if d.get("id")]
        imp["importe_disputado"] = sum(int(d.get("amount") or 0) for d in dispute_list)
        if dispute_list:
            recursos["disputes"] = dispute_list

    if not imp.get("comision_ruana") and imp.get("importe_bruto"):
        imp["comision_ruana"] = comision_ruana_cents(int(imp["importe_bruto"]))

    ctrl["origen"] = "stripe_api"
    out["identidad"] = ident
    out["importes_cents"] = imp
    out["control"] = ctrl
    out["recursos"] = recursos
    return out
