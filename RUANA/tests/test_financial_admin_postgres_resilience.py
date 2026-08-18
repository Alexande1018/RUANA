"""Panel financiero: resiliencia ante esquema Postgres incompleto o legacy."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import db_manager as db_module
from core.repositories.financial_admin_repo import FinancialAdminRepo
from core.services import financial_admin_service as fas
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(
            postgres_configured=False,
            database_url="",
            public_app_url="http://localhost:5000",
            stripe_secret_key="sk_test_x",
            stripe_webhook_secret="whsec_test",
        ),
    )
    return db_module.DBManager(str(tmp_path / "ruana_fin_postgres_res.db"))


def _headers(session_headers, permisos=None):
    if permisos is None:
        permisos = ["leer"]
    return session_headers("admin", "ADMIN_PG", permisos=permisos)


def test_dashboard_kpis_legacy_payment_conflicts_no_estado_conflicto():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE payment_conflicts (
            id INTEGER PRIMARY KEY,
            trabajo_id INTEGER,
            estado TEXT DEFAULT 'PENDIENTE_PRUEBA',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        "INSERT INTO payment_conflicts (trabajo_id, estado) VALUES (1, 'PENDIENTE_PRUEBA')"
    )
    repo = FinancialAdminRepo()
    kpis = repo.dashboard_kpis(cur)
    assert "conflictos_abiertos" in kpis
    assert kpis["conflictos_abiertos"] == 1
    conn.close()


def test_dashboard_kpis_skips_contacto_columns_when_missing():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE contactos_ruana (
            id INTEGER PRIMARY KEY,
            estado TEXT
        )
        """
    )
    repo = FinancialAdminRepo()
    kpis = repo.dashboard_kpis(cur)
    assert "pagos_pendientes" not in kpis
    assert "dinero_retenido_cents" not in kpis
    conn.close()


def test_paginated_skips_count_when_table_missing(sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = _headers(session_headers)
    resp = sqlite_db  # ensure db init
    del resp
    client = app_module.app.test_client()
    r = client.get("/api/admin/financial/ledger?limit=10", headers=headers)
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert data["items"] == []


def test_stripe_webhook_failed_where_adapts_columns():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE stripe_webhook_events (
            id INTEGER PRIMARY KEY,
            stripe_event_id TEXT,
            tipo TEXT,
            estado_procesamiento TEXT,
            error_message TEXT
        )
        """
    )
    repo = FinancialAdminRepo()
    wh = repo._stripe_webhook_failed_where(cur)
    assert wh is not None
    assert "estado_procesamiento" in wh
    conn.close()


def test_scalar_compat_row_like_dict():
    repo = FinancialAdminRepo()
    row = MagicMock()
    row.keys.return_value = ["count"]
    row.__getitem__ = lambda self, k: {"count": 7}[k]
    row.values = lambda: iter([7])
    assert repo._scalar(row) == 7


def test_postgres_init_includes_financial_migrations_through_fase11():
    import inspect
    from core.services import schema_service

    source = inspect.getsource(schema_service._init_postgres_schema)
    for mig in (
        "_migrar_payment_conflicts",
        "_migrar_financial_fase04_conflicts",
        "_migrar_financial_fase05_refunds",
        "_migrar_financial_fase06_disputes",
        "_migrar_financial_fase07_reconciliation",
        "_migrar_financial_fase08_ledger",
        "_migrar_financial_fase09_admin_panel",
        "_migrar_financial_fase10_security",
        "_migrar_financial_fase11_automation",
    ):
        assert mig in source, f"Falta {mig} en _init_postgres_schema"
