"""Blueprint de automatización y monitorización financiera (FASE 11)."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.financial_automation_authorization import AUTOMATION_EXECUTE, MONITORING_VIEW
from core.services import financial_automation_service as fas
from web.auth_decorators import (
    _admin_codigo,
    _cron_secret_valid,
    require_admin_escritura_or_cron,
    require_automation_permission,
)

financial_automation_bp = Blueprint("financial_automation", __name__)

_BASE = "/api/admin/financial-automation"
_BASE_ES = "/api/admin/automatizacion-financiera"


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _actor() -> str:
    if _cron_secret_valid():
        return "cron"
    return _admin_codigo() or "admin"


def _query_int(name: str, default: int, *, min_v: int = 1, max_v: int = 200) -> int:
    try:
        val = int(request.args.get(name, default))
    except (TypeError, ValueError):
        val = default
    return max(min_v, min(val, max_v))


@financial_automation_bp.route(f"{_BASE}/bp-health", methods=["GET"])
@financial_automation_bp.route(f"{_BASE_ES}/bp-health", methods=["GET"])
def financial_automation_bp_health():
    return jsonify({"status": "ok", "dominio": "financial_automation"})


@financial_automation_bp.route(f"{_BASE}/ejecutar-ciclo", methods=["POST"])
@financial_automation_bp.route(f"{_BASE_ES}/ejecutar-ciclo", methods=["POST"])
@require_admin_escritura_or_cron
@require_automation_permission(AUTOMATION_EXECUTE)
def ejecutar_ciclo():
    data = request.get_json(silent=True) or {}
    recon_limit = _query_int("recon_limit", int(data.get("recon_limit") or 20), min_v=1, max_v=100)
    incluir = data.get("incluir_reconciliacion", True)
    if isinstance(incluir, str):
        incluir = incluir.strip().lower() not in ("0", "false", "no")
    result = fas.ejecutar_ciclo_monitoreo(
        get_db(),
        actor=_actor(),
        permiso=AUTOMATION_EXECUTE,
        recon_limit=recon_limit,
        incluir_reconciliacion=bool(incluir),
    )
    return _http(result)


@financial_automation_bp.route(f"{_BASE}/reconciliar-lote", methods=["POST"])
@financial_automation_bp.route(f"{_BASE_ES}/reconciliar-lote", methods=["POST"])
@require_admin_escritura_or_cron
@require_automation_permission(AUTOMATION_EXECUTE)
def reconciliar_lote():
    data = request.get_json(silent=True) or {}
    limit = _query_int("limit", int(data.get("limit") or 20), min_v=1, max_v=100)
    result = fas.ejecutar_reconciliacion_periodica(
        get_db(), limit=limit, actor=_actor(), permiso=AUTOMATION_EXECUTE,
    )
    return _http(result)


@financial_automation_bp.route(f"{_BASE}/resumen", methods=["GET"])
@financial_automation_bp.route(f"{_BASE_ES}/resumen", methods=["GET"])
@require_automation_permission(MONITORING_VIEW)
def resumen():
    return jsonify(fas.obtener_resumen(get_db()))


@financial_automation_bp.route(f"{_BASE}/ejecuciones", methods=["GET"])
@financial_automation_bp.route(f"{_BASE_ES}/ejecuciones", methods=["GET"])
@require_automation_permission(MONITORING_VIEW)
def listar_ejecuciones():
    return jsonify(fas.listar_ejecuciones(
        get_db(),
        limit=_query_int("limit", 50),
        offset=_query_int("offset", 0, min_v=0),
    ))


@financial_automation_bp.route(f"{_BASE}/ejecuciones/<run_id>", methods=["GET"])
@financial_automation_bp.route(f"{_BASE_ES}/ejecuciones/<run_id>", methods=["GET"])
@require_automation_permission(MONITORING_VIEW)
def obtener_ejecucion(run_id: str):
    return jsonify(fas.obtener_ejecucion(get_db(), run_id))


@financial_automation_bp.route(f"{_BASE}/alertas", methods=["GET"])
@financial_automation_bp.route(f"{_BASE_ES}/alertas", methods=["GET"])
@require_automation_permission(MONITORING_VIEW)
def listar_alertas():
    return jsonify(fas.listar_alertas_persistidas(
        get_db(),
        limit=_query_int("limit", 50),
        offset=_query_int("offset", 0, min_v=0),
    ))


def _http(result: Dict[str, Any]) -> Tuple[Any, int]:
    if result.get("status") in ("success", "skipped"):
        return jsonify(result), 200
    return jsonify(result), 400
