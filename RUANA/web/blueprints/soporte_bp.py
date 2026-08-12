"""Blueprint centro de comunicación / soporte RUANA.

Rutas aliado + mutaciones admin. GETs admin listar también aquí
(se retiran de admin_bp para no duplicar). Contratos idénticos.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import admin_service, chat_service
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    require_admin,
    require_admin_escritura,
    require_aliado,
)

soporte_bp = Blueprint("soporte", __name__)

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


@soporte_bp.route("/api/soporte/bp-health", methods=["GET"])
def soporte_bp_health():
    return jsonify({"status": "ok", "dominio": "soporte"})


@soporte_bp.route('/api/admin/centro-comunicacion', methods=['GET'])
@require_admin
def admin_listar_centro_comunicacion():
    try:
        db = get_db()
        conversaciones = admin_service.listar_conversaciones_soporte_admin(
            db,
            aliado_codigo=request.args.get('aliado', ''),
            estado=request.args.get('estado', ''),
            solo_no_leidas=(request.args.get('solo_no_leidas', '0') == '1'),
            limite=request.args.get('limite', 100, type=int),
            offset=request.args.get('offset', 0, type=int),
        )
        return jsonify({'status': 'success', 'conversaciones': conversaciones})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@soporte_bp.route('/api/admin/centro-comunicacion/<int:conversacion_id>/mensajes', methods=['GET'])
@require_admin
def admin_mensajes_centro_comunicacion(conversacion_id):
    try:
        db = get_db()
        mensajes = chat_service.listar_mensajes_soporte_admin(db, conversacion_id)
        return jsonify({'status': 'success', 'mensajes': mensajes})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@soporte_bp.route('/api/aliados/<codigo>/centro-comunicacion', methods=['GET', 'POST'])
@require_aliado
def centro_comunicacion_aliado(codigo):
    """Centro de comunicación RUANA para el aliado autenticado."""
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        if request.method == 'GET':
            conversaciones = chat_service.listar_conversaciones_soporte_aliado(db, codigo, limite=request.args.get('limite', 50, type=int))
            return jsonify({'status': 'success', 'conversaciones': conversaciones})
        data = request.get_json() or {}
        result = chat_service.crear_conversacion_soporte_aliado(
            db,
            aliado_codigo=codigo,
            asunto=data.get('asunto') or 'Consulta general',
            mensaje=data.get('mensaje') or '',
            categoria=data.get('categoria') or 'consulta',
        )
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@soporte_bp.route('/api/aliados/<codigo>/centro-comunicacion/<int:conversacion_id>/mensajes', methods=['GET', 'POST'])
@require_aliado
def centro_comunicacion_aliado_mensajes(codigo, conversacion_id):
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        if request.method == 'GET':
            mensajes = chat_service.listar_mensajes_soporte_aliado(db, conversacion_id, codigo)
            return jsonify({'status': 'success', 'mensajes': mensajes})
        data = request.get_json() or {}
        result = chat_service.enviar_mensaje_soporte_aliado(db, conversacion_id, codigo, data.get('mensaje') or '')
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@soporte_bp.route('/api/aliados/<codigo>/centro-comunicacion/<int:conversacion_id>/marcar-leida', methods=['POST'])
@require_aliado
def centro_comunicacion_aliado_marcar_leida(codigo, conversacion_id):
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        result = chat_service.marcar_soporte_leido_aliado(db, conversacion_id, codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@soporte_bp.route('/api/admin/centro-comunicacion/<int:conversacion_id>/responder', methods=['POST'])
@require_admin_escritura
def admin_responder_centro_comunicacion(conversacion_id):
    try:
        data = request.get_json() or {}
        db = get_db()
        result = admin_service.responder_soporte_admin(
            db,
            conversacion_id=conversacion_id,
            admin_codigo=_admin_codigo(),
            mensaje=data.get('mensaje') or '',
            nuevo_estado=data.get('estado') or 'respondido',
        )
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@soporte_bp.route('/api/admin/centro-comunicacion/<int:conversacion_id>/estado', methods=['POST'])
@require_admin_escritura
def admin_estado_centro_comunicacion(conversacion_id):
    try:
        data = request.get_json() or {}
        db = get_db()
        result = admin_service.actualizar_estado_soporte_admin(db, conversacion_id, data.get('estado') or '', _admin_codigo())
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@soporte_bp.route('/api/admin/centro-comunicacion/<int:conversacion_id>', methods=['DELETE'])
@require_admin_escritura
def admin_eliminar_conversacion_centro(conversacion_id):
    try:
        db = get_db()
        result = admin_service.eliminar_conversacion_soporte_admin(db, conversacion_id, _admin_codigo())
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

