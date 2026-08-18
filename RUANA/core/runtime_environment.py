"""Detección de entorno de ejecución RUANA (FASE 13A)."""
from __future__ import annotations

import os


def ruana_env() -> str:
    """development | test | production (vacío → development en local)."""
    explicit = (os.environ.get("RUANA_ENV") or "").strip().lower()
    if explicit:
        return explicit
    flask_env = (os.environ.get("FLASK_ENV") or "").strip().lower()
    if flask_env == "production":
        return "production"
    if os.environ.get("CI", "").strip().lower() in ("1", "true", "yes"):
        return "test"
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "test"
    return "development"


def is_production() -> bool:
    if ruana_env() == "production":
        return True
    return bool((os.environ.get("K_SERVICE") or "").strip())


def is_test_context() -> bool:
    env = ruana_env()
    return env in ("test", "development") or bool(os.environ.get("PYTEST_CURRENT_TEST"))
