"""Reintentos Stripe webhook: failed → reclaim, completed → idempotencia."""
from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.financial.estados import EstadoFinanciero
from core.repositories.stripe_webhook_repo import StripeWebhookRepo
from core.services import financial_transaction_service as fts
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
    return db_module.DBManager(str(tmp_path / "wh_retry.db"))


def _mock_event(event_id, event_type, obj):
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data.object = obj
    event.livemode = False
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


def _procesar(db, event_id, event_type, obj):
    event = _mock_event(event_id, event_type, obj)
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig_valid")


def _checkout_obj(cid):
    return {
        "payment_status": "paid",
        "payment_intent": f"pi_{cid}",
        "metadata": {"contacto_id": str(cid)},
        "id": f"cs_{cid}",
    }


def test_01_nuevo_evento_se_procesa_una_vez(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    res = _procesar(sqlite_db, "evt_new_once", "checkout.session.completed", _checkout_obj(cid))
    assert res["status"] == "success"
    assert not res.get("duplicate")
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_procesamiento FROM stripe_webhook_events WHERE stripe_event_id='evt_new_once'"
    ).fetchone()
    conn.close()
    assert row[0] == "completed"


def test_02_completed_reenvio_no_reprocesa(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    obj = _checkout_obj(cid)
    r1 = _procesar(sqlite_db, "evt_completed_dup", "checkout.session.completed", obj)
    r2 = _procesar(sqlite_db, "evt_completed_dup", "checkout.session.completed", obj)
    assert r1["status"] == "success"
    assert r2.get("duplicate") is True
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.ESPERANDO_CONFIRMACION


def test_03_failed_reenvio_reclama_y_reprocesa(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    event = _mock_event(
        "evt_failed_retry", "checkout.session.completed", _checkout_obj(cid),
    )
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        with patch(
            "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
            side_effect=RuntimeError("temporal"),
        ):
            r_fail = stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "sig")
    assert r_fail["status"] == "error"
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_procesamiento FROM stripe_webhook_events WHERE stripe_event_id='evt_failed_retry'"
    ).fetchone()
    conn.close()
    assert row[0] == "failed"

    r_retry = _procesar(sqlite_db, "evt_failed_retry", "checkout.session.completed", _checkout_obj(cid))
    assert r_retry["status"] == "success"
    assert not r_retry.get("duplicate")
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.ESPERANDO_CONFIRMACION


def test_04_falla_dos_veces_permite_tercer_intento(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    event = _mock_event("evt_fail_twice", "checkout.session.completed", _checkout_obj(cid))
    for _ in range(2):
        with patch("core.stripe_client.construct_webhook_event", return_value=event):
            with patch(
                "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
                side_effect=RuntimeError("temporal"),
            ):
                res = stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "sig")
        assert res["status"] == "error"
    conn = sqlite_db._connect()
    estado = conn.execute(
        "SELECT estado_procesamiento FROM stripe_webhook_events WHERE stripe_event_id='evt_fail_twice'"
    ).fetchone()[0]
    conn.close()
    assert estado == "failed"

    r_ok = _procesar(sqlite_db, "evt_fail_twice", "checkout.session.completed", _checkout_obj(cid))
    assert r_ok["status"] == "success"
    conn = sqlite_db._connect()
    estado = conn.execute(
        "SELECT estado_procesamiento FROM stripe_webhook_events WHERE stripe_event_id='evt_fail_twice'"
    ).fetchone()[0]
    conn.close()
    assert estado == "completed"


def test_05_exito_tras_fallo_bloquea_reenvios_posteriores(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    event = _mock_event("evt_fail_then_ok", "checkout.session.completed", _checkout_obj(cid))
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        with patch(
            "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
            side_effect=RuntimeError("temporal"),
        ):
            stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "sig")
    r_ok = _procesar(sqlite_db, "evt_fail_then_ok", "checkout.session.completed", _checkout_obj(cid))
    assert r_ok["status"] == "success"
    r_dup = _procesar(sqlite_db, "evt_fail_then_ok", "checkout.session.completed", _checkout_obj(cid))
    assert r_dup.get("duplicate") is True


def test_06_concurrencia_mismo_evento_nuevo_un_solo_handler(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    obj = _checkout_obj(cid)
    calls = []
    call_lock = threading.Lock()
    barrier = threading.Barrier(2)
    results = []

    def track_pago(*_args, **_kwargs):
        with call_lock:
            calls.append(1)
        return {"status": "success"}

    def run():
        barrier.wait()
        results.append(_procesar(sqlite_db, "evt_conc_new", "checkout.session.completed", obj))

    with patch(
        "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
        side_effect=track_pago,
    ):
        t1 = threading.Thread(target=run)
        t2 = threading.Thread(target=run)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    assert len(calls) == 1
    assert len(results) == 2
    success = sum(1 for r in results if r.get("status") == "success" and not r.get("duplicate"))
    duplicates = sum(1 for r in results if r.get("duplicate"))
    assert success + duplicates == 2


def test_07_concurrencia_reintento_failed_un_solo_handler(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    event = _mock_event("evt_conc_fail", "checkout.session.completed", _checkout_obj(cid))
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        with patch(
            "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
            side_effect=RuntimeError("temporal"),
        ):
            stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "sig")

    calls = []
    call_lock = threading.Lock()
    barrier = threading.Barrier(2)
    results = []

    def track_pago(*_args, **_kwargs):
        with call_lock:
            calls.append(1)
        return {"status": "success"}

    def run():
        barrier.wait()
        results.append(
            _procesar(sqlite_db, "evt_conc_fail", "checkout.session.completed", _checkout_obj(cid))
        )

    with patch(
        "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
        side_effect=track_pago,
    ):
        t1 = threading.Thread(target=run)
        t2 = threading.Thread(target=run)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    assert len(calls) == 1
    assert len(results) == 2
    success = sum(1 for r in results if r.get("status") == "success" and not r.get("duplicate"))
    duplicates = sum(1 for r in results if r.get("duplicate"))
    assert success + duplicates == 2


def test_08_repo_reclamar_failed_sqlite(sqlite_db):
    repo = StripeWebhookRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    assert repo.reclamar_evento(cur, "evt_repo_fail", "charge.dispute.created") == "claimed"
    conn.commit()
    repo.marcar_evento_fallido(cur, "evt_repo_fail", "err")
    conn.commit()
    assert repo.reclamar_evento(cur, "evt_repo_fail", "charge.dispute.created") == "claimed"
    conn.commit()
    row = cur.execute(
        "SELECT estado_procesamiento, resultado FROM stripe_webhook_events "
        "WHERE stripe_event_id='evt_repo_fail'"
    ).fetchone()
    conn.close()
    assert row[0] == "processing"
    assert row[1] == "processing"


def test_09_repo_completed_no_reclama_sqlite(sqlite_db):
    repo = StripeWebhookRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    repo.reclamar_evento(cur, "evt_repo_ok", "checkout.session.completed")
    repo.finalizar_evento(cur, "evt_repo_ok", "ok")
    conn.commit()
    assert repo.reclamar_evento(cur, "evt_repo_ok", "checkout.session.completed") == "duplicate_ok"
    conn.close()


def test_10_repo_reclamar_failed_postgres_sql():
    from unittest.mock import MagicMock

    db = MagicMock()
    db.backend = "postgres"
    cursor = MagicMock()
    executed: list[str] = []
    rowcounts = [0, 1]  # INSERT 0 rows, UPDATE 1 row

    def record_execute(sql, params=()):
        executed.append(str(sql))
        cursor.rowcount = rowcounts.pop(0) if rowcounts else 0
        return cursor

    cursor.execute = record_execute
    cursor.fetchone = MagicMock(return_value=None)

    repo = StripeWebhookRepo()
    assert repo.reclamar_evento(cursor, "evt_pg", "charge.dispute.created") == "claimed"
    update_sql = next(s for s in executed if "UPDATE stripe_webhook_events" in s)
    assert "estado_procesamiento = 'failed'" in update_sql
    assert "estado_procesamiento = 'processing'" in update_sql
