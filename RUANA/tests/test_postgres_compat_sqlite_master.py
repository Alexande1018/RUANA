"""Traducción sqlite_master → information_schema en PostgresCompatCursor."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.postgres_compat import PostgresCompatCursor


def _compat_cursor():
    conn = MagicMock()
    conn._conn = MagicMock()
    inner = MagicMock()
    conn._conn.cursor.return_value = inner
    return PostgresCompatCursor(conn), inner


def test_select1_sqlite_master_table_exists():
    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"exists_flag": 1}

    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        ("contactos_ruana",),
    )

    assert cur.fetchone() == (1,)
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert inner.execute.call_args[0][1] == ("contactos_ruana",)


def test_select1_sqlite_master_table_missing():
    cur, inner = _compat_cursor()
    inner.fetchone.return_value = None

    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        ("missing_table",),
    )

    assert cur.fetchone() is None


def test_financial_admin_repo_tabla_existe_uses_information_schema_on_postgres():
    from core.repositories.financial_admin_repo import FinancialAdminRepo

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"exists_flag": 1}
    repo = FinancialAdminRepo()

    assert repo.tabla_existe(cur, "contactos_ruana") is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
