#!/usr/bin/env python3
"""Aplica la migración RLS en Postgres (Supabase prod) de forma idempotente."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260902000200_enable_rls_public_tables.sql"

DIAGNOSTIC_SQL = """
SELECT c.relname AS tabla,
       c.relrowsecurity AS rls,
       c.relforcerowsecurity AS force_rls,
       (SELECT count(*) FROM pg_policies p
        WHERE p.schemaname = 'public' AND p.tablename = c.relname) AS politicas
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relrowsecurity, c.relname
"""


def _fetch_diag(cur) -> list[dict]:
    cur.execute(DIAGNOSTIC_SQL)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL no configurada", file=sys.stderr)
        return 1
    if not MIGRATION.is_file():
        print(f"Migración no encontrada: {MIGRATION}", file=sys.stderr)
        return 1

    dry_run = os.environ.get("RLS_DRY_RUN", "0").strip().lower() in ("1", "true", "yes")
    sql = MIGRATION.read_text(encoding="utf-8")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            before = _fetch_diag(cur)
            sin_rls = [r["tabla"] for r in before if not r["rls"]]
            print("=== RLS ANTES ===")
            print(f"tablas_public={len(before)} sin_rls={len(sin_rls)}")
            if sin_rls:
                print("sin_rls:", ", ".join(sin_rls[:30]), ("..." if len(sin_rls) > 30 else ""))

            if dry_run:
                print("=== DRY-RUN: migración no ejecutada ===")
                return 0

            if not sin_rls and os.environ.get("RLS_FORCE", "0") not in ("1", "true", "yes"):
                print("OK: todas las tablas public ya tienen RLS activo")
                return 0

            print("=== APLICANDO MIGRACIÓN RLS ===")
            cur.execute(sql)
            conn.commit()

            after = _fetch_diag(cur)
            sin_rls_after = [r["tabla"] for r in after if not r["rls"]]
            print("=== RLS DESPUÉS ===")
            print(json.dumps(
                {
                    "tablas_public": len(after),
                    "sin_rls": len(sin_rls_after),
                    "tablas_sin_rls": sin_rls_after,
                },
                ensure_ascii=False,
                indent=2,
            ))

    if sin_rls_after:
        print("ERROR: quedan tablas sin RLS", file=sys.stderr)
        return 1
    print("OK: migración RLS aplicada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
