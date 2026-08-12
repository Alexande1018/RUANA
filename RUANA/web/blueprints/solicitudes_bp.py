"""Blueprint de solicitudes de grupo (extraído de web/app.py).

Rutas /api/solicitudes* y mutación admin de atender.
Comportamiento y paths idénticos.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    require_admin_escritura,
    require_aliado,
)

solicitudes_bp = Blueprint("solicitudes", __name__)


def get_db():
    """Usa get_db del módulo app cargado (RUANA.web.app o web.app) para respetar monkeypatch."""
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


@solicitudes_bp.route("/api/solicitudes/bp-health", methods=["GET"])
def solicitudes_bp_health():
    """Ping ligero del dominio solicitudes."""
    return jsonify({"status": "ok", "dominio": "solicitudes"})


@solicitudes_bp.route("/api/solicitudes", methods=["GET", "POST"])
@require_aliado
def api_solicitudes():
    """GET — lista activas del grupo del aliado en sesión. POST body { oficio, descripcion } — crear."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesi?n expirada"}), 401
    if request.method == "GET":
        try:
            db = get_db()
            entrantes = db.listar_solicitudes_activas_por_codigo(codigo)
            propias = db.listar_solicitudes_propias_por_codigo(codigo)
            historial = db.listar_solicitudes_historial_grupo_por_codigo(codigo, limite=50)
            return jsonify(
                {
                    "entrantes": entrantes,
                    "propias": propias,
                    "historial": historial,
                }
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        data = request.get_json() or {}
        oficio = (data.get("oficio") or "").strip()
        descripcion = (data.get("descripcion") or "").strip()
        if not oficio:
            return jsonify({"error": "Oficio obligatorio"}), 400
        if not descripcion:
            return jsonify({"error": "Descripción obligatoria"}), 400
        if len(descripcion) < 5:
            return jsonify({"error": "La descripción debe tener al menos 5 caracteres"}), 400
        try:
            db = get_db()
            result = db.crear_solicitud_por_codigo(codigo, oficio, descripcion)
            if result.get("status") != "success":
                return jsonify({"error": result.get("message", "Error al crear solicitud")}), 400
            return jsonify({"ok": True, "id": result.get("id")}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@solicitudes_bp.route("/api/solicitudes/<int:solicitud_id>/atender", methods=["POST"])
@require_aliado
def atender_solicitud(solicitud_id):
    """
    POST /api/solicitudes/<id>/atender
    Marca atendida y registra al aliado en sesión como quien atendió.
    """
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesi?n expirada"}), 401
    try:
        db = get_db()
        result = db.atender_solicitud_por_id(solicitud_id, codigo)
        if result.get("status") != "success":
            return jsonify({"error": result.get("message", "Error al atender")}), 400
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@solicitudes_bp.route("/api/admin/solicitudes/<int:solicitud_id>/atender", methods=["POST"])
@require_admin_escritura
def admin_solicitud_atender(solicitud_id):
    """
    POST /api/admin/solicitudes/<id>/atender
    Marca la solicitud como atendida y registra al admin en sesión como "Atendido por" y "Atendido at".
    Sirve para rellenar columnas vacías o marcar pendientes como atendidas desde admin.
    """
    try:
        admin_codigo = _admin_codigo()
        db = get_db()
        result = db.marcar_solicitud_atendida_por_admin(solicitud_id, admin_codigo or "")
        if result.get("status") != "success":
            return jsonify({"status": "error", "message": result.get("message", "Error")}), 400
        return jsonify({"status": "success", "ok": True}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
