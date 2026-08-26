"""stripe_webhook_events.id en Postgres: SERIAL + reclamar_evento."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.repositories.stripe_webhook_repo import StripeWebhookRepo
from core.services import schema_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    return db_module.DBManager(str(tmp_path / "wh_events_id.db"))


def test_reclamar_evento_generates_id_sqlite(sqlite_db):
    repo = StripeWebhookRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    claim = repo.reclamar_evento(cur, "evt_dispute_created", "charge.dispute.created")
    conn.commit()
    assert claim == "claimed"
    row = cur.execute(
        "SELECT id, tipo FROM stripe_webhook_events WHERE stripe_event_id = ?",
        ("evt_dispute_created",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is not None and int(row[0]) > 0
    assert row[1] == "charge.dispute.created"


def test_reclamar_evento_idempotencia_sqlite(sqlite_db):
    repo = StripeWebhookRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    first = repo.reclamar_evento(cur, "evt_dup_id", "charge.dispute.created")
    conn.commit()
    second = repo.reclamar_evento(cur, "evt_dup_id", "charge.dispute.created")
    conn.commit()
    count = cur.execute(
        "SELECT COUNT(*) FROM stripe_webhook_events WHERE stripe_event_id = ?",
        ("evt_dup_id",),
    ).fetchone()[0]
    conn.close()
    assert first == "claimed"
    assert second == "duplicate_processing"
    assert count == 1


def test_migrar_stripe_pagos_postgres_create_uses_serial_primary_key():
    db = MagicMock()
    db.backend = "postgres"
    conn = MagicMock()
    cursor = MagicMock()
    executed: list[str] = []

    def record_execute(sql, params=()):
        executed.append(str(sql))
        return cursor

    cursor.execute = record_execute
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []

    with patch.object(schema_service._repo, "columnas_tabla", return_value=[]):
        with patch.object(schema_service._repo, "tabla_existe", return_value=True):
            schema_service._migrar_stripe_pagos(db, conn, cursor)

    create_sql = next(s for s in executed if "CREATE TABLE IF NOT EXISTS stripe_webhook_events" in s)
    assert "SERIAL PRIMARY KEY" in create_sql
    assert "AUTOINCREMENT" not in create_sql.upper()


def test_asegurar_stripe_webhook_events_id_serial_skips_when_default_exists():
    db = MagicMock()
    db.backend = "postgres"
    cursor = MagicMock()
    executed: list[str] = []

    def record_execute(sql, params=()):
        executed.append(str(sql))
        return cursor

    cursor.execute = record_execute
    cursor.fetchone.return_value = ("nextval('stripe_webhook_events_id_seq'::regclass)",)

    with patch.object(schema_service._repo, "tabla_existe", return_value=True):
        schema_service._asegurar_stripe_webhook_events_id_serial_postgres(db, cursor)

    assert not any("CREATE SEQUENCE" in s for s in executed)


def test_asegurar_stripe_webhook_events_id_serial_repairs_missing_default():
    db = MagicMock()
    db.backend = "postgres"
    cursor = MagicMock()
    executed: list[str] = []

    def record_execute(sql, params=()):
        executed.append(str(sql))
        return cursor

    cursor.execute = record_execute
    cursor.fetchone.return_value = (None,)

    with patch.object(schema_service._repo, "tabla_existe", return_value=True):
        schema_service._asegurar_stripe_webhook_events_id_serial_postgres(db, cursor)

    assert any("CREATE SEQUENCE IF NOT EXISTS stripe_webhook_events_id_seq" in s for s in executed)
    assert any("ALTER COLUMN id SET DEFAULT nextval" in s for s in executed)
    assert any("OWNED BY stripe_webhook_events.id" in s for s in executed)


def test_asegurar_stripe_webhook_events_id_serial_noop_on_sqlite():
    db = MagicMock()
    db.backend = "sqlite"
    cursor = MagicMock()
    schema_service._asegurar_stripe_webhook_events_id_serial_postgres(db, cursor)
    cursor.execute.assert_not_called()
