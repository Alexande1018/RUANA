"""Blueprint REST de reembolsos financieros (FASE 05)."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.refund_authorization import REFUND_EXECUTE, REFUND_VIEW
from core.services import financial_refund_service as frs
from web.auth_decorators import _admin_codigo, require_refund_permission

financial_refunds_bp = Blueprint("financial_refunds", __name__)

_BASE_EN = "/api/admin/financial-refunds"
_BASE_ES = "/api/admin/reembolsos-financieros"


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


@financial_refunds_bp.route(f"{_BASE_EN}/bp-health", methods=["GET"])
@financial_refunds_bp.route(f"{_BASE_ES}/bp-health", methods=["GET"])
def financial_refunds_bp_health():
    return jsonify({"status": "ok", "dominio": "financial_refunds"})


@financial_refunds_bp.route(f"{_BASE_EN}/disponible/<int:contacto_id>", methods=["GET"])
@financial_refunds_bp.route(f"{_BASE_ES}/disponible/<int:contacto_id>", methods=["GET"])
@require_refund_permission(REFUND_VIEW)
def importe_disponible(contacto_id: int):
    result = frs.calcular_importe_disponible_refund_cents(get_db(), contacto_id)
    return jsonify(result), 200 if result.get("status") == "success" else 400


@financial_refunds_bp.route(f"{_BASE_EN}/ejecutar", methods=["POST"])
@financial_refunds_bp.route(f"{_BASE_ES}/ejecutar", methods=["POST"])
@require_refund_permission(REFUND_EXECUTE)
def ejecutar_reembolso():
    data = _json_body()
    contacto_id = data.get("contacto_id")
    if not contacto_id:
        return jsonify({"status": "error", "message": "contacto_id obligatorio"}), 400
    causa = (data.get("causa_ruana") or "").strip()
    if not causa:
        return jsonify({"status": "error", "message": "causa_ruana obligatoria"}), 400
    key = _idempotency_key(data)
    if not key:
        return jsonify({"status": "error", "message": "idempotency_key obligatoria"}), 400
    try:
        importe = int(data.get("importe_solicitado_cents") or 0)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "importe_solicitado_cents inválido"}), 400
    try:
        parte = int(data.get("parte_ejecutada_cents") or 0)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "parte_ejecutada_cents inválido"}), 400
    result = frs.ejecutar_reembolso(
        get_db(), int(contacto_id),
        importe_solicitado_cents=importe,
        actor=_admin_codigo(),
        idempotency_key=key,
        permiso_usado=REFUND_EXECUTE,
        causa_ruana=causa,
        conflicto_id=int(data["conflicto_id"]) if data.get("conflicto_id") else None,
        parte_ejecutada_cents=parte,
        conservar_comision_total=bool(data.get("conservar_comision_total")),
    )
    return _http(result)


@financial_refunds_bp.route(
    f"/api/admin/financial-conflicts/<int:conflict_id>/ejecutar-reembolso", methods=["POST"],
)
@financial_refunds_bp.route(
    f"/api/admin/conflictos-financieros/<int:conflict_id>/ejecutar-reembolso", methods=["POST"],
)
@require_refund_permission(REFUND_EXECUTE)
def ejecutar_reembolso_conflicto(conflict_id: int):
    data = _json_body()
    key = _idempotency_key(data)
    if not key:
        return jsonify({"status": "error", "message": "idempotency_key obligatoria"}), 400
    try:
        parte = int(data.get("parte_ejecutada_cents") or 0)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "parte_ejecutada_cents inválido"}), 400
    result = frs.ejecutar_reembolso_desde_conflicto(
        get_db(), conflict_id,
        actor=_admin_codigo(),
        idempotency_key=key,
        permiso_usado=REFUND_EXECUTE,
        causa_ruana=(data.get("causa_ruana") or "").strip(),
        parte_ejecutada_cents=parte,
        conservar_comision_total=bool(data.get("conservar_comision_total")),
    )
    return _http(result)


def _http(result: Dict[str, Any]) -> Tuple[Any, int]:
    if result.get("status") == "success":
        return jsonify(result), 200
    if result.get("bloqueo"):
        return jsonify(result), 409
    return jsonify(result), 400
