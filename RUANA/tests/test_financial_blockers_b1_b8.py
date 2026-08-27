"""Tests corrección bloqueadores B1/B2/B3/B4/B7/B8 (webhooks, ledger, refunds, arranque)."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.financial.estados import EstadoFinanciero
from core.repositories.stripe_webhook_repo import StripeWebhookRepo
from core.services import financial_automation_service as fas
from core.services import financial_refund_service as frs
from core.services import financial_transaction_service as fts
from core.services import pago_service
from core.services import stripe_webhook_service
from core.startup_validation import StartupConfigurationError, validate_startup_configuration


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RUANA_STRIPE_MODE", "test")
    monkeypatch.setenv("RUANA_WEBHOOK_PROCESSING_STUCK_MINUTES", "1")
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
            flask_secret_key="x" * 32,
        ),
    )
    return db_module.DBManager(str(tmp_path / "blockers.db"))


def _mock_event(event_id, event_type, obj):
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.livemode = False
    event.data.object = obj
    return event


def _seed_stripe(db, importe=500.0, estado_financiero="PAGO_PENDIENTE"):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "P", "p@t.com", "acct_test", 1),
    )
    apoyo = round(importe * 0.12, 2)
    neto = round(importe - apoyo, 2)
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, apoyo_ruana, comision
        ) VALUES (?, ?, ?, 'pendiente_de_pago', 0, ?, 'stripe', 'esperando_cobro_cliente', ?,
                  'NO_APLICA', ?, ?, ?)
        """,
        ("SOL", "PRO", "Srv", importe, estado_financiero, neto, apoyo, apoyo),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def _procesar(db, event_id, event_type, obj, *, side_effect=None, _patched=True):
    event = _mock_event(event_id, event_type, obj)
    if not _patched:
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig_valid")
    patches = [patch("core.stripe_client.construct_webhook_event", return_value=event)]
    if side_effect is not None:
        patches.append(
            patch(
                "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
                side_effect=side_effect,
            )
        )
    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig_valid")


# --- B1: failed → retry → completed ---


def test_b1_failed_retry_then_succeeded(sqlite_db):
    """failed → retry Stripe → processing → completed sin duplicar cobro."""
    cid = _seed_stripe(sqlite_db)
    obj = {
        "payment_status": "paid",
        "payment_intent": "pi_retry_ok",
        "metadata": {"contacto_id": str(cid)},
        "id": "cs_retry",
    }
    r1 = _procesar(sqlite_db, "evt_retry_b1", "checkout.session.completed", obj, side_effect=RuntimeError("temporal"))
    assert r1["status"] == "error"
    assert r1.get("code") == "processing_error"

    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_procesamiento FROM stripe_webhook_events WHERE stripe_event_id='evt_retry_b1'"
    ).fetchone()
    conn.close()
    assert row[0] == "failed"

    r2 = _procesar(sqlite_db, "evt_retry_b1", "checkout.session.completed", obj)
    assert r2["status"] == "success"
    assert not r2.get("duplicate")

    conn = sqlite_db._connect()
    estado_wh = conn.execute(
        "SELECT estado_procesamiento FROM stripe_webhook_events WHERE stripe_event_id='evt_retry_b1'"
    ).fetchone()[0]
    count_ingresos = conn.execute(
        "SELECT COUNT(*) FROM ingresos_ruana WHERE contacto_id=?", (cid,)
    ).fetchone()[0]
    conn.close()
    assert estado_wh == "completed"
    assert count_ingresos == 1


# --- B2: processing atascado → reclaim ---


def test_b2_stuck_processing_reclaimed(sqlite_db):
    repo = StripeWebhookRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    repo.reclamar_evento(cur, "evt_stuck_b2", "checkout.session.completed")
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "UPDATE stripe_webhook_events SET procesado_en = ? WHERE stripe_event_id = ?",
        (old, "evt_stuck_b2"),
    )
    conn.commit()
    second = repo.reclamar_evento(cur, "evt_stuck_b2", "checkout.session.completed")
    conn.commit()
    conn.close()
    assert second == "claimed"


# --- B1/B2: completed duplicate_ok ---


def test_completed_duplicate_ok_no_reprocess(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    obj = {
        "payment_status": "paid",
        "payment_intent": "pi_dup_ok",
        "metadata": {"contacto_id": str(cid)},
        "id": "cs_dup",
    }
    r1 = _procesar(sqlite_db, "evt_dup_ok", "checkout.session.completed", obj)
    r2 = _procesar(sqlite_db, "evt_dup_ok", "checkout.session.completed", obj)
    assert r1["status"] == "success"
    assert r2.get("duplicate") is True
    conn = sqlite_db._connect()
    count = conn.execute("SELECT COUNT(*) FROM ingresos_ruana WHERE contacto_id=?", (cid,)).fetchone()[0]
    conn.close()
    assert count == 1


# --- Concurrencia ---


def test_concurrencia_mismo_event_id_un_solo_cobro(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    obj = {
        "payment_status": "paid",
        "payment_intent": "pi_conc_b1",
        "metadata": {"contacto_id": str(cid)},
        "id": "cs_conc",
    }
    event = _mock_event("evt_conc_b1", "checkout.session.completed", obj)
    results = []
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        results.append(_procesar(sqlite_db, "evt_conc_b1", "checkout.session.completed", obj, _patched=False))

    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        t1 = threading.Thread(target=run)
        t2 = threading.Thread(target=run)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    success = sum(1 for r in results if r.get("status") == "success" and not r.get("duplicate"))
    duplicates = sum(1 for r in results if r.get("duplicate"))
    assert success + duplicates == 2
    conn = sqlite_db._connect()
    count = conn.execute("SELECT COUNT(*) FROM ingresos_ruana WHERE contacto_id=?", (cid,)).fetchone()[0]
    conn.close()
    assert count <= 1


# --- B3: detectar webhooks usa procesado_en ---


def test_b3_detectar_webhooks_failed_no_sql_error(sqlite_db):
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO stripe_webhook_events (
            stripe_event_id, tipo, resultado, estado_procesamiento, procesado_en
        ) VALUES ('evt_fail_b3', 'checkout.session.completed', 'error', 'failed', CURRENT_TIMESTAMP)
        """
    )
    conn.commit()
    stats = fas._detectar_webhooks(c, "run_b3")
    conn.close()
    assert stats["nuevas"] >= 1 or stats["actualizadas"] >= 1


# --- B4: ledger fallo genera alerta ---


def test_b4_ledger_fallo_genera_alerta(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    obj = {
        "payment_status": "paid",
        "payment_intent": "pi_ledger_fail",
        "metadata": {"contacto_id": str(cid)},
        "id": "cs_ledger",
    }
    with patch(
        "core.services.financial_ledger_hooks.fls.registrar_pago_confirmado",
        return_value={"status": "error", "message": "ledger roto"},
    ):
        r = _procesar(sqlite_db, "evt_ledger_b4", "checkout.session.completed", obj)
    assert r["status"] == "error"
    conn = sqlite_db._connect()
    alertas = conn.execute(
        "SELECT COUNT(*) FROM financial_alerts WHERE tipo = 'ledger_hook_fallido'"
    ).fetchone()[0]
    conn.close()
    assert alertas >= 1


# --- B7: charge.refunded crea financial_refunds + ledger ---


def test_b7_charge_refunded_unificado_ledger(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_payment_intent_id='pi_ref_b7' WHERE id=?", (cid,)
    )
    conn.commit()
    conn.close()
    _procesar(
        sqlite_db,
        "evt_ref_b7",
        "charge.refunded",
        {
            "id": "ch_b7",
            "payment_intent": "pi_ref_b7",
            "amount_refunded": 50000,
            "currency": "eur",
            "refunds": {
                "data": [{
                    "id": "re_b7_test",
                    "amount": 50000,
                    "status": "succeeded",
                    "charge": "ch_b7",
                    "payment_intent": "pi_ref_b7",
                }],
            },
        },
    )
    conn = sqlite_db._connect()
    fin = conn.execute(
        "SELECT COUNT(*) FROM financial_refunds WHERE contacto_id=? AND stripe_refund_id='re_b7_test'",
        (cid,),
    ).fetchone()[0]
    ledger = conn.execute(
        "SELECT COUNT(*) FROM ledger_transactions WHERE contacto_id=?",
        (cid,),
    ).fetchone()[0]
    conn.close()
    assert fin == 1
    assert ledger >= 1


# --- B8: arranque fatal mismatch modo/clave ---


def test_b8_startup_fatal_mismatch_mode_key(monkeypatch):
    monkeypatch.setenv("RUANA_ENV", "production")
    monkeypatch.setenv("K_SERVICE", "ruana")
    monkeypatch.setenv("RUANA_STRIPE_MODE", "live")
    with pytest.raises(StartupConfigurationError, match="sk_live_"):
        validate_startup_configuration(
            SimpleNamespace(
                flask_secret_key="x" * 32,
                stripe_secret_key="sk_test_" + "x" * 20,
                stripe_webhook_secret="whsec_" + "x" * 24,
            )
        )
