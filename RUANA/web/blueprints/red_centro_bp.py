"""Blueprint del piloto reversible «Red Centro» (Madrid + Toledo).

Todo pasa por ``red_centro_service``. Sin ``RED_CENTRO_ENABLED=1`` las rutas
responden pero no activan nada y el aviso nunca se muestra.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import red_centro_service
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    require_admin,
    require_admin_escritura,
    require_aliado,
)

red_centro_bp = Blueprint("red_centro", __name__)


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
    result = dict(result or {})
    if result.get("status") != "success":
        code = int(result.pop("http", 400) or 400)
        return jsonify({"status": "error", "error": result.get("message"), "message": result.get("message")}), code
    result.pop("http", None)
    return jsonify(result), ok_status


# --- Admin --------------------------------------------------------------------

@red_centro_bp.route("/api/admin/red-centro", methods=["GET"])
@require_admin
def admin_red_centro_estado():
    try:
        return _respuesta(red_centro_service.estado(get_db()))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@red_centro_bp.route("/api/admin/red-centro/activar", methods=["POST"])
@require_admin_escritura
def admin_red_centro_activar():
    try:
        return _respuesta(red_centro_service.activar(get_db(), _admin_codigo() or ""))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@red_centro_bp.route("/api/admin/red-centro/revertir", methods=["POST"])
@require_admin_escritura
def admin_red_centro_revertir():
    try:
        return _respuesta(red_centro_service.revertir(get_db(), _admin_codigo() or ""))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@red_centro_bp.route("/api/admin/red-centro/plantilla-notificacion", methods=["GET"])
@require_admin
def admin_red_centro_plantilla():
    return jsonify({"status": "success", "plantilla": red_centro_service.plantilla_notificacion(),
                    "envio_masivo": False})


# --- Aliado (modal de bienvenida) -------------------------------------------------

@red_centro_bp.route("/api/aliado/red-centro/aviso", methods=["GET"])
@require_aliado
def aliado_red_centro_aviso():
    try:
        return _respuesta(red_centro_service.aviso_para_aliado(get_db(), _aliado_codigo()))
    except Exception:
        return jsonify({"status": "success", "mostrar": False})


@red_centro_bp.route("/api/aliado/red-centro/aviso", methods=["POST"])
@require_aliado
def aliado_red_centro_aviso_accion():
    data = request.get_json(silent=True) or {}
    try:
        return _respuesta(
            red_centro_service.registrar_accion_aviso(get_db(), _aliado_codigo(), data.get("accion") or "")
        )
    except Exception:
        return jsonify({"status": "error", "message": "No se pudo guardar."}), 500
