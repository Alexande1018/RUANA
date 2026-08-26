"""Flask-Limiter: rate limiting por IP (memoria; multi-instancia fuera de alcance)."""

import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)


def init_limiter(app):
    limiter.init_app(app)
    if app.config.get("TESTING"):
        limiter.enabled = False
        return
    # E2E/CI: SQLite local o runner GitHub — sin límite por IP en memoria.
    if os.environ.get("RUANA_DISABLE_RATE_LIMIT", "").strip().lower() in ("1", "true", "yes"):
        limiter.enabled = False
        return
    if os.environ.get("CI", "").strip().lower() in ("1", "true", "yes"):
        limiter.enabled = False
        return
    if os.environ.get("RUANA_DB_PATH", "").strip():
        limiter.enabled = False
