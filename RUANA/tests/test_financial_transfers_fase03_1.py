"""Tests FASE 03.1: eventos reales Stripe Connect para transferencias."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.financial.estados import EstadoFinanciero
from core.services import financial_transaction_service as fts
from core.services import pago_service
from core.services import stripe_webhook_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    from core.settings import get_settings

    get_settings.cache_clear()
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
    return db_module.DBManager(str(tmp_path / "ruana_fase031.db"))


def _seed(db, estado="TRANSFERENCIA_ENVIADA"):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "P", "p@t.com", "acct_test", 1),
    )
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, stripe_payment_intent_id, stripe_transfer_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, 500, 'stripe', 'cobro_confirmado', ?,
                  'ENVIADA', 440, 'pi_f031', 'tr_f031')
        """,
        ("SOL", "PRO", "Srv", estado),
    )
    cid = c.lastrowid
    c.execute(
        """
        INSERT INTO financial_transfers (
            contacto_id, idempotency_key, stripe_transfer_id, amount_cents, currency,
            destination_account_id, professional_codigo, stripe_payment_intent_id, estado
        ) VALUES (?, ?, 'tr_f031', 44000, 'eur', 'acct_test', 'PRO', 'pi_f031', 'STRIPE_CREADA')
        """,
        (cid, f"transfer-contacto-{cid}"),
    )
    conn.commit()
    conn.close()
    return cid


def _webhook(db, event_id, event_type, obj):
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data.object = obj
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig")


def _transfer_obj(cid, tid="tr_f031", **extra):
    base = {
        "id": tid,
        "amount": 44000,
        "currency": "eur",
        "destination": "acct_test",
        "reversed": False,
        "balance_transaction": "txn_bt_1",
        "destination_payment": "py_dest_1",
        "metadata": {"contacto_id": str(cid)},
    }
    base.update(extra)
    return base


def test_transfer_created_confirma_transferido(sqlite_db):
    cid = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_031_c", "transfer.created", _transfer_obj(cid))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    conn = sqlite_db._connect()
    ft = conn.execute(
        "SELECT estado, stripe_balance_transaction_id FROM financial_transfers WHERE contacto_id=?",
        (cid,),
    ).fetchone()
    ep = conn.execute("SELECT estado_pago FROM contactos_ruana WHERE id=?", (cid,)).fetchone()[0]
    conn.close()
    assert ep == "transferido"
    assert ft[0] == "COMPLETADA"
    assert ft[1] == "txn_bt_1"


def test_transfer_paid_legacy_alias(sqlite_db):
    cid = _seed(sqlite_db, estado="TRANSFERENCIA_ENVIADA")
    res = _webhook(sqlite_db, "evt_031_p", "transfer.paid", _transfer_obj(cid))
    assert res["status"] == "success"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_api_solo_enviada_webhook_confirma(mock_transfer, sqlite_db):
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "P", "p@t.com", "acct_test", 1),
    )
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, stripe_payment_intent_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, 500, 'stripe', 'cobro_confirmado',
                  'ESPERANDO_CONFIRMACION', 'RETENIDO', 440, 'pi_live')
        """,
        ("SOL", "PRO", "Srv"),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()

    mock_transfer.return_value = {"id": "tr_live"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["estado_financiero"] == "TRANSFERENCIA_ENVIADA"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA

    _webhook(sqlite_db, "evt_live", "transfer.created", _transfer_obj(cid, tid="tr_live"))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO


def test_transfer_updated_sync(sqlite_db):
    cid = _seed(sqlite_db, estado="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_pago='transferido', estado_transferencia='COMPLETADA' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    obj = _transfer_obj(cid, metadata={"contacto_id": str(cid), "sync": "1"})
    res = _webhook(sqlite_db, "evt_upd", "transfer.updated", obj)
    assert res["status"] == "success"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO


def test_transfer_reversed_desde_transferido(sqlite_db):
    cid = _seed(sqlite_db, estado="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_pago='transferido', estado_transferencia='COMPLETADA' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    _webhook(sqlite_db, "evt_rev", "transfer.reversed", _transfer_obj(cid, reversed=True))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_REVERTIDA


def test_importe_webhook_incoherente_bloquea(sqlite_db):
    cid = _seed(sqlite_db)
    res = _webhook(
        sqlite_db, "evt_bad", "transfer.created",
        _transfer_obj(cid, amount=99999),
    )
    assert res["status"] == "success"
    assert fts.obtener_estado_financiero(sqlite_db, cid) != EstadoFinanciero.TRANSFERIDO
