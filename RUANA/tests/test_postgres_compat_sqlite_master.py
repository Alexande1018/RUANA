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
    inner.fetchone.return_value = {"name": "contactos_ruana"}

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


def test_select_name_sqlite_master_placeholder_uses_information_schema():
    """SchemaRepo.tabla_existe (antes SELECT name ... name=?) abortaba el init de Postgres."""
    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "stripe_webhook_events"}

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        ("stripe_webhook_events",),
    )

    row = cur.fetchone()
    assert row == ("stripe_webhook_events",)
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql
    assert inner.execute.call_args[0][1] == ("stripe_webhook_events",)


def test_schema_repo_tabla_existe_does_not_query_sqlite_master_on_postgres():
    from core.repositories.schema_repo import SchemaRepo

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "stripe_webhook_events"}
    repo = SchemaRepo()

    assert repo.tabla_existe(cur, "stripe_webhook_events") is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql


def test_select_name_sqlite_master_index_uses_pg_indexes():
    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "idx_contacto_aliado"}

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_contacto_aliado'"
    )

    assert cur.fetchone() == ("idx_contacto_aliado",)
    sql = inner.execute.call_args[0][0]
    assert "pg_indexes" in sql


def test_insert_or_ignore_skips_lastval_probe():
    cur, inner = _compat_cursor()
    inner.execute.return_value = None
    inner.description = None

    cur.execute(
        "INSERT OR IGNORE INTO stripe_webhook_events (stripe_event_id, tipo) VALUES (?, ?)",
        ("evt_1", "checkout.session.completed"),
    )

    executed = [str(c[0][0]) for c in inner.execute.call_args_list]
    assert any("ON CONFLICT" in s.upper() for s in executed)
    assert not any("lastval" in s.lower() for s in executed)
