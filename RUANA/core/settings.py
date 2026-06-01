"""Runtime settings for RUANA.

Secrets are read from environment variables. In local development, create a
repo-root `.env.local` or `.env` file and load it before starting Flask.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is optional at import time
    load_dotenv = None


def _load_env_files() -> None:
    if load_dotenv is None:
        return

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env.local", override=False)
    load_dotenv(root / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    firebase_project_id: str = os.environ.get("FIREBASE_PROJECT_ID", "ruana-4293f")
    public_app_url: str = os.environ.get("RUANA_PUBLIC_APP_URL", "")
    google_cloud_region: str = os.environ.get("GOOGLE_CLOUD_REGION", "europe-west1")
    supabase_url: str = os.environ.get("SUPABASE_URL", "")
    supabase_anon_key: str = os.environ.get("SUPABASE_ANON_KEY", "")
    supabase_service_role_key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    database_url: str = os.environ.get("DATABASE_URL", "")
    flask_secret_key: str = os.environ.get("FLASK_SECRET_KEY", "ruana_secret_key_dev")

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def postgres_configured(self) -> bool:
        return bool(self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_files()
    firebase_project_id = os.environ.get("FIREBASE_PROJECT_ID", "ruana-4293f")
    public_app_url = (
        os.environ.get("RUANA_PUBLIC_APP_URL", "")
        or os.environ.get("PUBLIC_APP_URL", "")
        or f"https://{firebase_project_id}.web.app"
    )
    return Settings(
        firebase_project_id=firebase_project_id,
        public_app_url=public_app_url.rstrip("/"),
        google_cloud_region=os.environ.get("GOOGLE_CLOUD_REGION", "europe-west1"),
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        database_url=os.environ.get("DATABASE_URL", ""),
        flask_secret_key=os.environ.get("FLASK_SECRET_KEY", "ruana_secret_key_dev"),
    )
