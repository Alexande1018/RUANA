"""Store y helpers de sesión JWT RUANA (extraído de web/app.py).

Cada login genera un session_id (JWT firmado) que el frontend envía en
X-Ruana-Session-Id. El JWT permite validar sesión en cualquier instancia
de Cloud Run sin memoria compartida; el store en memoria cubre tests y
caché local.
"""

from __future__ import annotations

import threading
import time

import jwt
from flask import request

_RUANA_SESSION_STORE = {}
_RUANA_SESSION_REVOKED = set()
_RUANA_SESSION_LOCK = threading.Lock()
RUANA_SESSION_HEADER = 'X-Ruana-Session-Id'

_session_secret_key = None


def configure_session_secret(secret_key):
    """Configura la clave con la que se firman/validan los JWT de sesión."""
    global _session_secret_key
    _session_secret_key = secret_key


def _resolve_session_secret():
    if _session_secret_key is not None:
        return _session_secret_key
    from core.settings import get_settings
    return get_settings().flask_secret_key


def _ruana_session_from_jwt(token):
    """Decodifica un JWT de sesión RUANA. None si es inválido o expiró."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, _resolve_session_secret(), algorithms=['HS256'])
        if float(payload.get('exp', 0)) <= time.time():
            return None
        return {
            'tipo': payload.get('tipo'),
            'codigo': (payload.get('codigo') or '').strip(),
            'expires_at': float(payload.get('exp', 0)),
            'permisos': list(payload.get('permisos') or []),
        }
    except Exception:
        return None


def _get_ruana_session():
    """
    Lee X-Ruana-Session-Id del request y devuelve la sesión si existe y no expiró.
    Acepta JWT firmado (multi-instancia) o entradas legacy en memoria (tests).
    """
    sid = (request.headers.get(RUANA_SESSION_HEADER) or '').strip()
    if not sid:
        return None
    with _RUANA_SESSION_LOCK:
        if sid in _RUANA_SESSION_REVOKED:
            return None
        data = _RUANA_SESSION_STORE.get(sid)
    if data and float(data.get('expires_at', 0)) > time.time():
        return data
    return _ruana_session_from_jwt(sid)


def _ruana_session_create(tipo, codigo, expires_at, permisos=None):
    """Crea una sesión y devuelve un JWT como session_id (nuevo id por login)."""
    payload = {
        'tipo': tipo,
        'codigo': (codigo or '').strip(),
        'exp': int(expires_at),
    }
    if permisos is not None:
        payload['permisos'] = list(permisos)
    token = jwt.encode(payload, _resolve_session_secret(), algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    with _RUANA_SESSION_LOCK:
        _RUANA_SESSION_STORE[token] = {
            'tipo': tipo,
            'codigo': (codigo or '').strip(),
            'expires_at': float(expires_at),
            'permisos': list(permisos) if permisos is not None else [],
        }
    return token


def _ruana_session_invalidate(session_id):
    """Invalida una sesión por su id."""
    sid = (session_id or '').strip()
    if not sid:
        return
    with _RUANA_SESSION_LOCK:
        _RUANA_SESSION_STORE.pop(sid, None)
        _RUANA_SESSION_REVOKED.add(sid)


def _ruana_session_invalidate_for_codigo(codigo):
    """Invalida todas las sesiones activas de un aliado (login, caché en memoria)."""
    codigo_norm = (codigo or '').strip()
    if not codigo_norm:
        return
    with _RUANA_SESSION_LOCK:
        to_remove = [
            sid for sid, data in _RUANA_SESSION_STORE.items()
            if data.get('tipo') == 'aliado' and (data.get('codigo') or '').strip() == codigo_norm
        ]
        for sid in to_remove:
            _RUANA_SESSION_STORE.pop(sid, None)
            _RUANA_SESSION_REVOKED.add(sid)
