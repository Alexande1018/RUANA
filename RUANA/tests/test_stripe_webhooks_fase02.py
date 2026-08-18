"""Tests FASE 02: webhooks Stripe robustos + reconciliación."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.financial.discrepancia import TipoDiscrepancia
from core.financial.estados import EstadoFinanciero
from core.services import financial_reconciliation_service as reconciliation
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
    return db_module.DBManager(str(tmp_path / "ruana_fase02.db"))


def _mock_event(event_id, event_type, obj):
    event = MagicMock()
    event.id = event_id
    event.type = event_type
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


def _procesar(db, event_id, event_type, obj):
    event = _mock_event(event_id, event_type, obj)
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig_valid")


# 1. webhook válido
def test_01_webhook_valido(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    res = _procesar(
        sqlite_db, "evt_01", "checkout.session.completed",
        {"payment_status": "paid", "payment_intent": "pi_01", "metadata": {"contacto_id": str(cid)}, "id": "cs_01"},
    )
    assert res["status"] == "success"


# 2. firma inválida
def test_02_firma_invalida(sqlite_db):
    with patch("core.stripe_client.construct_webhook_event", side_effect=ValueError("bad sig")):
        res = stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "bad")
    assert res["status"] == "error"
    assert "firma" in res["message"].lower()


# 3. webhook duplicado
def test_03_webhook_duplicado(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    obj = {"payment_status": "paid", "payment_intent": "pi_dup", "metadata": {"contacto_id": str(cid)}, "id": "cs"}
    r1 = _procesar(sqlite_db, "evt_dup", "checkout.session.completed", obj)
    r2 = _procesar(sqlite_db, "evt_dup", "checkout.session.completed", obj)
    assert r1["status"] == "success"
    assert r2.get("duplicate") is True


# 4. concurrencia mismo event_id
def test_04_concurrencia_mismo_event_id(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    obj = {"payment_status": "paid", "payment_intent": "pi_conc", "metadata": {"contacto_id": str(cid)}, "id": "cs"}
    results = []
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        results.append(_procesar(sqlite_db, "evt_conc", "checkout.session.completed", obj))

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
    count = conn.execute(
        "SELECT COUNT(*) FROM ingresos_ruana WHERE contacto_id=?", (cid,)
    ).fetchone()[0]
    conn.close()
    assert count <= 1


# 5-7. payment events
def test_05_checkout_session_completed(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    _procesar(
        sqlite_db, "evt_05", "checkout.session.completed",
        {"payment_status": "paid", "payment_intent": "pi_05", "metadata": {"contacto_id": str(cid)}, "id": "cs_05"},
    )
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.ESPERANDO_CONFIRMACION


def test_06_payment_intent_succeeded(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    _procesar(
        sqlite_db, "evt_06", "payment_intent.succeeded",
        {"id": "pi_06", "metadata": {"contacto_id": str(cid), "tipo": "encargo_ruana"}},
    )
    conn = sqlite_db._connect()
    pi = conn.execute("SELECT stripe_payment_intent_id FROM contactos_ruana WHERE id=?", (cid,)).fetchone()[0]
    conn.close()
    assert pi == "pi_06"


def test_07_payment_intent_failed(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_PENDIENTE")
    _procesar(
        sqlite_db, "evt_07", "payment_intent.payment_failed",
        {"id": "pi_fail", "metadata": {"contacto_id": str(cid), "tipo": "encargo_ruana"}},
    )
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.PAGO_FALLIDO


# 8-11. transfer events
def test_08_transfer_created(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="LIBERACION_AUTORIZADA")
    _procesar(
        sqlite_db, "evt_08", "transfer.created",
        {"id": "tr_08", "metadata": {"contacto_id": str(cid)}},
    )
    conn = sqlite_db._connect()
    tr = conn.execute("SELECT stripe_transfer_id FROM contactos_ruana WHERE id=?", (cid,)).fetchone()[0]
    et = conn.execute("SELECT estado_transferencia FROM contactos_ruana WHERE id=?", (cid,)).fetchone()[0]
    conn.close()
    assert tr == "tr_08"
    assert et == "ENVIADA"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA


def test_09_transfer_paid(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="TRANSFERENCIA_ENVIADA")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_transfer_id='tr_09' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    _procesar(sqlite_db, "evt_09", "transfer.paid", {"id": "tr_09", "metadata": {"contacto_id": str(cid)}})
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO


def test_10_transfer_failed(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="TRANSFERENCIA_ENVIADA")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_transfer_id='tr_fail' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    _procesar(sqlite_db, "evt_10", "transfer.failed", {"id": "tr_fail", "metadata": {"contacto_id": str(cid)}})
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_FALLIDA


def test_11_transfer_paid_duplicado(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_transfer_id='tr_dup', estado_transferencia='COMPLETADA' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    r1 = _procesar(sqlite_db, "evt_11a", "transfer.paid", {"id": "tr_dup", "metadata": {"contacto_id": str(cid)}})
    r2 = _procesar(sqlite_db, "evt_11b", "transfer.paid", {"id": "tr_dup", "metadata": {"contacto_id": str(cid)}})
    assert r1["resultado"] == "idempotent"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO


# 12. transfer.paid antes de transfer.created
def test_12_transfer_paid_antes_created(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="LIBERACION_AUTORIZADA")
    _procesar(sqlite_db, "evt_12a", "transfer.paid", {"id": "tr_12", "metadata": {"contacto_id": str(cid)}})
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    r = _procesar(sqlite_db, "evt_12b", "transfer.created", {"id": "tr_12", "metadata": {"contacto_id": str(cid)}})
    assert r["status"] == "success"


# 13. transfer.failed después de transfer.paid
def test_13_transfer_failed_despues_paid(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_transfer_id='tr_13' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    _procesar(sqlite_db, "evt_13", "transfer.failed", {"id": "tr_13", "metadata": {"contacto_id": str(cid)}})
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    conn = sqlite_db._connect()
    disc = conn.execute(
        "SELECT COUNT(*) FROM financial_reconciliation WHERE contacto_id=? AND tipo_discrepancia=?",
        (cid, TipoDiscrepancia.STATUS_MISMATCH.value),
    ).fetchone()[0]
    conn.close()
    assert disc >= 1


# 14-15. refunds
def test_14_charge_refunded_total(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_payment_intent_id='pi_ref' WHERE id=?", (cid,)
    )
    conn.commit()
    conn.close()
    _procesar(
        sqlite_db, "evt_14", "charge.refunded",
        {"id": "ch_14", "payment_intent": "pi_ref", "amount_refunded": 50000, "currency": "eur"},
    )
    conn = sqlite_db._connect()
    total = conn.execute("SELECT SUM(amount) FROM stripe_refunds WHERE contacto_id=?", (cid,)).fetchone()[0]
    conn.close()
    assert total == 500.0


def test_15_charge_refunded_parcial(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_payment_intent_id='pi_parc' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    _procesar(
        sqlite_db, "evt_15", "charge.refunded",
        {"id": "ch_15", "payment_intent": "pi_parc", "amount_refunded": 10000, "currency": "eur"},
    )
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT es_total FROM stripe_refunds WHERE contacto_id=?", (cid,)
    ).fetchone()
    conn.close()
    assert row[0] == 0


# 16-17. disputes
def test_16_charge_dispute_created(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_payment_intent_id='pi_disp' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    _procesar(
        sqlite_db, "evt_16", "charge.dispute.created",
        {
            "id": "dp_16", "charge": "ch_d", "payment_intent": "pi_disp",
            "amount": 50000, "currency": "eur", "reason": "fraudulent", "status": "needs_response",
            "evidence_details": {"due_by": 1234567890},
        },
    )
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.DISPUTA_STRIPE


def test_17_disputa_bloquea_liberacion(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="DISPUTA_STRIPE")
    res = fts.intentar_autorizar_liberacion(sqlite_db, cid, "SOL")
    assert res["status"] == "error"


# 18-21. reconciliación detección
def test_18_reconciliacion_importe_distinto(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_payment_intent_id='pi_rec' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    res = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"payment_intent": {"id": "pi_rec", "amount": 60000, "currency": "eur", "status": "succeeded"}},
    )
    assert res["discrepancias_nuevas"] >= 1


def test_19_reconciliacion_moneda_distinta(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_payment_intent_id='pi_usd', estado_pago='cobro_confirmado' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    res = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"payment_intent": {"id": "pi_usd", "amount": 50000, "currency": "usd", "status": "succeeded"}},
    )
    assert any(d["tipo"] == TipoDiscrepancia.CURRENCY_MISMATCH.value for d in res.get("discrepancias", []))


def test_20_reconciliacion_transfer_inexistente(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_transfer_id='tr_x', estado_pago='transferido' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    res = reconciliation.reconciliar_contacto(sqlite_db, cid, stripe_snapshot={"transfer": {}})
    assert res["discrepancias_nuevas"] >= 1


def test_21_reconciliacion_payment_intent_inexistente(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_payment_intent_id='pi_missing', estado_pago='cobro_confirmado' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    res = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"payment_intent": {"id": "pi_other", "status": "succeeded", "amount": 50000}},
    )
    tipos = {d["tipo"] for d in res.get("discrepancias", [])}
    assert TipoDiscrepancia.PAYMENT_INTENT_MISMATCH.value in tipos or TipoDiscrepancia.AMOUNT_MISMATCH.value in tipos


# 22-25. reconciliación operativa
def test_22_reconciliacion_sin_discrepancias(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="ESPERANDO_CONFIRMACION")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_payment_intent_id='pi_ok', estado_pago='cobro_confirmado' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    res = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"payment_intent": {"id": "pi_ok", "amount": 50000, "currency": "eur", "status": "succeeded"}},
    )
    assert res["discrepancias_nuevas"] == 0


def test_23_reconciliacion_estado_diferente(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_transfer_id='tr_st' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    res = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"transfer": {"id": "tr_st", "amount": 44000, "status": "failed"}},
    )
    assert res["discrepancias_nuevas"] >= 1


def test_24_reconciliacion_repetida_sin_duplicados(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="TRANSFERIDO")
    snap = {"transfer": {"id": "tr_x", "amount": 44000, "status": "failed"}}
    r1 = reconciliation.reconciliar_contacto(sqlite_db, cid, stripe_snapshot=snap)
    r2 = reconciliation.reconciliar_contacto(sqlite_db, cid, stripe_snapshot=snap)
    assert r1["discrepancias_nuevas"] >= 1
    assert r2["discrepancias_nuevas"] == 0


# 26-28. errores y protección estado
def test_26_fallo_procesamiento_no_marca_completado(sqlite_db):
    cid = _seed_stripe(sqlite_db)
    event = _mock_event(
        "evt_fail", "checkout.session.completed",
        {"payment_status": "paid", "payment_intent": "pi_fail", "metadata": {"contacto_id": str(cid)}, "id": "cs"},
    )
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        with patch(
            "core.services.stripe_webhook_service.pago_service._procesar_pago_confirmado",
            side_effect=RuntimeError("temporal"),
        ):
            res = stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "sig")
    assert res["status"] == "error"
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_procesamiento FROM stripe_webhook_events WHERE stripe_event_id='evt_fail'"
    ).fetchone()
    conn.close()
    assert row[0] == "failed"


def test_27_evento_antiguo_no_sobrescribe_estado_posterior(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_payment_intent_id='pi_locked' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    _procesar(
        sqlite_db, "evt_old_fail", "payment_intent.payment_failed",
        {"id": "pi_locked", "metadata": {"contacto_id": str(cid), "tipo": "encargo_ruana"}},
    )
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.PAGO_CONFIRMADO


def test_28_payment_failed_no_afecta_confirmado(sqlite_db):
    cid = _seed_stripe(sqlite_db, estado_financiero="ESPERANDO_CONFIRMACION")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_payment_intent_id='pi_conf', estado_pago='cobro_confirmado' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    _procesar(
        sqlite_db, "evt_28", "payment_intent.payment_failed",
        {"id": "pi_conf", "metadata": {"contacto_id": str(cid), "tipo": "encargo_ruana"}},
    )
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.ESPERANDO_CONFIRMACION
