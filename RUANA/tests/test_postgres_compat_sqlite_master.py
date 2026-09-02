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


def test_regression_encargo72_select_name_sqlite_master_placeholder():
    """Reproduce el bug original: SELECT name FROM sqlite_master ... name=? iba a Postgres.

    Sin el traductor, inner.execute recibe sqlite_master (init abortado → webhook 500).
    Con el fix, se reescribe a information_schema.tables.
    """
    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "stripe_webhook_events"}
    original_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"

    cur.execute(original_sql, ("stripe_webhook_events",))

    sent = inner.execute.call_args[0][0]
    assert "sqlite_master" not in sent
    assert "information_schema.tables" in sent
    assert inner.execute.call_args[0][1] == ("stripe_webhook_events",)
    assert cur.fetchone() == ("stripe_webhook_events",)


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


# Consultas exactas de los seis repos financieros (mismo patrón sqlite_master).
# El traductor es genérico: (name|1) + placeholder o literal + LIMIT opcional.
_FINANCIAL_SQLITE_MASTER_CASES = (
    (
        "financial_transfer_repo",
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_transfers' LIMIT 1",
        (),
        "financial_transfers",
    ),
    (
        "financial_refund_repo",
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_refunds' LIMIT 1",
        (),
        "financial_refunds",
    ),
    (
        "financial_reconciliation_advanced_repo",
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        ("financial_reconciliation_executions",),
        "financial_reconciliation_executions",
    ),
    (
        "financial_ledger_repo",
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        ("ledger_transactions",),
        "ledger_transactions",
    ),
    (
        "financial_dispute_repo",
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_disputes' LIMIT 1",
        (),
        "financial_disputes",
    ),
    (
        "financial_conflict_repo",
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='payment_conflicts' LIMIT 1",
        (),
        "payment_conflicts",
    ),
)


def test_sqlite_master_regex_covers_all_six_financial_repos():
    from core.postgres_compat import _SQLITE_MASTER_RE

    for repo_name, sql, _params, expected_table in _FINANCIAL_SQLITE_MASTER_CASES:
        match = _SQLITE_MASTER_RE.match(sql.strip())
        assert match, f"{repo_name}: regex no cubre {sql!r}"
        assert (match.group(1) or "").lower() == "1"
        assert (match.group(2) or "").lower() == "table"
        literal = match.group(3)
        if literal:
            assert literal == expected_table, repo_name


def test_six_financial_repo_sqlite_master_queries_translate_to_information_schema():
    """Cada SQL exacta de los seis repos se reescribe; Postgres no ve sqlite_master."""
    for repo_name, sql, params, expected_table in _FINANCIAL_SQLITE_MASTER_CASES:
        cur, inner = _compat_cursor()
        inner.fetchone.return_value = {"name": expected_table}
        cur.execute(sql, params)
        sent = inner.execute.call_args[0][0]
        sent_params = inner.execute.call_args[0][1]
        assert "sqlite_master" not in sent, repo_name
        assert "information_schema.tables" in sent, repo_name
        assert sent_params == (expected_table,), repo_name
        assert cur.fetchone() == (1,), repo_name


def test_financial_transfer_repo_tabla_existe_does_not_query_sqlite_master():
    from core.repositories.financial_transfer_repo import FinancialTransferRepo

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "financial_transfers"}
    assert FinancialTransferRepo().tabla_existe(cur) is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql
    assert inner.execute.call_args[0][1] == ("financial_transfers",)


def test_financial_refund_repo_tabla_existe_does_not_query_sqlite_master():
    from core.repositories.financial_refund_repo import FinancialRefundRepo

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "financial_refunds"}
    assert FinancialRefundRepo().tabla_existe(cur) is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql
    assert inner.execute.call_args[0][1] == ("financial_refunds",)


def test_financial_reconciliation_advanced_repo_tabla_existe_does_not_query_sqlite_master():
    from core.repositories.financial_reconciliation_advanced_repo import (
        FinancialReconciliationAdvancedRepo,
    )

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "financial_reconciliation_executions"}
    assert FinancialReconciliationAdvancedRepo().tabla_existe(
        cur, "financial_reconciliation_executions"
    ) is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql
    assert inner.execute.call_args[0][1] == ("financial_reconciliation_executions",)


def test_financial_ledger_repo_tabla_existe_does_not_query_sqlite_master():
    from core.repositories.financial_ledger_repo import FinancialLedgerRepo

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "ledger_transactions"}
    assert FinancialLedgerRepo().tabla_existe(cur, "ledger_transactions") is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql
    assert inner.execute.call_args[0][1] == ("ledger_transactions",)


def test_financial_dispute_repo_tabla_existe_does_not_query_sqlite_master():
    from core.repositories.financial_dispute_repo import FinancialDisputeRepo

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "financial_disputes"}
    assert FinancialDisputeRepo().tabla_existe(cur) is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql
    assert inner.execute.call_args[0][1] == ("financial_disputes",)


def test_financial_conflict_repo_tabla_existe_does_not_query_sqlite_master():
    from core.repositories.financial_conflict_repo import FinancialConflictRepo

    cur, inner = _compat_cursor()
    inner.fetchone.return_value = {"name": "payment_conflicts"}
    assert FinancialConflictRepo().tabla_existe(cur) is True
    sql = inner.execute.call_args[0][0]
    assert "information_schema.tables" in sql
    assert "sqlite_master" not in sql
    assert inner.execute.call_args[0][1] == ("payment_conflicts",)
