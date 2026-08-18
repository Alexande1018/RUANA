"""Rate limiting para mutaciones financieras sensibles (FASE 10)."""
from __future__ import annotations

from functools import wraps

from web.limiter import limiter

FINANCIAL_MUTATION_LIMIT = "60 per hour; 15 per minute"


def limit_financial_mutation(f):
    """Aplica rate limit a endpoints de mutación financiera."""
    @wraps(f)
    @limiter.limit(FINANCIAL_MUTATION_LIMIT)
    def wrapped(*args, **kwargs):
        return f(*args, **kwargs)
    return wrapped
