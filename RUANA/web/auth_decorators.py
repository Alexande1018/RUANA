"""Decorators y helpers de autorización HTTP (extraídos de web/app.py).

Permite que los Blueprints usen require_aliado / require_admin sin importar app.
"""

from __future__ import annotations

import os
import time
from functools import wraps

import jwt
from flask import jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from core.auth_session import _get_ruana_session, _resolve_session_secret


def _admin_jwt_payload():
    """Si hay Authorization: Bearer <jwt> válido, devuelve el payload; si no, None."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, _resolve_session_secret(), algorithms=["HS256"])
        if payload.get("exp", 0) <= time.time():
            return None
        return payload
    except Exception:
        return None


def _admin_session_valid():
    """True si hay sesión admin válida (store por header o JWT)."""
    s = _get_ruana_session()
    if s and s.get("tipo") == "admin" and s.get("codigo"):
        return True
    payload = _admin_jwt_payload()
    return bool(payload and payload.get("admin_codigo"))


def _admin_permisos():
    """Lista de permisos del admin actual. Vacía si no hay sesión."""
    s = _get_ruana_session()
    if s and s.get("tipo") == "admin" and isinstance(s.get("permisos"), list):
        return s["permisos"]
    payload = _admin_jwt_payload()
    if payload and isinstance(payload.get("permisos"), list):
        return payload["permisos"]
    return []


def _admin_permisos_efectivos():
    """Permisos del admin con fallback legacy (mismo criterio que /api/admin/me)."""
    permisos = _admin_permisos()
    if not permisos and _admin_codigo():
        return ["leer", "escribir", "eliminar", "configurar"]
    return permisos


def _admin_puede_escribir():
    """True si el admin tiene permiso de escritura o configuración."""
    p = _admin_permisos()
    return "escribir" in p or "configurar" in p


def _admin_codigo():
    """Código del admin en sesión o JWT. Vacío si no hay sesión."""
    s = _get_ruana_session()
    if s and s.get("tipo") == "admin":
        return (s.get("codigo") or "").strip()
    payload = _admin_jwt_payload()
    return (payload.get("admin_codigo") or "") if payload else ""


_google_auth_request = google_requests.Request()
_SCHEDULER_SA = os.environ.get("RUANA_SCHEDULER_SA", "").strip()

def _cron_oidc_valid() -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not _SCHEDULER_SA:
        return False
    try:
        claims = id_token.verify_oauth2_token(auth[7:].strip(), _google_auth_request)
    except Exception:
        return False
    return claims.get("email") == _SCHEDULER_SA and bool(claims.get("email_verified"))


def _cron_secret_valid() -> bool:
    if _cron_oidc_valid():
        return True
    expected = os.environ.get("RUANA_CRON_SECRET", "").strip()
    if not expected:
        return False
    got = (request.headers.get("X-Ruana-Cron-Secret") or "").strip()
    return bool(got) and got == expected


def require_admin_escritura_or_cron(f):
    """Admin con escritura o llamada scheduler con X-Ruana-Cron-Secret."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if _cron_secret_valid():
            return f(*args, **kwargs)
        if not _admin_session_valid() and not (
            _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
        ):
            return jsonify({"status": "error", "message": "Sesi?n admin expirada o no autorizado"}), 401
        if not _admin_puede_escribir():
            return jsonify({"status": "error", "message": "Sin permiso de escritura (solo lectura)"}), 403
        return f(*args, **kwargs)
    return wrapped


def require_admin_or_cron(f):
    """Sesión admin/JWT o llamada scheduler con X-Ruana-Cron-Secret."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if _cron_secret_valid():
            return f(*args, **kwargs)
        if _admin_session_valid():
            return f(*args, **kwargs)
        payload = _admin_jwt_payload()
        if payload and payload.get("admin_codigo"):
            return f(*args, **kwargs)
        return jsonify({"status": "error", "message": "Sesi?n admin expirada o no autorizado"}), 401
    return wrapped


def require_admin(f):
    """Decorator: exige sesión admin o JWT válido. Devuelve 401 si no."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if _admin_session_valid():
            return f(*args, **kwargs)
        payload = _admin_jwt_payload()
        if payload and payload.get("admin_codigo"):
            return f(*args, **kwargs)
        return jsonify({"status": "error", "message": "Sesi?n admin expirada o no autorizado"}), 401
    return wrapped


def require_admin_escritura(f):
    """Decorator: exige admin Y permiso escritura/configurar."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _admin_session_valid() and not (
            _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
        ):
            return jsonify({"status": "error", "message": "Sesi?n admin expirada o no autorizado"}), 401
        if not _admin_puede_escribir():
            return jsonify({"status": "error", "message": "Sin permiso de escritura (solo lectura)"}), 403
        return f(*args, **kwargs)
    return wrapped


def require_conflict_permission(permiso_requerido: str):
    """Decorator: admin autenticado + permiso granular de conflicto (deny-by-default)."""
    from core.conflict_authorization import tiene_permiso_conflict

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_conflict(_admin_permisos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_refund_permission(permiso_requerido: str):
    """Decorator: admin autenticado + permiso granular de refund (deny-by-default)."""
    from core.refund_authorization import tiene_permiso_refund

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_refund(_admin_permisos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_dispute_permission(permiso_requerido: str):
    """Decorator: admin autenticado + permiso granular de disputa (deny-by-default)."""
    from core.dispute_authorization import tiene_permiso_dispute

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_dispute(_admin_permisos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_reconciliation_permission(permiso_requerido: str):
    """Decorator: admin autenticado + permiso granular de reconciliación (deny-by-default)."""
    from core.reconciliation_authorization import tiene_permiso_recon

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_recon(_admin_permisos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_ledger_permission(permiso_requerido: str):
    """Decorator: admin autenticado + permiso granular de ledger (deny-by-default)."""
    from core.ledger_authorization import tiene_permiso_ledger

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_ledger(_admin_permisos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_financial_admin_permission(permiso_requerido: str):
    """Decorator: admin autenticado + permiso granular del panel financiero (deny-by-default)."""
    from core.financial_admin_authorization import tiene_permiso_panel

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_panel(_admin_permisos_efectivos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_financial_permission(permiso_requerido: str):
    """Decorator: admin + permiso financiero centralizado FASE 10 (deny-by-default)."""
    from core.financial_security_authorization import tiene_permiso_financiero

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_financiero(_admin_permisos_efectivos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_automation_permission(permiso_requerido: str):
    """Decorator: admin/cron + permiso de automatización financiera FASE 11."""
    from core.financial_automation_authorization import tiene_permiso_automation

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if _cron_secret_valid():
                return f(*args, **kwargs)
            if not _admin_session_valid() and not (
                _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
            ):
                return jsonify({
                    "status": "error",
                    "message": "Sesión admin expirada o no autorizado",
                }), 401
            if not tiene_permiso_automation(_admin_permisos_efectivos(), permiso_requerido):
                return jsonify({
                    "status": "error",
                    "message": f"Permiso requerido: {permiso_requerido}",
                    "permiso_requerido": permiso_requerido,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def _aliado_session_valid():
    """True si hay sesión de aliado válida."""
    s = _get_ruana_session()
    return bool(s and s.get("tipo") == "aliado" and s.get("codigo"))


def _aliado_codigo():
    """Código del aliado autenticado. None si no hay sesión válida."""
    s = _get_ruana_session()
    if s and s.get("tipo") == "aliado":
        return (s.get("codigo") or "").strip()
    return None


def require_aliado(f):
    """Decorator: exige sesión de aliado válida. 401 si no."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _aliado_session_valid():
            return jsonify({
                "status": "error",
                "message": "Sesión expirada o no autorizado. Inicia sesión con tu código.",
            }), 401
        return f(*args, **kwargs)
    return wrapped


def _forbidden_unless_admin_or_aliado_self(codigo):
    """None si admin o aliado consultando su propio código; si no, (response, status)."""
    codigo = (codigo or "").strip()
    if _admin_session_valid() or (
        _admin_jwt_payload() and _admin_jwt_payload().get("admin_codigo")
    ):
        return None
    aliado = _aliado_codigo()
    if aliado:
        if aliado == codigo:
            return None
        return jsonify({"status": "error", "message": "No autorizado"}), 403
    return jsonify({
        "status": "error",
        "message": "Sesión expirada o no autorizado. Inicia sesión con tu código.",
    }), 401
