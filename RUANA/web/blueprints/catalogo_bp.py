"""Blueprint de catálogo / filtros / health (extraído de web/app.py)."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify

from core.db_manager import get_db
from web.catalogo_utils import _catalogo_oficios_desde_archivo

catalogo_bp = Blueprint('catalogo_bp', __name__)


@catalogo_bp.route('/api/catalogo/oficios', methods=['GET'])
def get_catalogo_oficios():
    """
    GET /api/catalogo/oficios
    Retorna el catálogo oficial de oficios RUANA en formato jerárquico.
    Cada oficio tiene nombre y lista de especializaciones (una plaza por especialización por grupo).
    """
    try:
        oficios = _catalogo_oficios_desde_archivo()
        if oficios:
            return jsonify({
                'status': 'success',
                'oficios': oficios,
                'timestamp': datetime.now().isoformat()
            })
        db = get_db()
        oficios = db.get_catalogo_oficios_jerarquico()
        return jsonify({
            'status': 'success',
            'oficios': oficios,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@catalogo_bp.route('/api/catalogo/oficios-raw', methods=['GET'])
def get_catalogo_oficios_raw():
    """Devuelve el catálogo leyendo solo el archivo config (sin BD). Fallback para el frontend."""
    oficios = _catalogo_oficios_desde_archivo()
    return jsonify({'status': 'success', 'oficios': oficios})


@catalogo_bp.route('/api/filtros', methods=['GET'])
def get_filtros():
    """
    GET /api/filtros
    Retorna opciones disponibles para filtros (extra?das de SQLite)
    """
    try:
        db = get_db()
        aliados = db.listar_aliados()

        zonas = sorted(list(set(a.get('codigo_postal', '') for a in aliados if a.get('codigo_postal'))))
        oficios = sorted(list(set(a.get('oficio', '') for a in aliados if a.get('oficio'))))

        return jsonify({
            'status': 'success',
            'zonas': zonas,
            'oficios': oficios,
            'estados': ['activo', 'inactivo'],
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@catalogo_bp.route('/api/health', methods=['GET'])
def health():
    """
    GET /api/health
    Verifica estado del servidor
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })
