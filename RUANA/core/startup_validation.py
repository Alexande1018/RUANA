"""Validación de configuración al arranque (FASE 13A P0-1/2/3)."""
from __future__ import annotations

import os
import re
from typing import List

from core.runtime_environment import is_production, is_test_context, ruana_env

_INSECURE_FLASK_KEYS = frozenset({
    "",
    "ruana_secret_key_dev",
    "ruana_qa_secret_key",
})

_MIN_SECRET_LEN = 24


class StartupConfigurationError(RuntimeError):
    """Configuración inválida que impide arranque seguro."""


def _weak_secret(value: str) -> bool:
    v = (value or "").strip()
    if len(v) < _MIN_SECRET_LEN:
        return True
    if v.lower() in _INSECURE_FLASK_KEYS:
        return True
    if re.fullmatch(r"(.)\1{8,}", v):
        return True
    return False


def validate_stripe_mode_and_keys(*, stripe_mode: str, stripe_secret_key: str, production: bool) -> None:
    mode = (stripe_mode or "").strip().lower()
    key = (stripe_secret_key or "").strip()

    if production and mode not in ("test", "live"):
        raise StartupConfigurationError(
            "RUANA_STRIPE_MODE obligatorio en producción (test|live)"
        )
    if not production and not mode:
        return

    if mode not in ("test", "live"):
        raise StartupConfigurationError(f"RUANA_STRIPE_MODE inválido: {mode!r}")

    if not key:
        if production:
            raise StartupConfigurationError("STRIPE_SECRET_KEY obligatorio en producción")
        return

    if mode == "test" and not key.startswith("sk_test_"):
        raise StartupConfigurationError("RUANA_STRIPE_MODE=test requiere clave sk_test_")
    if mode == "live" and not key.startswith("sk_live_"):
        raise StartupConfigurationError("RUANA_STRIPE_MODE=live requiere clave sk_live_")


def validate_secrets(
    *,
    flask_secret_key: str,
    stripe_secret_key: str,
    stripe_webhook_secret: str,
    cron_secret: str,
    production: bool,
    financial_automation_active: bool = True,
) -> None:
    if production:
        if _weak_secret(flask_secret_key):
            raise StartupConfigurationError(
                "FLASK_SECRET_KEY obligatorio en producción (mín. 24 chars, sin default dev)"
            )
        if _weak_secret(stripe_secret_key):
            raise StartupConfigurationError("STRIPE_SECRET_KEY obligatorio o demasiado débil")
        if _weak_secret(stripe_webhook_secret):
            raise StartupConfigurationError("STRIPE_WEBHOOK_SECRET obligatorio o demasiado débil")
        if financial_automation_active and _weak_secret(cron_secret):
            raise StartupConfigurationError(
                "RUANA_CRON_SECRET obligatorio en producción (FASE 11 activa)"
            )
    elif is_test_context():
        return
    else:
        if flask_secret_key in _INSECURE_FLASK_KEYS and ruana_env() == "development":
            pass


def validate_cookie_policy(*, session_cookie_secure: bool, production: bool) -> None:
    if production and not session_cookie_secure:
        raise StartupConfigurationError(
            "SESSION_COOKIE_SECURE debe ser True en producción "
            "(RUANA_SESSION_COOKIE_SECURE=1)"
        )


def validate_startup_configuration(settings) -> None:
    """Lanza StartupConfigurationError si la configuración no es segura."""
    production = is_production()
    stripe_mode = os.environ.get("RUANA_STRIPE_MODE", "").strip().lower()
    if not stripe_mode and is_test_context():
        stripe_mode = "test"

    validate_stripe_mode_and_keys(
        stripe_mode=stripe_mode,
        stripe_secret_key=settings.stripe_secret_key,
        production=production,
    )
    validate_secrets(
        flask_secret_key=settings.flask_secret_key,
        stripe_secret_key=settings.stripe_secret_key,
        stripe_webhook_secret=settings.stripe_webhook_secret,
        cron_secret=os.environ.get("RUANA_CRON_SECRET", ""),
        production=production,
    )

    secure = os.environ.get("RUANA_SESSION_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")
    if production:
        secure = True
    validate_cookie_policy(session_cookie_secure=secure, production=production)


def collect_startup_errors(settings) -> List[str]:
    try:
        validate_startup_configuration(settings)
        return []
    except StartupConfigurationError as e:
        return [str(e)]
