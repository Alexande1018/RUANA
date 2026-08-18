"""Blueprint REST de reembolsos financieros (FASE 05 + FASE 10 aprobaciones)."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.financial_resource_guard import validar_contacto_existe
from core.financial_security_authorization import (
    REFUND_AUTHORIZE,
    REFUND_EXECUTE,
    REFUND_REQUEST,
)
from core.refund_authorization import REFUND_VIEW
from core.services import financial_action_approval_service as faas
from core.services import financial_refund_service as frs
from web.auth_decorators import _admin_codigo, require_refund_permission
from web.financial_rate_limit import limit_financial_mutation

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
    db = get_db()
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            ok, _ = validar_contacto_existe(cursor, contacto_id)
        finally:
            conn.close()
    if not ok:
        return jsonify({"status": "error", "message": "Contacto no encontrado"}), 404
    result = frs.calcular_importe_disponible_refund_cents(db, contacto_id)
    return jsonify(result), 200 if result.get("status") == "success" else 400


@financial_refunds_bp.route(f"{_BASE_EN}/solicitar", methods=["POST"])
@financial_refunds_bp.route(f"{_BASE_ES}/solicitar", methods=["POST"])
@require_refund_permission(REFUND_REQUEST)
@limit_financial_mutation
def solicitar_reembolso():
    data = _json_body()
    contacto_id = data.get("contacto_id")
    if not contacto_id:
        return jsonify({"status": "error", "message": "contacto_id obligatorio"}), 400
    key = _idempotency_key(data)
    if not key:
        return jsonify({"status": "error", "message": "idempotency_key obligatoria"}), 400
    try:
        importe = int(data.get("importe_solicitado_cents") or 0)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "importe_solicitado_cents inválido"}), 400
    db = get_db()
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            ok, _ = validar_contacto_existe(cursor, int(contacto_id))
        finally:
            conn.close()
    if not ok:
        return jsonify({"status": "error", "message": "Contacto no encontrado"}), 404
    result = faas.solicitar_accion(
        db,
        action_type=faas.ACTION_REFUND_EXECUTE,
        contacto_id=int(contacto_id),
        actor=_admin_codigo() or "admin",
        permiso=REFUND_REQUEST,
        importe_cents=importe,
        currency=str(data.get("moneda") or "eur"),
        motivo=(data.get("motivo") or "").strip(),
        idempotency_key=key,
        metadata={"causa_ruana": data.get("causa_ruana")},
    )
    return _http(result)


@financial_refunds_bp.route(f"{_BASE_EN}/aprobaciones/<int:approval_id>/autorizar", methods=["POST"])
@financial_refunds_bp.route(f"{_BASE_ES}/aprobaciones/<int:approval_id>/autorizar", methods=["POST"])
@require_refund_permission(REFUND_AUTHORIZE)
@limit_financial_mutation
def autorizar_reembolso(approval_id: int):
    data = _json_body()
    result = faas.autorizar_accion(
        get_db(), approval_id,
        actor=_admin_codigo() or "admin",
        permiso=REFUND_AUTHORIZE,
        motivo=(data.get("motivo") or "").strip(),
    )
    if result.get("code") == "version_conflict":
        return jsonify(result), 409
    if result.get("code") == "separation_of_duties":
        return jsonify(result), 403
    return _http(result)


@financial_refunds_bp.route(f"{_BASE_EN}/aprobaciones/<int:approval_id>/rechazar", methods=["POST"])
@financial_refunds_bp.route(f"{_BASE_ES}/aprobaciones/<int:approval_id>/rechazar", methods=["POST"])
@require_refund_permission(REFUND_AUTHORIZE)
@limit_financial_mutation
def rechazar_reembolso(approval_id: int):
    data = _json_body()
    result = faas.rechazar_accion(
        get_db(), approval_id,
        actor=_admin_codigo() or "admin",
        permiso=REFUND_AUTHORIZE,
        motivo=(data.get("motivo") or "").strip(),
    )
    if result.get("code") == "version_conflict":
        return jsonify(result), 409
    return _http(result)


@financial_refunds_bp.route(f"{_BASE_EN}/aprobaciones/pendientes", methods=["GET"])
@financial_refunds_bp.route(f"{_BASE_ES}/aprobaciones/pendientes", methods=["GET"])
@require_refund_permission(REFUND_AUTHORIZE)
def listar_aprobaciones_pendientes():
    return jsonify(faas.listar_pendientes(get_db(), limit=int(request.args.get("limit") or 50)))


@financial_refunds_bp.route(f"{_BASE_EN}/ejecutar", methods=["POST"])
@financial_refunds_bp.route(f"{_BASE_ES}/ejecutar", methods=["POST"])
@require_refund_permission(REFUND_EXECUTE)
@limit_financial_mutation
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
    approval_id = data.get("approval_id")
    db = get_db()
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            ok, _ = validar_contacto_existe(cursor, int(contacto_id))
        finally:
            conn.close()
    if not ok:
        return jsonify({"status": "error", "message": "Contacto no encontrado"}), 404
    result = frs.ejecutar_reembolso(
        db, int(contacto_id),
        importe_solicitado_cents=importe,
        actor=_admin_codigo(),
        idempotency_key=key,
        permiso_usado=REFUND_EXECUTE,
        causa_ruana=causa,
        conflicto_id=int(data["conflicto_id"]) if data.get("conflicto_id") else None,
        parte_ejecutada_cents=parte,
        conservar_comision_total=bool(data.get("conservar_comision_total")),
        approval_id=int(approval_id) if approval_id else None,
    )
    return _http(result)


@financial_refunds_bp.route(
    f"/api/admin/financial-conflicts/<int:conflict_id>/ejecutar-reembolso", methods=["POST"],
)
@financial_refunds_bp.route(
    f"/api/admin/conflictos-financieros/<int:conflict_id>/ejecutar-reembolso", methods=["POST"],
)
@require_refund_permission(REFUND_EXECUTE)
@limit_financial_mutation
def ejecutar_reembolso_conflicto(conflict_id: int):
    data = _json_body()
    key = _idempotency_key(data)
    if not key:
        return jsonify({"status": "error", "message": "idempotency_key obligatoria"}), 400
    try:
        parte = int(data.get("parte_ejecutada_cents") or 0)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "parte_ejecutada_cents inválido"}), 400
    approval_id = data.get("approval_id")
    result = frs.ejecutar_reembolso_desde_conflicto(
        get_db(), conflict_id,
        actor=_admin_codigo(),
        idempotency_key=key,
        permiso_usado=REFUND_EXECUTE,
        causa_ruana=(data.get("causa_ruana") or "").strip(),
        parte_ejecutada_cents=parte,
        conservar_comision_total=bool(data.get("conservar_comision_total")),
        approval_id=int(approval_id) if approval_id else None,
    )
    return _http(result)


def _http(result: Dict[str, Any]) -> Tuple[Any, int]:
    if result.get("status") == "success":
        return jsonify(result), 200
    if result.get("code") == "version_conflict":
        return jsonify(result), 409
    if result.get("code") in ("separation_of_duties", "idor"):
        return jsonify(result), 403
    if result.get("bloqueo"):
        return jsonify(result), 409
    if result.get("message") == "approval_id obligatorio cuando RUANA_FINANCIAL_REQUIRE_APPROVAL=1":
        return jsonify(result), 400
    return jsonify(result), 400
