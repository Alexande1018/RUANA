"""Blueprint de autenticación aliado + validación de invitación (lectura).

Login/logout/sesión de aliado y endpoints de lectura de invitaciones.
Admin JWT/login/logout permanecen en app.py.
"""

from __future__ import annotations

import os
import re
import time

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.auth_session import (
    RUANA_SESSION_HEADER,
    _ruana_session_create,
    _ruana_session_invalidate,
)
from core.db_manager import RUANA_CODIGO_INVITACION_REGEX
from web.auth_decorators import _aliado_codigo, _aliado_session_valid

auth_bp = Blueprint("auth", __name__)

ALIADO_SESSION_EXPIRES_SECONDS = int(os.environ.get("RUANA_ALIADO_SESSION_EXPIRES", 3600))


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


@auth_bp.route("/api/auth/bp-health", methods=["GET"])
def auth_bp_health():
    """Ping ligero del dominio auth aliado."""
    return jsonify({"status": "ok", "dominio": "auth"})


@auth_bp.route("/api/aliado/login", methods=["POST"], strict_slashes=False)
def aliado_login():
    """
    POST /api/aliado/login  body: { codigo: "XXXXX" }
    Valida el código, comprueba estado del aliado y crea sesión en store server-side.
    Retorna { status: 'success', codigo: "...", session_id: "..." }. El frontend debe guardar
    session_id en sessionStorage y enviar header X-Ruana-Session-Id en cada petición (aisla por pestaña).
    """
    data = request.get_json() or {}
    codigo = (data.get('codigo') or '').strip()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'C?digo de aliado requerido'}), 400
    try:
        db = get_db()
        aliado = db.obtener_aliado_por_codigo(codigo)
        if not aliado:
            return jsonify({'status': 'error', 'message': 'C?digo inv?lido o aliado no encontrado'}), 401
        estado = aliado.get('estado')
        if estado == 'expulsado':
            return jsonify({'status': 'error', 'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'}), 403
        if estado == 'pendiente_validacion':
            return jsonify({'status': 'error', 'message': 'Tu cuenta est? pendiente de validaci?n. No puedes acceder al panel hasta que un administrador la active.'}), 403
        if estado == 'rechazado':
            return jsonify({'status': 'error', 'message': 'Tu solicitud de registro no fue aceptada.'}), 403
        if estado == 'suspendido_temporal':
            return jsonify({'status': 'error', 'message': 'Acceso suspendido temporalmente.'}), 403
        if estado == 'en_espera':
            return jsonify({'status': 'error', 'message': 'Estás en la lista de Suplentes. En cuanto se libere una plaza en tu zona, el equipo RUANA te incorporará y podrás acceder al panel.'}), 403
        expires_at = time.time() + ALIADO_SESSION_EXPIRES_SECONDS
        session_id = _ruana_session_create('aliado', codigo, expires_at)
        # Regla 8: registrar día de login (calendario servidor) y evaluar racha 7 días
        try:
            db.registrar_acceso_login(codigo)
        except Exception:
            pass
        return jsonify({'status': 'success', 'codigo': codigo, 'session_id': session_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_bp.route("/api/aliado/sesion", methods=["GET"], strict_slashes=False)
def aliado_sesion():
    """
    GET /api/aliado/sesion
    Requiere header X-Ruana-Session-Id. Devuelve { status: 'ok', codigo: "XXXXX" } si la sesión es válida; si no, 401.
    """
    if not _aliado_session_valid():
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada o no autorizado'}), 401
    return jsonify({'status': 'ok', 'codigo': _aliado_codigo()})


@auth_bp.route("/api/aliado/logout", methods=["POST"])
def aliado_logout():
    """POST /api/aliado/logout  Invalida la sesión indicada por header X-Ruana-Session-Id (o body session_id)."""
    sid = request.headers.get(RUANA_SESSION_HEADER) or (request.get_json() or {}).get('session_id')
    _ruana_session_invalidate(sid)
    return jsonify({'status': 'success'})


@auth_bp.route("/api/validar-invitacion", methods=["GET"])
def validar_invitacion_query():
    """
    GET /api/validar-invitacion?codigo=XXXXX
    Valida c?digo de invitaci?n (query param). Endpoint dedicado para evitar problemas de routing.
    """
    print("[RUANA] ENDPOINT validar-invitacion (query) llamado path=%s" % request.path)
    codigo_raw = request.args.get('codigo') or ''
    return _validar_invitacion_impl(codigo_raw)


def _validar_invitacion_impl(codigo_raw):
    """L?gica com?n de validaci?n de invitaci?n."""
    try:
        codigo = ''.join(c for c in str(codigo_raw or '').strip() if c.isprintable() and c != '\x00').strip()
        if not codigo:
            return jsonify({
                'status': 'error',
                'message': 'C?digo de invitaci?n requerido'
            }), 400

        db = get_db()

        # Formato RUANA-{grupo_id}-{OFICIO}-{4chars}: invitaci?n por oficio (Oficios faltantes)
        codigo_upper = codigo.strip().upper()
        if re.match(RUANA_CODIGO_INVITACION_REGEX, codigo_upper):
            inv = db.validar_invitacion_oficio(codigo_upper)
            if not inv:
                return jsonify({
                    'status': 'error',
                    'message': 'C?digo no encontrado o ya utilizado. Cada c?digo de invitaci?n solo puede usarse una vez.'
                }), 404
            return jsonify({
                'status': 'success',
                'message': 'C?digo v?lido',
                'invitacion': {
                    'codigo': inv['codigo'],
                    'zona': inv.get('zona', ''),
                    'grupo': inv.get('grupo', ''),
                    'oficio': inv.get('oficio', ''),
                    'codigo_postal': inv.get('codigo_postal', ''),
                }
            }), 200

        campana = None
        if hasattr(db, 'validar_campana_invitacion'):
            campana = db.validar_campana_invitacion(codigo_upper)
        if campana:
            return jsonify({
                'status': 'success',
                'message': 'Codigo valido',
                'invitacion': {
                    'tipo': 'campana',
                    'codigo': campana.get('codigo'),
                    'zona': campana.get('codigo_postal') or '',
                    'grupo': None,
                    'aliado_id': None,
                    'fecha_expiracion': None,
                    'max_usos': campana.get('max_usos'),
                    'usos_actuales': campana.get('usos_actuales'),
                    'usos_restantes': campana.get('usos_restantes'),
                }
            }), 200
        if hasattr(db, 'obtener_campana_invitacion') and db.obtener_campana_invitacion(codigo_upper):
            return jsonify({
                'status': 'error',
                'message': 'Codigo de invitacion agotado o desactivado.'
            }), 404

        # Formato aliado: 5 d?gitos, A0001, ALFA01
        if not (
            re.match(r'^\d{5}$', codigo) or
            re.match(r'^[A-Z]\d{4}$', codigo) or
            re.match(r'^[A-Z]{4}\d{2}$', codigo)
        ):
            return jsonify({
                'status': 'error',
                'message': 'Formato de c?digo inv?lido'
            }), 400

        # Preferir invitaciones reales (tabla invitaciones) frente a placeholders legacy.
        invitacion_pendiente = None
        if hasattr(db, 'obtener_invitacion_pendiente'):
            invitacion_pendiente = db.obtener_invitacion_pendiente(codigo)
        if invitacion_pendiente:
            return jsonify({
                'status': 'success',
                'message': 'C?digo v?lido',
                'invitacion': {
                    'codigo': invitacion_pendiente.get('codigo') or codigo,
                    'zona': invitacion_pendiente.get('zona_invitador') or '',
                    'grupo': None,
                    'aliado_id': invitacion_pendiente.get('invitador_aliado_id') or invitacion_pendiente.get('invitador_id'),
                    'fecha_expiracion': None,
                    'tipo': 'invitacion',
                }
            }), 200

        aliado = db.obtener_aliado_por_codigo(codigo)

        # LOG TEMPORAL: traza completa para depuraci?n de invitaciones
        try:
            print(f"[RUANA][INVITACION] validar_invitacion codigo={codigo} db_path={db.db_path}")
            print(f"[RUANA][INVITACION] aliado_encontrado={bool(aliado)} datos={dict(aliado) if aliado else None}")
        except Exception as _log_err:
            print(f"[RUANA][INVITACION] Error log interno: {_log_err}")

        # C?digo expulsado: desactivado, requiere nueva invitaci?n para volver
        if aliado and aliado.get('estado') == 'expulsado':
            return jsonify({
                'status': 'error',
                'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'
            }), 403
        # Compatibilidad: placeholders legacy (pendiente_completar) siguen siendo invitaci?n.
        # Si el c?digo es de un aliado activo o pendiente_validacion, es c?digo de ingreso (no invitaci?n).
        if not aliado or aliado.get('estado') != 'pendiente_completar':
            if aliado and aliado.get('estado') in ('activo', 'pendiente_validacion'):
                return jsonify({
                    'status': 'error',
                    'message': 'Este c?digo es de ingreso personal. Usa la opci?n "Tengo c?digo de ingreso".'
                }), 404
            return jsonify({
                'status': 'error',
                'message': f'C?digo de invitaci?n {codigo} no encontrado o ya usado.'
            }), 404

        invitacion_payload = {
            'codigo': codigo,
            'zona': aliado.get('codigo_postal') or '',
            'grupo': None,
            'aliado_id': aliado.get('id'),
            'fecha_expiracion': None,
            'tipo': 'invitacion_legacy_placeholder',
        }

        return jsonify({
            'status': 'success',
            'message': 'C?digo v?lido',
            'invitacion': invitacion_payload
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error al validar invitaci?n: {str(e)}'
        }), 500


@auth_bp.route("/api/invitaciones/validar", methods=["GET"])
def validar_invitacion_legacy():
    """GET /api/invitaciones/validar?codigo=XXXXX - alias para compatibilidad."""
    codigo_raw = request.args.get('codigo') or ''
    return _validar_invitacion_impl(codigo_raw)


@auth_bp.route("/api/invitaciones/validar/<path:codigo>", methods=["GET"])
def validar_invitacion_path(codigo):
    """GET /api/invitaciones/validar/XXXXX - c?digo en path."""
    return _validar_invitacion_impl(codigo)
