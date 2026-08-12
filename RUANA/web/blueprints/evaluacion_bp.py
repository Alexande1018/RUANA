"""Blueprint de evaluaciones (Motor RUANA). Extraído de web/app.py."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import evaluacion_service
from web.auth_decorators import (
    _aliado_codigo,
    _forbidden_unless_admin_or_aliado_self,
    require_admin,
    require_aliado,
)

evaluacion_bp = Blueprint("evaluacion", __name__)

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


@evaluacion_bp.route("/api/evaluaciones/bp-health", methods=["GET"])
def evaluacion_bp_health():
    return jsonify({"status": "ok", "dominio": "evaluacion"})

@evaluacion_bp.route('/api/evaluaciones/<codigo_aliado>', methods=['GET'])
@require_aliado
def obtener_evaluacion(codigo_aliado):
    """
    GET /api/evaluaciones/XXXXX
    Obtiene la evaluaci?n m?s reciente del aliado. Solo se permite el c?digo de la sesi?n.
    """
    try:
        codigo_aliado = codigo_aliado.strip()
        if codigo_aliado != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        evaluacion = evaluacion_service.obtener_evaluacion(db, codigo_aliado)
        
        if not evaluacion:
            return jsonify({
                'status': 'error',
                'message': f'No hay evaluaci?n para {codigo_aliado}'
            }), 404
        
        return jsonify({
            'status': 'success',
            'evaluacion': evaluacion,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@evaluacion_bp.route('/api/evaluaciones', methods=['GET'])
@require_admin
def listar_evaluaciones():
    """
    GET /api/evaluaciones
    GET /api/evaluaciones?estado=verde
    
    Lista todas las evaluaciones o filtra por estado
    """
    try:
        estado = request.args.get('estado', '').strip() or None
        db = get_db()
        
        evaluaciones = evaluacion_service.listar_evaluaciones(db, estado)
        
        return jsonify({
            'status': 'success',
            'total': len(evaluaciones),
            'evaluaciones': evaluaciones,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@evaluacion_bp.route('/api/evaluaciones/<codigo_aliado>/historico', methods=['GET'])
def obtener_historico_evaluacion(codigo_aliado):
    """
    GET /api/evaluaciones/XXXXX/historico
    
    Obtiene el hist?rico de cambios de evaluaci?n de un aliado
    """
    try:
        codigo_aliado = codigo_aliado.strip()
        auth_err = _forbidden_unless_admin_or_aliado_self(codigo_aliado)
        if auth_err:
            return auth_err
        db = get_db()
        
        historico = evaluacion_service.obtener_historico_evaluaciones(db, codigo_aliado)
        
        return jsonify({
            'status': 'success',
            'historico': historico,
            'total': len(historico),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@evaluacion_bp.route('/api/evaluaciones/estadisticas', methods=['GET'])
@require_admin
def estadisticas_evaluaciones():
    """
    GET /api/evaluaciones/estadisticas
    
    Retorna estad?sticas generales de las evaluaciones
    """
    try:
        db = get_db()
        stats = evaluacion_service.obtener_estadisticas_evaluaciones(db)
        
        return jsonify({
            'status': 'success',
            'estadisticas': stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

