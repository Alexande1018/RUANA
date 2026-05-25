"""Supabase helpers for server-side RUANA code.

Use the service role key only on the backend. Frontend code should use the anon
key together with Row Level Security.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from core.settings import get_settings


@lru_cache(maxsize=1)
def get_supabase_admin_client() -> Client:
    settings = get_settings()
    if not settings.supabase_configured:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
