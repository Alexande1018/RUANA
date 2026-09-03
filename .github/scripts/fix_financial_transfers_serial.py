#!/usr/bin/env python3
"""Reparación idempotente: DEFAULT nextval en financial_transfers.id (encargo #72)."""
from __future__ import annotations

import os
import sys

import psycopg

SQL = """
CREATE SEQUENCE IF NOT EXISTS financial_transfers_id_seq;
SELECT setval(
    'financial_transfers_id_seq',
    COALESCE((SELECT MAX(id) FROM financial_transfers), 0) + 1,
    false
);
ALTER TABLE financial_transfers
    ALTER COLUMN id SET DEFAULT nextval('financial_transfers_id_seq');
ALTER SEQUENCE financial_transfers_id_seq OWNED BY financial_transfers.id;
"""


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL no configurada", file=sys.stderr)
        return 1
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
            cur.execute(
                """
                SELECT column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'financial_transfers'
                  AND column_name = 'id'
                """
            )
            row = cur.fetchone()
            default = row[0] if row else None
    print(f"financial_transfers.id column_default={default!r}")
    if not default or "nextval" not in str(default):
        print("ERROR: id sigue sin DEFAULT nextval", file=sys.stderr)
        return 1
    print("OK: financial_transfers.id tiene SERIAL/DEFAULT nextval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
