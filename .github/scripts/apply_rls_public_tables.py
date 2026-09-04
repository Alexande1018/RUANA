#!/usr/bin/env python3
"""Aplica la migración RLS public (idempotente) contra DATABASE_URL."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.pq import ExecStatus

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260902000200_enable_rls_public_tables.sql"


def main() -> int:
    url = __import__("os").environ.get("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL no configurada", file=sys.stderr)
        return 1
    if not MIGRATION.is_file():
        print(f"Migración no encontrada: {MIGRATION}", file=sys.stderr)
        return 1
    sql = MIGRATION.read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        result = conn.pgconn.exec_(sql.encode("utf-8"))
        status = result.status
        if status == ExecStatus.FATAL_ERROR:
            err = (result.error_message or b"").decode("utf-8", errors="replace")
            print(f"ERROR aplicando RLS: {err}", file=sys.stderr)
            return 1
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FILTER (WHERE NOT c.relrowsecurity) AS sin_rls,
                       COUNT(*) AS total
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                """
            )
            sin_rls, total = cur.fetchone()
    print(f"RLS public: tablas={total} sin_rls={sin_rls}")
    if int(sin_rls or 0) != 0:
        print("ERROR: quedan tablas public sin RLS", file=sys.stderr)
        return 1
    print("OK: RLS activo en todas las tablas public (sin FORCE)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
