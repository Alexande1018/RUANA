"""Blueprint admin de solo lectura: todas las solicitudes con su detalle completo.

Une solicitudes semanales y solicitudes de conexión (todas las semanas y estados).
No modifica nada: solo GET, sin expirar ni tocar el flujo del aliado.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import admin_solicitudes_service
from web.auth_decorators import require_admin

admin_solicitudes_bp = Blueprint("admin_solicitudes", __name__)


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _respuesta(result):
    code = int(result.pop("http", 0) or 0)
    if result.get("status") != "success":
        msg = result.get("message") or "Error"
        return jsonify({"status": "error", "error": msg, "message": msg}), code or 400
    return jsonify(result), 200


@admin_solicitudes_bp.route("/api/admin/solicitudes-todas", methods=["GET"])
@require_admin
def admin_listar_solicitudes_todas():
    """GET /api/admin/solicitudes-todas?tipo=&estado=&grupo=&semana=&q=&limit=&offset=

    tipo: semanal | conexion | (vacío = las dos). grupo: id numérico o parte del nombre.
    semana: cualquier fecha YYYY-MM-DD (se usa el lunes de esa semana).
    """
    args = request.args
    result = admin_solicitudes_service.listar_todas(
        get_db(),
        tipo=args.get("tipo", ""),
        estado=args.get("estado", ""),
        grupo=args.get("grupo", ""),
        semana=args.get("semana", ""),
        q=args.get("q", ""),
        limite=args.get("limit", args.get("limite", admin_solicitudes_service.LIMITE_POR_DEFECTO)),
        offset=args.get("offset", 0),
    )
    return _respuesta(result)


@admin_solicitudes_bp.route(
    "/api/admin/solicitudes-todas/<tipo>/<int:solicitud_id>", methods=["GET"]
)
@require_admin
def admin_detalle_solicitud(tipo, solicitud_id):
    """GET /api/admin/solicitudes-todas/<semanal|conexion>/<id> — detalle completo."""
    return _respuesta(admin_solicitudes_service.obtener_detalle(get_db(), tipo, solicitud_id))
