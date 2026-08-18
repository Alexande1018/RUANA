"""Blueprint REST de reconciliación financiera avanzada (FASE 07). Solo observación."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.reconciliation_authorization import RECON_EXECUTE, RECON_RESOLVE, RECON_VIEW
from core.services import financial_reconciliation_advanced_service as fras
from web.auth_decorators import _admin_codigo, require_reconciliation_permission

financial_reconciliation_bp = Blueprint("financial_reconciliation", __name__)

_BASE_EN = "/api/admin/financial-reconciliation"
_BASE_ES = "/api/admin/reconciliacion-financiera"


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _json_body() -> Dict[str, Any]:
    return request.get_json(silent=True) or {}


def _idempotency_key(data: Dict[str, Any]) -> str:
    header = (request.headers.get("Idempotency-Key") or "").strip()
    body = (data.get("idempotency_key") or "").strip()
    return header or body


@financial_reconciliation_bp.route(f"{_BASE_EN}/bp-health", methods=["GET"])
@financial_reconciliation_bp.route(f"{_BASE_ES}/bp-health", methods=["GET"])
def financial_reconciliation_bp_health():
    return jsonify({"status": "ok", "dominio": "financial_reconciliation"})


@financial_reconciliation_bp.route(f"{_BASE_EN}/contacto/<int:contacto_id>", methods=["POST"])
@financial_reconciliation_bp.route(f"{_BASE_ES}/contacto/<int:contacto_id>", methods=["POST"])
@require_reconciliation_permission(RECON_EXECUTE)
def reconciliar_contacto(contacto_id: int):
    data = _json_body()
    key = _idempotency_key(data) or f"api-recon-contacto-{contacto_id}"
    result = fras.reconciliar_contacto_avanzado(
        get_db(), contacto_id,
        actor=_admin_codigo(),
        permiso_usado=RECON_EXECUTE,
        idempotency_key=key,
        motivo=(data.get("motivo") or "").strip(),
    )
    return _http(result)


@financial_reconciliation_bp.route(f"{_BASE_EN}/payment-intent/<payment_intent_id>", methods=["POST"])
@financial_reconciliation_bp.route(f"{_BASE_ES}/payment-intent/<payment_intent_id>", methods=["POST"])
@require_reconciliation_permission(RECON_EXECUTE)
def reconciliar_payment_intent(payment_intent_id: str):
    data = _json_body()
    key = _idempotency_key(data) or f"api-recon-pi-{payment_intent_id}"
    result = fras.reconciliar_payment_intent(
        get_db(), payment_intent_id,
        actor=_admin_codigo(),
        permiso_usado=RECON_EXECUTE,
        idempotency_key=key,
    )
    return _http(result)


@financial_reconciliation_bp.route(f"{_BASE_EN}/transfer/<transfer_id>", methods=["POST"])
@financial_reconciliation_bp.route(f"{_BASE_ES}/transfer/<transfer_id>", methods=["POST"])
@require_reconciliation_permission(RECON_EXECUTE)
def reconciliar_transfer(transfer_id: str):
    data = _json_body()
    key = _idempotency_key(data) or f"api-recon-tr-{transfer_id}"
    result = fras.reconciliar_transfer(
        get_db(), transfer_id,
        actor=_admin_codigo(),
        permiso_usado=RECON_EXECUTE,
        idempotency_key=key,
    )
    return _http(result)


@financial_reconciliation_bp.route(f"{_BASE_EN}/lote", methods=["POST"])
@financial_reconciliation_bp.route(f"{_BASE_ES}/lote", methods=["POST"])
@require_reconciliation_permission(RECON_EXECUTE)
def ejecutar_lote():
    data = _json_body()
    try:
        limit = int(data.get("limit") or 50)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "limit inválido"}), 400
    limit = max(1, min(limit, 200))
    result = fras.ejecutar_lote(
        get_db(), limit=limit,
        actor=_admin_codigo(),
        permiso_usado=RECON_EXECUTE,
    )
    return _http(result)


@financial_reconciliation_bp.route(f"{_BASE_EN}/ejecuciones/<int:execution_id>/resolver", methods=["POST"])
@financial_reconciliation_bp.route(f"{_BASE_ES}/ejecuciones/<int:execution_id>/resolver", methods=["POST"])
@require_reconciliation_permission(RECON_RESOLVE)
def resolver_ejecucion(execution_id: int):
    data = _json_body()
    motivo = (data.get("motivo") or "").strip()
    if not motivo:
        return jsonify({"status": "error", "message": "motivo obligatorio"}), 400
    result = fras.resolver_ejecucion(
        get_db(), execution_id,
        actor=_admin_codigo(),
        permiso_usado=RECON_RESOLVE,
        motivo=motivo,
    )
    return _http(result)


@financial_reconciliation_bp.route(f"{_BASE_EN}/ejecuciones/<int:execution_id>", methods=["GET"])
@financial_reconciliation_bp.route(f"{_BASE_ES}/ejecuciones/<int:execution_id>", methods=["GET"])
@require_reconciliation_permission(RECON_VIEW)
def obtener_ejecucion(execution_id: int):
    db = get_db()
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            from core.repositories.financial_reconciliation_advanced_repo import (
                FinancialReconciliationAdvancedRepo,
            )
            row = FinancialReconciliationAdvancedRepo().select_por_id(cursor, execution_id)
        finally:
            conn.close()
    if not row:
        return jsonify({"status": "error", "message": "Ejecución no encontrada"}), 404
    return jsonify({"status": "success", "ejecucion": row}), 200


def _http(result: Dict[str, Any]) -> Tuple[Any, int]:
    if result.get("status") == "success":
        return jsonify(result), 200
    if result.get("message") == "Contacto no encontrado":
        return jsonify(result), 404
    return jsonify(result), 400
