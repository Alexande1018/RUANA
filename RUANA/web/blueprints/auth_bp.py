"""Blueprint de autenticación aliado + validación de invitación (lectura).

Login/logout/sesión de aliado y endpoints de lectura de invitaciones.
Admin JWT/login/logout permanecen en app.py.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import aliado_service, invitacion_service, solicitud_service
from core.services import aliado_pin_service
from core.aliado_pin_auth import GENERIC_CREDENTIALS_ERROR
from core.auth_session import (
    RUANA_SESSION_HEADER,
    _ruana_session_create,
    _ruana_session_invalidate,
)
from core.db_manager import RUANA_CODIGO_INVITACION_REGEX
from web.auth_decorators import _aliado_codigo, _aliado_session_valid, require_aliado
from web.limiter import limiter

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
@limiter.limit("30 per hour")
@limiter.limit("10 per minute")
def aliado_login():
    """
    POST /api/aliado/login  body: { codigo: "XXXXX", pin: "1234" }
    Valida código + PIN (o devuelve pin_setup_required si aún no tiene PIN).
    Retorna { status: 'success', codigo: "...", session_id: "..." }.
    """
    data = request.get_json() or {}
    codigo = (data.get('codigo') or '').strip()
    pin = (data.get('pin') or '').strip()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'Código de aliado requerido'}), 400
    try:
        db = get_db()
        resultado = aliado_pin_service.validar_login_aliado(db, codigo, pin)
        if not resultado.get('ok'):
            status = resultado.get('http_status', 401)
            return jsonify({'status': 'error', 'message': resultado.get('message', GENERIC_CREDENTIALS_ERROR)}), status

        if resultado.get('pin_setup_required'):
            return jsonify({
                'status': 'success',
                'pin_setup_required': True,
                'codigo': resultado.get('codigo'),
                'setup_token': resultado.get('setup_token'),
            })

        codigo_ok = resultado.get('codigo')
        expires_at = time.time() + ALIADO_SESSION_EXPIRES_SECONDS
        session_id = _ruana_session_create('aliado', codigo_ok, expires_at)
        try:
            aliado_service.registrar_acceso_login(db, codigo_ok)
        except Exception:
            pass
        return jsonify({'status': 'success', 'codigo': codigo_ok, 'session_id': session_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_bp.route("/api/aliado/pin/crear", methods=["POST"], strict_slashes=False)
@limiter.limit("20 per hour")
def aliado_pin_crear():
    """Crea el PIN personal tras primer acceso (requiere setup_token)."""
    data = request.get_json() or {}
    setup_token = (data.get('setup_token') or '').strip()
    pin = (data.get('pin') or '').strip()
    pin_confirmacion = (data.get('pin_confirmacion') or data.get('pin_confirm') or '').strip()
    if not setup_token:
        return jsonify({'status': 'error', 'message': 'Token de configuración requerido'}), 400
    try:
        db = get_db()
        resultado = aliado_pin_service.establecer_pin_inicial(db, setup_token, pin, pin_confirmacion)
        if resultado.get('status') != 'success':
            return jsonify(resultado), 400
        codigo = resultado.get('codigo')
        expires_at = time.time() + ALIADO_SESSION_EXPIRES_SECONDS
        session_id = _ruana_session_create('aliado', codigo, expires_at)
        try:
            aliado_service.registrar_acceso_login(db, codigo)
        except Exception:
            pass
        return jsonify({
            'status': 'success',
            'message': resultado.get('message'),
            'codigo': codigo,
            'session_id': session_id,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_bp.route("/api/aliado/pin/cambiar", methods=["POST"], strict_slashes=False)
@require_aliado
@limiter.limit("20 per hour")
def aliado_pin_cambiar():
    """Cambia el PIN personal (requiere sesión activa)."""
    data = request.get_json() or {}
    pin_actual = (data.get('pin_actual') or '').strip()
    pin_nuevo = (data.get('pin_nuevo') or '').strip()
    pin_confirmacion = (data.get('pin_confirmacion') or data.get('pin_confirm') or '').strip()
    try:
        db = get_db()
        resultado = aliado_pin_service.cambiar_pin(
            db,
            _aliado_codigo(),
            pin_actual,
            pin_nuevo,
            pin_confirmacion,
        )
        status = 200 if resultado.get('status') == 'success' else 400
        return jsonify(resultado), status
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_bp.route("/api/aliado/recuperacion/solicitar", methods=["POST"], strict_slashes=False)
@limiter.limit("10 per hour")
@limiter.limit("3 per minute")
def aliado_recuperacion_solicitar():
    """Solicita código temporal por email (tipos: pin, codigo, ambos)."""
    data = request.get_json() or {}
    tipo = (data.get('tipo') or '').strip().lower()
    email = (data.get('email') or '').strip()
    codigo = (data.get('codigo') or '').strip()
    try:
        db = get_db()
        resultado = aliado_pin_service.solicitar_recuperacion(
            db, tipo=tipo, email=email, codigo=codigo,
        )
        status = 200 if resultado.get('status') == 'success' else 400
        return jsonify(resultado), status
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_bp.route("/api/aliado/recuperacion/verificar", methods=["POST"], strict_slashes=False)
@limiter.limit("30 per hour")
@limiter.limit("10 per minute")
def aliado_recuperacion_verificar():
    """Verifica el código temporal enviado por email."""
    data = request.get_json() or {}
    recovery_token = data.get('recovery_token')
    codigo_temporal = (data.get('codigo_temporal') or data.get('codigo') or '').strip()
    try:
        token_id = int(recovery_token)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Solicitud de recuperación inválida.'}), 400
    if not codigo_temporal:
        return jsonify({'status': 'error', 'message': 'Introduce el código temporal.'}), 400
    try:
        db = get_db()
        resultado = aliado_pin_service.verificar_recuperacion(db, token_id, codigo_temporal)
        status = 200 if resultado.get('status') == 'success' else 400
        return jsonify(resultado), status
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_bp.route("/api/aliado/recuperacion/pin", methods=["POST"], strict_slashes=False)
@limiter.limit("20 per hour")
def aliado_recuperacion_pin():
    """Restablece el PIN tras verificación por email."""
    data = request.get_json() or {}
    recovery_token = data.get('recovery_token')
    pin_nuevo = (data.get('pin') or data.get('pin_nuevo') or '').strip()
    pin_confirmacion = (data.get('pin_confirmacion') or data.get('pin_confirm') or '').strip()
    try:
        token_id = int(recovery_token)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Solicitud de recuperación inválida.'}), 400
    try:
        db = get_db()
        resultado = aliado_pin_service.restablecer_pin_recuperacion(
            db, token_id, pin_nuevo, pin_confirmacion,
        )
        status = 200 if resultado.get('status') == 'success' else 400
        return jsonify(resultado), status
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
            inv = invitacion_service.validar_invitacion_oficio(db, codigo_upper)
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

        campana = invitacion_service.validar_campana_invitacion(db, codigo_upper)
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
        if invitacion_service.obtener_campana_invitacion(db, codigo_upper):
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
        invitacion_pendiente = invitacion_service.obtener_invitacion_pendiente(db, codigo)
        if invitacion_pendiente:
            fecha_exp = None
            if invitacion_pendiente.get('solicitud_id') is not None:
                creado = invitacion_pendiente.get('creado_en')
                desde = None
                if creado:
                    try:
                        desde = datetime.fromisoformat(str(creado).replace('Z', '').split('.')[0])
                    except (TypeError, ValueError):
                        desde = None
                fecha_exp = solicitud_service.calcular_expiracion_candidato(desde)
            return jsonify({
                'status': 'success',
                'message': 'C?digo v?lido',
                'invitacion': {
                    'codigo': invitacion_pendiente.get('codigo') or codigo,
                    'zona': invitacion_pendiente.get('zona_invitador') or '',
                    'grupo': None,
                    'aliado_id': invitacion_pendiente.get('invitador_aliado_id') or invitacion_pendiente.get('invitador_id'),
                    'fecha_expiracion': fecha_exp,
                    'tipo': 'invitacion',
                }
            }), 200

        if invitacion_service.es_codigo_conozco_caducado(db, codigo):
            return jsonify({
                'status': 'error',
                'message': 'Este código ha caducado (24 h sin registro). Pide uno nuevo al aliado del grupo.',
            }), 404

        aliado = aliado_service.obtener_aliado_por_codigo(db, codigo)

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
