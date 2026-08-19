"""Rate limiting para mutaciones financieras sensibles (FASE 10 / FASE 14)."""
from __future__ import annotations

from functools import wraps

from web.limiter import limiter

FINANCIAL_MUTATION_LIMIT = "60 per hour; 15 per minute"
STRIPE_WEBHOOK_LIMIT = "300 per hour; 60 per minute"


def limit_financial_mutation(f):
    """Aplica rate limit a endpoints de mutación financiera."""
    @wraps(f)
    @limiter.limit(FINANCIAL_MUTATION_LIMIT)
    def wrapped(*args, **kwargs):
        return f(*args, **kwargs)
    return wrapped


def limit_stripe_webhook(f):
    """Rate limit para webhook Stripe (firma verificada; límite alto por reintentos)."""
    @wraps(f)
    @limiter.limit(STRIPE_WEBHOOK_LIMIT)
    def wrapped(*args, **kwargs):
        return f(*args, **kwargs)
    return wrapped
