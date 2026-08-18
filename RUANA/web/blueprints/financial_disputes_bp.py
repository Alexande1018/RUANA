"""Blueprint REST de disputas Stripe (FASE 06)."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.dispute_authorization import (
    DISPUTE_ADD_EVIDENCE,
    DISPUTE_INVESTIGATE,
    DISPUTE_SUBMIT_EVIDENCE,
    DISPUTE_VIEW,
)
from core.services import financial_dispute_service as fds
from web.auth_decorators import _admin_codigo, require_dispute_permission

financial_disputes_bp = Blueprint("financial_disputes", __name__)

_BASE_EN = "/api/admin/financial-disputes"
_BASE_ES = "/api/admin/disputas-financieras"


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


@financial_disputes_bp.route(f"{_BASE_EN}/bp-health", methods=["GET"])
@financial_disputes_bp.route(f"{_BASE_ES}/bp-health", methods=["GET"])
def financial_disputes_bp_health():
    return jsonify({"status": "ok", "dominio": "financial_disputes"})


@financial_disputes_bp.route(f"{_BASE_EN}/<int:dispute_id>", methods=["GET"])
@financial_disputes_bp.route(f"{_BASE_ES}/<int:dispute_id>", methods=["GET"])
@require_dispute_permission(DISPUTE_VIEW)
def detalle_disputa(dispute_id: int):
    result = fds.obtener_disputa(get_db(), dispute_id)
    return jsonify(result), 200 if result.get("status") == "success" else 404


@financial_disputes_bp.route(f"{_BASE_EN}/contacto/<int:contacto_id>", methods=["GET"])
@financial_disputes_bp.route(f"{_BASE_ES}/contacto/<int:contacto_id>", methods=["GET"])
@require_dispute_permission(DISPUTE_VIEW)
def listar_por_contacto(contacto_id: int):
    result = fds.listar_por_contacto(get_db(), contacto_id)
    return jsonify(result), 200


@financial_disputes_bp.route(f"{_BASE_EN}/<int:dispute_id>/transicion", methods=["POST"])
@financial_disputes_bp.route(f"{_BASE_ES}/<int:dispute_id>/transicion", methods=["POST"])
@require_dispute_permission(DISPUTE_INVESTIGATE)
def transicion_disputa(dispute_id: int):
    data = _json_body()
    estado = (data.get("estado_interno") or "").strip()
    if not estado:
        return jsonify({"status": "error", "message": "estado_interno obligatorio"}), 400
    result = fds.transicionar_estado_interno(
        get_db(), dispute_id, estado_nuevo=estado, actor=_admin_codigo(),
    )
    return _http(result)


@financial_disputes_bp.route(f"{_BASE_EN}/<int:dispute_id>/evidencias", methods=["POST"])
@financial_disputes_bp.route(f"{_BASE_ES}/<int:dispute_id>/evidencias", methods=["POST"])
@require_dispute_permission(DISPUTE_ADD_EVIDENCE)
def agregar_evidencia(dispute_id: int):
    data = _json_body()
    tipo = (data.get("tipo") or "").strip()
    referencia = (data.get("referencia") or "").strip()
    if not tipo:
        return jsonify({"status": "error", "message": "tipo obligatorio"}), 400
    result = fds.agregar_evidencia(
        get_db(), dispute_id, tipo=tipo, referencia=referencia, actor=_admin_codigo(),
    )
    return _http(result)


@financial_disputes_bp.route(f"{_BASE_EN}/<int:dispute_id>/enviar-evidencia", methods=["POST"])
@financial_disputes_bp.route(f"{_BASE_ES}/<int:dispute_id>/enviar-evidencia", methods=["POST"])
@require_dispute_permission(DISPUTE_SUBMIT_EVIDENCE)
def enviar_evidencia(dispute_id: int):
    data = _json_body()
    key = _idempotency_key(data)
    result = fds.enviar_evidencia_stripe(
        get_db(), dispute_id,
        actor=_admin_codigo(),
        evidence_payload=data.get("evidence") or {},
        idempotency_key=key,
    )
    return _http(result)


@financial_disputes_bp.route(f"{_BASE_EN}/<int:dispute_id>/vincular-conflicto", methods=["POST"])
@financial_disputes_bp.route(f"{_BASE_ES}/<int:dispute_id>/vincular-conflicto", methods=["POST"])
@require_dispute_permission(DISPUTE_INVESTIGATE)
def vincular_conflicto(dispute_id: int):
    data = _json_body()
    conflicto_id = data.get("conflicto_id")
    if not conflicto_id:
        return jsonify({"status": "error", "message": "conflicto_id obligatorio"}), 400
    result = fds.vincular_conflicto(
        get_db(), dispute_id, int(conflicto_id), actor=_admin_codigo(),
    )
    return _http(result)


def _http(result: Dict[str, Any]) -> Tuple[Any, int]:
    if result.get("status") == "success":
        return jsonify(result), 200
    if result.get("bloqueo"):
        return jsonify(result), 409
    return jsonify(result), 400
