"""Blueprint del panel administrativo financiero (FASE 09). Lectura agregada + alertas."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.financial_admin_authorization import (
    AUDIT_VIEW,
    CONFLICTS_VIEW,
    DASHBOARD_VIEW,
    DISPUTES_VIEW,
    LEDGER_VIEW,
    PAYMENTS_VIEW,
    RECONCILIATION_VIEW,
    REFUNDS_VIEW,
    TRANSFERS_VIEW,
)
from core.services import financial_admin_service as fas
from web.auth_decorators import _admin_codigo, require_financial_admin_permission

financial_admin_bp = Blueprint("financial_admin", __name__)

_BASE = "/api/admin/financial"
_BASE_ES = "/api/admin/finanzas"


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _query_int(name: str, default: int, *, min_v: int = 0, max_v: int = 200) -> int:
    try:
        val = int(request.args.get(name, default))
    except (TypeError, ValueError):
        val = default
    return max(min_v, min(val, max_v))


@financial_admin_bp.route(f"{_BASE}/bp-health", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/bp-health", methods=["GET"])
def financial_admin_bp_health():
    return jsonify({"status": "ok", "dominio": "financial_admin"})


@financial_admin_bp.route(f"{_BASE}/dashboard", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/panel", methods=["GET"])
@require_financial_admin_permission(DASHBOARD_VIEW)
def dashboard():
    return jsonify(fas.obtener_dashboard(get_db()))


@financial_admin_bp.route(f"{_BASE}/alerts", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/alertas", methods=["GET"])
@require_financial_admin_permission(DASHBOARD_VIEW)
def alertas():
    return jsonify(fas.listar_alertas(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
    ))


@financial_admin_bp.route(f"{_BASE}/alerts/<path:alert_key>/resolve", methods=["POST"])
@financial_admin_bp.route(f"{_BASE_ES}/alertas/<path:alert_key>/resolve", methods=["POST"])
@require_financial_admin_permission(DASHBOARD_VIEW)
def resolver_alerta(alert_key: str):
    data = request.get_json(silent=True) or {}
    result = fas.resolver_alerta(
        get_db(),
        alert_key=alert_key,
        motivo=(data.get("motivo") or "").strip(),
        actor=_admin_codigo() or "admin",
        permiso=DASHBOARD_VIEW,
    )
    return _http(result)


@financial_admin_bp.route(f"{_BASE}/payments", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/pagos", methods=["GET"])
@require_financial_admin_permission(PAYMENTS_VIEW)
def payments():
    contacto_raw = request.args.get("contacto_id")
    contacto_id = int(contacto_raw) if contacto_raw and contacto_raw.isdigit() else None
    return jsonify(fas.listar_pagos(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        estado=request.args.get("estado", ""),
        q=request.args.get("q", ""),
        contacto_id=contacto_id,
    ))


@financial_admin_bp.route(f"{_BASE}/transfers", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/transferencias", methods=["GET"])
@require_financial_admin_permission(TRANSFERS_VIEW)
def transfers():
    return jsonify(fas.listar_transfers(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        estado=request.args.get("estado", ""),
        q=request.args.get("q", ""),
    ))


@financial_admin_bp.route(f"{_BASE}/refunds", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/reembolsos", methods=["GET"])
@require_financial_admin_permission(REFUNDS_VIEW)
def refunds():
    return jsonify(fas.listar_refunds(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        estado=request.args.get("estado", ""),
        q=request.args.get("q", ""),
    ))


@financial_admin_bp.route(f"{_BASE}/disputes", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/disputas", methods=["GET"])
@require_financial_admin_permission(DISPUTES_VIEW)
def disputes():
    return jsonify(fas.listar_disputes(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        estado=request.args.get("estado", ""),
        q=request.args.get("q", ""),
    ))


@financial_admin_bp.route(f"{_BASE}/conflicts", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/conflictos", methods=["GET"])
@require_financial_admin_permission(CONFLICTS_VIEW)
def conflicts():
    return jsonify(fas.listar_conflicts(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        estado=request.args.get("estado", ""),
        q=request.args.get("q", ""),
    ))


@financial_admin_bp.route(f"{_BASE}/reconciliation", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/reconciliacion", methods=["GET"])
@require_financial_admin_permission(RECONCILIATION_VIEW)
def reconciliation():
    return jsonify(fas.listar_reconciliation(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        estado=request.args.get("estado", ""),
    ))


@financial_admin_bp.route(f"{_BASE}/ledger", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/libro-mayor", methods=["GET"])
@require_financial_admin_permission(LEDGER_VIEW)
def ledger():
    return jsonify(fas.listar_ledger(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        estado=request.args.get("estado", ""),
    ))


@financial_admin_bp.route(f"{_BASE}/webhooks", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/webhooks", methods=["GET"])
@require_financial_admin_permission(AUDIT_VIEW)
def webhooks():
    return jsonify(fas.listar_webhooks(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        solo_fallidos=request.args.get("solo_fallidos", "1"),
    ))


@financial_admin_bp.route(f"{_BASE}/audit", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/auditoria", methods=["GET"])
@require_financial_admin_permission(AUDIT_VIEW)
def audit():
    return jsonify(fas.listar_audit(
        get_db(),
        limit=_query_int("limit", 50, min_v=1),
        offset=_query_int("offset", 0),
        entidad=request.args.get("entidad", ""),
        q=request.args.get("q", ""),
    ))


@financial_admin_bp.route(f"{_BASE}/operation/<int:contacto_id>", methods=["GET"])
@financial_admin_bp.route(f"{_BASE_ES}/operacion/<int:contacto_id>", methods=["GET"])
@require_financial_admin_permission(PAYMENTS_VIEW)
def operacion(contacto_id: int):
    result = fas.obtener_operacion(get_db(), contacto_id)
    if result.get("status") != "success":
        return jsonify(result), 404
    return jsonify(result)


def _http(result: Dict[str, Any]) -> Tuple[Any, int]:
    if result.get("status") == "success":
        return jsonify(result), 200
    return jsonify(result), 400
