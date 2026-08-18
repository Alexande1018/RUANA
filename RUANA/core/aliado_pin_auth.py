"""Utilidades de PIN personal para aliados RUANA.

Reutiliza el mismo mecanismo de hash que admin_auth (Werkzeug).
No almacena PIN ni hashes en logs.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Optional

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from core.auth_session import _resolve_session_secret

PIN_REGEX = re.compile(r"^\d{4,6}$")
GENERIC_CREDENTIALS_ERROR = "Credenciales incorrectas"

PIN_MAX_INTENTOS = int(os.environ.get("RUANA_PIN_MAX_INTENTOS", "5"))
PIN_BLOQUEO_SEGUNDOS = int(os.environ.get("RUANA_PIN_BLOQUEO_MINUTOS", "15")) * 60
PIN_SETUP_EXPIRES_SECONDS = int(os.environ.get("RUANA_PIN_SETUP_EXPIRES", "900"))


def validar_formato_pin(pin: str) -> bool:
    return bool(PIN_REGEX.match((pin or "").strip()))


def hash_pin(pin: str) -> str:
    return generate_password_hash((pin or "").strip())


def verificar_pin(pin: str, pin_hash: str) -> bool:
    stored = (pin_hash or "").strip()
    if not stored:
        return False
    return check_password_hash(stored, (pin or "").strip())


def crear_setup_token(codigo: str) -> str:
    payload = {
        "typ": "pin_setup",
        "codigo": (codigo or "").strip(),
        "exp": int(time.time()) + PIN_SETUP_EXPIRES_SECONDS,
    }
    return jwt.encode(payload, _resolve_session_secret(), algorithm="HS256")


def validar_setup_token(token: str) -> Optional[str]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, _resolve_session_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "pin_setup":
        return None
    codigo = (payload.get("codigo") or "").strip()
    return codigo or None


def esta_bloqueado_por_pin(aliado: dict[str, Any]) -> bool:
    bloqueado_hasta = aliado.get("pin_bloqueado_hasta")
    if not bloqueado_hasta:
        return False
    try:
        from datetime import datetime

        if isinstance(bloqueado_hasta, (int, float)):
            return time.time() < float(bloqueado_hasta)
        texto = str(bloqueado_hasta).strip()
        if not texto:
            return False
        if texto.replace(".", "", 1).isdigit():
            return time.time() < float(texto)
        valor = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if valor.tzinfo is not None:
            return time.time() < valor.timestamp()
        return time.time() < valor.timestamp()
    except Exception:
        return False
