"""Blueprint de invitaciones (generar/crear/campañas admin).

Rutas extraídas de web/app.py. Validación pública vive en auth_bp.
GET de campañas permanece en admin_bp. Paths y contratos idénticos.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import admin_service, aliado_service, invitacion_service, solicitud_service
from core.services import grupo_crecimiento_service
from core.db_constants import INVITACION_TIPO_CRECIMIENTO_GRUPO
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    require_admin_escritura,
    require_aliado,
)
from web.blueprints.admin_bp import _registro_url_para_invitacion

invitacion_bp = Blueprint("invitacion", __name__)

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


def _resolve_app_attr(name, default=None):
    """Resuelve atributo del módulo app (monkeypatch-friendly)."""
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None and hasattr(mod, name):
            return getattr(mod, name)
    return default


def _generar_codigo_invitacion(db):
    """Genera un código de invitación único sin crear aliado placeholder."""
    # Preferir implementación/monkeypatch expuesto en app
    override = _resolve_app_attr("_generar_codigo_invitacion")
    if override is not None and getattr(override, "__module__", "") not in (
        "web.blueprints.invitacion_bp",
        "RUANA.web.blueprints.invitacion_bp",
    ):
        return override(db)
    return _generar_codigo_invitacion_impl(db)


def _generar_codigo_invitacion_impl(db):
    import random

    for _ in range(100):
        codigo = str(random.randint(10000, 99999))
        disponible = True
        if hasattr(db, 'codigo_disponible_para_asignar'):
            disponible = aliado_service.codigo_disponible_para_asignar(db, codigo)
        elif aliado_service.codigo_existe(db, codigo):
            disponible = False
        elif invitacion_service.invitacion_codigo_existe(db, codigo):
            disponible = False
        if disponible:
            return codigo
    raise RuntimeError("No se pudo generar codigo de invitacion unico despues de 100 intentos")


@invitacion_bp.route("/api/invitacion/bp-health", methods=["GET"])
def invitacion_bp_health():
    return jsonify({"status": "ok", "dominio": "invitacion"})

@invitacion_bp.route('/api/generar-invitacion', methods=['POST'])
@invitacion_bp.route('/api/aliado/generar-invitacion', methods=['POST'])
@require_aliado
def generar_invitacion():
    """
    POST /api/generar-invitacion  o  POST /api/aliado/generar-invitacion
    Body: { oficio: "Alba?iler?a" }. Genera invitaci?n para oficio faltante en el grupo del aliado en sesi?n.
    """
    print("[RUANA] ENDPOINT generar-invitacion llamado")
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
    data = request.get_json() or {}
    oficio = (data.get('oficio') or '').strip()
    if not oficio:
        return jsonify({'status': 'error', 'message': 'Oficio requerido'}), 400
    try:
        db = get_db()
        result = invitacion_service.generar_invitacion_oficio(db, codigo, oficio)
        if result.get('status') == 'error':
            return jsonify(result), 400
        return jsonify({'status': 'success', 'codigo': result['codigo']})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@invitacion_bp.route('/api/invitaciones/crear', methods=['POST'])
@require_aliado
def crear_invitacion():
    """
    POST /api/invitaciones/crear
    
    Crea un c?digo de invitaci?n para un nuevo aliado.
    El c?digo vive solo en `invitaciones` (no crea aliado placeholder).
    Al registrarse, el invitado recibe un c?digo personal distinto.
    
    Body JSON:
    {
        "zona": "080001",
        "solicitud_id": 456
    }
    """
    try:
        data = request.get_json() or {}
        
        db = get_db()

        # La identidad del invitador sale siempre de la sesion de aliado.
        codigo_sesion = _aliado_codigo()
        aliado_sesion = aliado_service.obtener_aliado_por_codigo(db, codigo_sesion) if codigo_sesion else None
        if not aliado_sesion:
            return jsonify({'status': 'error', 'message': 'Aliado invitador no encontrado'}), 403
        estado_aliado = (aliado_sesion.get('estado') or '').strip().lower()
        if estado_aliado != 'activo':
            return jsonify({'status': 'error', 'message': 'Aliado no autorizado para crear invitaciones'}), 403

        aliado_invitador_id = aliado_sesion.get('id')
        solicitud_id = data.get('solicitud_id')
        crecimiento_grupo = bool(
            data.get('crecimiento_grupo')
            or (data.get('tipo') or '').strip() == INVITACION_TIPO_CRECIMIENTO_GRUPO
        )

        grupo_id_inv = None
        tipo_inv = 'ampliar_red'
        if crecimiento_grupo:
            validacion = grupo_crecimiento_service.puede_crear_invitacion_crecimiento(
                db, codigo_sesion
            )
            if not validacion.get('ok'):
                return jsonify({
                    'status': 'error',
                    'message': validacion.get('message') or 'No puedes crear esta invitación',
                }), 400
            grupo_id_inv = validacion.get('grupo_id')
            tipo_inv = INVITACION_TIPO_CRECIMIENTO_GRUPO
            solicitud_id = None

        codigo = _generar_codigo_invitacion(db)

        # Registrar quién invitó (recompensa al completar registro del invitado)
        if aliado_invitador_id is None:
            return jsonify({'status': 'error', 'message': 'No se pudo identificar al invitador'}), 500
        sid = None
        if solicitud_id is not None:
            try:
                sid = int(solicitud_id)
            except (TypeError, ValueError):
                sid = None
        try:
            invitacion_service._registrar_invitacion(
                db,
                codigo,
                int(aliado_invitador_id),
                sid,
                grupo_id_inv,
                tipo_inv,
            )
        except Exception as e:
            print(f"[RUANA] Error registrando invitacion {codigo}: {e}")
            return jsonify({
                'status': 'error',
                'message': 'No se pudo registrar la invitacion. Intenta de nuevo.',
            }), 500

        # «Conozco a alguien»: no cerrar la solicitud; marcar candidato pendiente
        if sid is not None:
            try:
                mark = solicitud_service.marcar_solicitud_candidato_pendiente(db, sid, codigo_sesion)
                if mark.get('status') != 'success':
                    print(f"[RUANA] Aviso candidato pendiente solicitud {sid}: {mark.get('message')}")
            except Exception as e:
                print(f"[RUANA] Error marcando candidato pendiente {sid}: {e}")

        expires_at = None
        if sid is not None:
            expires_at = solicitud_service.calcular_expiracion_candidato()
        
        return jsonify({
            'status': 'success',
            'message': f'C?digo de invitaci?n creado',
            'codigo': codigo,
            'tipo': tipo_inv if crecimiento_grupo else 'invitacion',
            'grupo_id': grupo_id_inv,
            'solicitud_id': sid,
            'estado_solicitud': 'candidato_pendiente' if sid is not None else None,
            'expires_at': expires_at,
            'validez_horas': solicitud_service.CANDIDATO_INVITACION_HORAS if sid is not None else None,
            'timestamp': datetime.now().isoformat()
        }), 201
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@invitacion_bp.route('/api/admin/invitaciones/crear', methods=['POST'])
@require_admin_escritura
def admin_crear_invitacion():
    """
    POST /api/admin/invitaciones/crear
    Crea un codigo de invitacion desde el panel admin (sin placeholder de aliado).
    """
    try:
        db = get_db()
        codigo = _generar_codigo_invitacion(db)

        # Vincular al admin como invitador para que el registro aparezca en la red de referidos.
        admin_codigo = _admin_codigo() or 'RUANA-ADMIN'
        admin_service.obtener_o_crear_invitador_admin(db, admin_codigo)
        admin_aliado = aliado_service.obtener_aliado_por_codigo(db, admin_codigo)
        admin_id = admin_aliado.get('id') if admin_aliado else None
        if admin_id is None:
            return jsonify({'status': 'error', 'message': 'No se pudo vincular invitacion al admin'}), 500
        try:
            invitacion_service._registrar_invitacion(db, codigo, int(admin_id))
        except Exception as e:
            print(f"[RUANA] Error registrando invitacion admin {codigo}: {e}")
            return jsonify({
                'status': 'error',
                'message': 'No se pudo registrar la invitacion admin. Intenta de nuevo.',
            }), 500

        return jsonify({
            'status': 'success',
            'message': 'Codigo de invitacion creado desde admin',
            'codigo': codigo,
            'tipo': 'invitacion_admin',
            'timestamp': datetime.now().isoformat()
        }), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500




@invitacion_bp.route('/api/admin/invitacion-campanas', methods=['POST'])
@require_admin_escritura
def admin_crear_campana_invitacion():
    """POST /api/admin/invitacion-campanas - Crea un codigo multiuso para QR/registro."""
    try:
        data = request.get_json() or {}
        db = get_db()
        result = invitacion_service.crear_campana_invitacion(
            db,
            codigo=(data.get('codigo') or '').strip(),
            nombre=(data.get('nombre') or '').strip(),
            codigo_postal=(data.get('codigo_postal') or data.get('zona') or '').strip(),
            max_usos=data.get('max_usos') or 100,
            creado_por_admin_codigo=_admin_codigo() or ''
        )
        if result.get('status') != 'success':
            return jsonify(result), 400
        campana = result.get('campana') or {}
        registro_url = _registro_url_para_invitacion(campana.get('codigo', ''))
        return jsonify({
            'status': 'success',
            'campana': campana,
            'registro_url': registro_url,
            'qr_url': 'https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=' + quote(registro_url, safe=''),
            'timestamp': datetime.now().isoformat()
        }), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@invitacion_bp.route('/api/admin/invitacion-campanas/<path:codigo>/desactivar', methods=['POST'])
@require_admin_escritura
def admin_desactivar_campana_invitacion(codigo):
    """POST /api/admin/invitacion-campanas/<codigo>/desactivar - Da de baja un codigo multiuso."""
    try:
        db = get_db()
        result = invitacion_service.desactivar_campana_invitacion(db, codigo)
        if result.get('status') != 'success':
            return jsonify(result), 404
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


