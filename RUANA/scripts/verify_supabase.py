#!/usr/bin/env python3
"""Verify RUANA's Supabase setup without printing secrets."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from core.db_manager import ALIADO_FOTO_PERFIL_COLUMN
from core.settings import get_settings
from core.supabase_client import get_supabase_admin_client


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL missing")
        return 1
    if not settings.supabase_configured:
        print("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing")
        return 1

    with psycopg.connect(settings.database_url, autocommit=True, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            checks = {
                "public_tables": "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'",
                "aliados_foto_perfil_url": (
                    "select count(*) from information_schema.columns "
                    "where table_schema='public' and table_name='aliados' "
                    f"and column_name='{ALIADO_FOTO_PERFIL_COLUMN}'"
                ),
                "rls_enabled": "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relrowsecurity",
                "policies": "select count(*) from pg_policies where schemaname='public'",
                "realtime_tables": "select count(*) from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename in ('chat_mensajes','notificaciones_aliado','contactos_ruana')",
            }
            for name, query in checks.items():
                cur.execute(query)
                print(f"{name}: {cur.fetchone()[0]}")

    buckets = get_supabase_admin_client().storage.list_buckets()
    names = sorted(getattr(bucket, "name", None) or bucket.get("name") for bucket in buckets)
    expected = {"ruana-public", "ruana-comprobantes", "ruana-conflictos"}
    print("buckets:", ",".join(names))
    missing = expected.difference(names)
    if missing:
        print("missing_buckets:", ",".join(sorted(missing)))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
