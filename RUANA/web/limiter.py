"""Flask-Limiter: rate limiting por IP (memoria; multi-instancia fuera de alcance)."""

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
