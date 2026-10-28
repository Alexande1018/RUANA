"""Blueprint de encargos externos («Encargo de RUANA»).

Flujo aparte, sin cobro: el admin crea el encargo y se lo asigna a un aliado;
el aliado lo acepta, lo rechaza o lo marca como hecho.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import encargo_externo_service
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    require_admin,
    require_admin_escritura,
    require_aliado,
)

encargos_externos_bp = Blueprint("encargos_externos", __name__)


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _respuesta(result, ok_status=200):
    if result.get("status") != "success":
        code = int(result.pop("http", 400) or 400)
        return jsonify({"status": "error", "error": result.get("message"), "message": result.get("message")}), code
    result.pop("http", None)
    return jsonify(result), ok_status


@encargos_externos_bp.route("/api/admin/encargos-externos", methods=["GET"])
@require_admin
def admin_listar_encargos_externos():
    estado = request.args.get("estado", "")
    try:
        limite = int(request.args.get("limite", 300))
    except (TypeError, ValueError):
        limite = 300
    return _respuesta(encargo_externo_service.listar_admin(get_db(), estado, limite))


@encargos_externos_bp.route("/api/admin/encargos-externos", methods=["POST"])
@require_admin_escritura
def admin_crear_encargo_externo():
    data = request.get_json(silent=True) or {}
    result = encargo_externo_service.crear_encargo_externo(
        get_db(), data, admin_codigo=_admin_codigo() or ""
    )
    return _respuesta(result, ok_status=201)


@encargos_externos_bp.route("/api/encargos-externos", methods=["GET"])
@require_aliado
def aliado_listar_encargos_externos():
    return _respuesta(encargo_externo_service.listar_para_aliado(get_db(), _aliado_codigo()))


@encargos_externos_bp.route(
    "/api/encargos-externos/<int:encargo_id>/<accion>", methods=["POST"]
)
@require_aliado
def aliado_cambiar_estado_encargo_externo(encargo_id, accion):
    data = request.get_json(silent=True) or {}
    result = encargo_externo_service.cambiar_estado(
        get_db(), encargo_id, _aliado_codigo(), accion, motivo=data.get("motivo") or ""
    )
    return _respuesta(result)
