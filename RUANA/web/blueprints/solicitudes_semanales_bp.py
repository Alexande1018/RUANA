"""Blueprint de solicitudes semanales (aislado del flujo solicitudes de grupo)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import solicitud_semanal_service
from web.auth_decorators import (
    _aliado_codigo,
    require_admin,
    require_admin_or_cron,
    require_aliado,
)
from web.blueprints.invitacion_bp import _generar_codigo_invitacion

solicitudes_semanales_bp = Blueprint("solicitudes_semanales", __name__)


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


@solicitudes_semanales_bp.route("/api/solicitudes-semanales/bp-health", methods=["GET"])
def solicitudes_semanales_bp_health():
    return jsonify({"status": "ok", "dominio": "solicitudes_semanales"})


@solicitudes_semanales_bp.route("/api/solicitudes-semanales", methods=["GET", "POST"])
@require_aliado
def api_solicitudes_semanales():
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesión expirada"}), 401
    db = get_db()
    if request.method == "GET":
        result = solicitud_semanal_service.obtener_panel_por_codigo(db, codigo)
        if result.get("status") == "error":
            return jsonify({"error": result.get("message")}), 400
        return jsonify(result)
    data = request.get_json() or {}
    oficio = (data.get("oficio") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()
    es_personalizado = data.get("es_oficio_personalizado") in (
        True,
        1,
        "1",
        "true",
        "True",
    )
    result = solicitud_semanal_service.crear_solicitud_semanal(
        db,
        codigo,
        oficio,
        descripcion,
        es_oficio_personalizado=es_personalizado,
    )
    if result.get("status") != "success":
        return jsonify({"error": result.get("message", "Error")}), 400
    return jsonify({
        "ok": True,
        "id": result.get("id"),
        "already_existed": bool(result.get("already_existed")),
    }), 201


@solicitudes_semanales_bp.route(
    "/api/solicitudes-semanales/<int:solicitud_id>", methods=["PATCH"]
)
@require_aliado
def actualizar_solicitud_semanal(solicitud_id):
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesión expirada"}), 401
    data = request.get_json() or {}
    oficio = (data.get("oficio") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()
    es_personalizado = data.get("es_oficio_personalizado") in (
        True,
        1,
        "1",
        "true",
        "True",
    )
    db = get_db()
    result = solicitud_semanal_service.actualizar_solicitud_semanal(
        db,
        solicitud_id,
        codigo,
        oficio,
        descripcion,
        es_oficio_personalizado=es_personalizado,
    )
    if result.get("status") != "success":
        return jsonify({"error": result.get("message")}), 400
    return jsonify({"ok": True})


@solicitudes_semanales_bp.route(
    "/api/solicitudes-semanales/<int:solicitud_id>/puedo-ayudar",
    methods=["POST"],
)
@require_aliado
def puedo_ayudar_solicitud_semanal(solicitud_id):
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesión expirada"}), 401
    db = get_db()
    result = solicitud_semanal_service.responder_puedo_ayudar(db, solicitud_id, codigo)
    if result.get("status") != "success":
        return jsonify({"error": result.get("message")}), 400
    return jsonify(result)


@solicitudes_semanales_bp.route(
    "/api/solicitudes-semanales/<int:solicitud_id>/no-puedo-ayudar",
    methods=["POST"],
)
@require_aliado
def no_puedo_ayudar_solicitud_semanal(solicitud_id):
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesión expirada"}), 401
    db = get_db()
    result = solicitud_semanal_service.responder_no_puedo_ayudar(
        db, solicitud_id, codigo
    )
    if result.get("status") != "success":
        return jsonify({"error": result.get("message")}), 400
    return jsonify({"ok": True})


@solicitudes_semanales_bp.route(
    "/api/solicitudes-semanales/<int:solicitud_id>/conozco-alguien",
    methods=["POST"],
)
@require_aliado
def conozco_alguien_solicitud_semanal(solicitud_id):
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesión expirada"}), 401
    db = get_db()
    result = solicitud_semanal_service.responder_conozco_alguien(
        db,
        solicitud_id,
        codigo,
        _generar_codigo_invitacion,
    )
    if result.get("status") != "success":
        status = 409 if result.get("ya_en_grupo") else 400
        return jsonify(
            {
                "error": result.get("message"),
                "ya_en_grupo": result.get("ya_en_grupo"),
            }
        ), status
    return jsonify({"ok": True, "codigo": result.get("codigo")})


@solicitudes_semanales_bp.route(
    "/api/solicitudes-semanales/<int:solicitud_id>/interesados",
    methods=["GET"],
)
@require_aliado
def interesados_solicitud_semanal(solicitud_id):
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"error": "Sesión expirada"}), 401
    db = get_db()
    result = solicitud_semanal_service.listar_interesados(db, solicitud_id, codigo)
    if result.get("status") != "success":
        return jsonify({"error": result.get("message")}), 403
    return jsonify(result)


@solicitudes_semanales_bp.route(
    "/api/admin/solicitudes-semanales", methods=["GET"]
)
@require_admin
def admin_solicitudes_semanales():
    db = get_db()
    limite = request.args.get("limite", 300, type=int)
    result = solicitud_semanal_service.listar_admin(db, limite=limite)
    if result.get("status") != "success":
        return jsonify({"error": result.get("message")}), 500
    return jsonify(result)


@solicitudes_semanales_bp.route(
    "/api/solicitudes-semanales/expirar", methods=["POST"]
)
@require_admin_or_cron
def expirar_solicitudes_semanales():
    db = get_db()
    result = solicitud_semanal_service.expirar_solicitudes_vencidas(db)
    if result.get("status") != "success":
        return jsonify({"error": result.get("message")}), 500
    return jsonify({"ok": True})
