"""Blueprint REST del ledger financiero (FASE 08)."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.ledger_authorization import LEDGER_ADJUST, LEDGER_RECONCILE, LEDGER_VIEW, LEDGER_VOID
from core.services import financial_ledger_reconciliation_service as flrs
from core.services import financial_ledger_service as fls
from web.auth_decorators import _admin_codigo, require_ledger_permission

financial_ledger_bp = Blueprint("financial_ledger", __name__)

_BASE_EN = "/api/admin/financial-ledger"
_BASE_ES = "/api/admin/libro-mayor-financiero"


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


@financial_ledger_bp.route(f"{_BASE_EN}/bp-health", methods=["GET"])
@financial_ledger_bp.route(f"{_BASE_ES}/bp-health", methods=["GET"])
def financial_ledger_bp_health():
    return jsonify({"status": "ok", "dominio": "financial_ledger"})


@financial_ledger_bp.route(f"{_BASE_EN}/transacciones/<int:transaction_id>", methods=["GET"])
@financial_ledger_bp.route(f"{_BASE_ES}/transacciones/<int:transaction_id>", methods=["GET"])
@require_ledger_permission(LEDGER_VIEW)
def obtener_transaccion(transaction_id: int):
    return jsonify(fls.obtener_transaccion(get_db(), transaction_id))


@financial_ledger_bp.route(f"{_BASE_EN}/cuentas/<account_code>/saldo", methods=["GET"])
@financial_ledger_bp.route(f"{_BASE_ES}/cuentas/<account_code>/saldo", methods=["GET"])
@require_ledger_permission(LEDGER_VIEW)
def saldo_cuenta(account_code: str):
    contacto_id = request.args.get("contacto_id")
    r = fls.saldo_cuenta(
        get_db(), account_code,
        contacto_id=int(contacto_id) if contacto_id else None,
    )
    return jsonify(r), 200 if r.get("status") == "success" else 400


@financial_ledger_bp.route(f"{_BASE_EN}/comprobar-equilibrio", methods=["GET"])
@financial_ledger_bp.route(f"{_BASE_ES}/comprobar-equilibrio", methods=["GET"])
@require_ledger_permission(LEDGER_RECONCILE)
def comprobar_equilibrio():
    return jsonify(flrs.comprobar_equilibrio(get_db()))


@financial_ledger_bp.route(f"{_BASE_EN}/huerfanos", methods=["GET"])
@financial_ledger_bp.route(f"{_BASE_ES}/huerfanos", methods=["GET"])
@require_ledger_permission(LEDGER_RECONCILE)
def listar_huerfanos():
    r = flrs.comprobar_equilibrio(get_db())
    return jsonify({"status": "success", "huerfanos": r.get("huerfanos", [])})


@financial_ledger_bp.route(f"{_BASE_EN}/transacciones/<int:transaction_id>/anular", methods=["POST"])
@financial_ledger_bp.route(f"{_BASE_ES}/transacciones/<int:transaction_id>/anular", methods=["POST"])
@require_ledger_permission(LEDGER_VOID)
def anular_transaccion(transaction_id: int):
    data = request.get_json(silent=True) or {}
    motivo = (data.get("motivo") or "").strip()
    key = (data.get("idempotency_key") or request.headers.get("Idempotency-Key") or "").strip()
    if not motivo or not key:
        return jsonify({"status": "error", "message": "motivo e idempotency_key obligatorios"}), 400
    r = fls.anular_transaccion(
        get_db(), transaction_id,
        actor=_admin_codigo(), idempotency_key=key, motivo=motivo,
    )
    return _http(r)


@financial_ledger_bp.route(f"{_BASE_EN}/ajuste", methods=["POST"])
@financial_ledger_bp.route(f"{_BASE_ES}/ajuste", methods=["POST"])
@require_ledger_permission(LEDGER_ADJUST)
def ajuste_admin():
    data = request.get_json(silent=True) or {}
    key = (data.get("idempotency_key") or "").strip()
    lineas = data.get("lineas") or []
    if not key or len(lineas) < 2:
        return jsonify({"status": "error", "message": "idempotency_key y lineas obligatorios"}), 400
    from core.financial.ledger_types import TipoLedgerTransaction
    r = fls.publicar_transaccion(
        get_db(),
        idempotency_key=key,
        contacto_id=int(data["contacto_id"]) if data.get("contacto_id") else None,
        tipo=TipoLedgerTransaction.ADMIN_ADJUSTMENT,
        moneda=str(data.get("moneda") or "eur"),
        lineas=lineas,
        actor_origen=_admin_codigo(),
        evento_origen="admin_adjust",
        referencia_stripe=str(data.get("referencia_stripe") or ""),
        metadata={"motivo": data.get("motivo") or ""},
    )
    return _http(r)


def _http(result: Dict[str, Any]) -> Tuple[Any, int]:
    if result.get("status") == "success":
        return jsonify(result), 200
    return jsonify(result), 400
