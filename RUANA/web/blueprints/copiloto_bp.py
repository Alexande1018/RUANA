"""Blueprint del Copiloto RUANA (asistente del aliado y del admin).

Rutas del aliado:
  GET  /api/aliado/copiloto/estado     → saludo, jugadas y capacidad de IA
  GET  /api/aliado/copiloto/jugadas    → solo las jugadas (para tarjetas)
  POST /api/aliado/copiloto/mensaje    → un turno de conversación
  POST /api/aliado/copiloto/redactar   → invitación / derivación lista para enviar

Rutas del administrador:
  GET  /api/admin/copiloto/estado      → saludo, jugadas de la red y modo IA
  POST /api/admin/copiloto/mensaje     → un turno de conversación

Todas exigen sesión; el código de aliado sale de la sesión, nunca del body.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import copiloto_admin, copiloto_llm, copiloto_service
from web.auth_decorators import _aliado_codigo, require_admin, require_aliado

logger = logging.getLogger(__name__)

copiloto_bp = Blueprint("copiloto", __name__)


def get_db():
    """Respeta el get_db monkeypatcheado en la app, igual que el resto de blueprints."""
    import sys

    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


@copiloto_bp.route("/api/aliado/copiloto/bp-health", methods=["GET"])
def copiloto_bp_health():
    return jsonify({"status": "ok", "blueprint": "copiloto"}), 200


@copiloto_bp.route("/api/aliado/copiloto/estado", methods=["GET"])
@require_aliado
def copiloto_estado():
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    try:
        datos = copiloto_service.estado(get_db(), codigo)
    except Exception as exc:  # pragma: no cover - red de seguridad
        logger.exception("Copiloto: fallo construyendo el estado")
        return jsonify({"status": "error", "message": str(exc)}), 500
    return jsonify({"status": "success", **datos}), 200


@copiloto_bp.route("/api/aliado/copiloto/jugadas", methods=["GET"])
@require_aliado
def copiloto_jugadas():
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    try:
        datos = copiloto_service.jugadas(get_db(), codigo)
    except Exception as exc:  # pragma: no cover
        logger.exception("Copiloto: fallo calculando jugadas")
        return jsonify({"status": "error", "message": str(exc)}), 500
    return jsonify(datos), 200


@copiloto_bp.route("/api/aliado/copiloto/mensaje", methods=["POST"])
@require_aliado
def copiloto_mensaje():
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401

    payload = request.get_json(silent=True) or {}
    mensaje = payload.get("mensaje") or payload.get("texto") or ""
    historial = payload.get("historial")
    try:
        datos = copiloto_service.conversar(get_db(), codigo, mensaje, historial)
    except Exception as exc:  # pragma: no cover
        logger.exception("Copiloto: fallo en la conversación")
        return jsonify({"status": "error", "message": str(exc)}), 500

    codigo_http = 200 if datos.get("status") == "success" else 400
    return jsonify(datos), codigo_http


@copiloto_bp.route("/api/aliado/copiloto/redactar", methods=["POST"])
@require_aliado
def copiloto_redactar():
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401

    payload = request.get_json(silent=True) or {}
    try:
        datos = copiloto_service.redactar(
            get_db(),
            codigo,
            payload.get("tipo") or "invitacion",
            oficio=payload.get("oficio") or "",
            notas=payload.get("notas") or "",
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Copiloto: fallo redactando")
        return jsonify({"status": "error", "message": str(exc)}), 500

    codigo_http = 200 if datos.get("status") == "success" else 400
    return jsonify(datos), codigo_http


@copiloto_bp.route("/api/aliado/copiloto/capacidades", methods=["GET"])
@require_aliado
def copiloto_capacidades():
    """Modo del copiloto para esta sesión: IA o asistente determinista."""
    return jsonify({"status": "success", **copiloto_llm.estado_publico()}), 200


# ---------------------------------------------------------------------------
# Copiloto del administrador
# ---------------------------------------------------------------------------

@copiloto_bp.route("/api/admin/copiloto/estado", methods=["GET"])
@require_admin
def copiloto_admin_estado():
    try:
        datos = copiloto_admin.estado(get_db())
    except Exception as exc:  # pragma: no cover - red de seguridad
        logger.exception("Copiloto admin: fallo construyendo el estado")
        return jsonify({"status": "error", "message": str(exc)}), 500
    return jsonify({"status": "success", **datos}), 200


@copiloto_bp.route("/api/admin/copiloto/mensaje", methods=["POST"])
@require_admin
def copiloto_admin_mensaje():
    payload = request.get_json(silent=True) or {}
    mensaje = payload.get("mensaje") or payload.get("texto") or ""
    historial = payload.get("historial")
    try:
        datos = copiloto_admin.conversar(get_db(), mensaje, historial)
    except Exception as exc:  # pragma: no cover
        logger.exception("Copiloto admin: fallo en la conversación")
        return jsonify({"status": "error", "message": str(exc)}), 500
    codigo_http = 200 if datos.get("status") == "success" else 400
    return jsonify(datos), codigo_http
