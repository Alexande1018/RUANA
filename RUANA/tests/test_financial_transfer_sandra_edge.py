"""Caso Sandra / encargo #72: cobro retenido, Connect ausente o de prueba, Transfer atascado."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.services import financial_transfer_service as transfer_svc
from core.services import pago_service
from core.services import stripe_webhook_service


DEV_CONNECT = "acct_1U4nS02OQ4mXrlA3"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RUANA_TRANSFER_STRIPE_STUCK_MINUTES", "5")
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
    return db_module.DBManager(str(tmp_path / "ruana_sandra.db"))


def _seed(db, *, prof_account=DEV_CONNECT, charges=1, importe=1.0):
    conn = db._connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)",
        ("64156", "Sandra", "sandra@t.com"),
    )
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("50009", "Andrea", "andrea@t.com", prof_account, charges),
    )
    apoyo = round(importe * 0.12, 2)
    neto = round(importe - apoyo, 2)
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, apoyo_ruana, comision, stripe_payment_intent_id,
            fecha_confirmacion_trabajo
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, ?, 'stripe', 'cobro_confirmado',
                  'TRANSFERENCIA_PENDIENTE', 'PENDIENTE', ?, ?, ?, 'pi_sandra', CURRENT_TIMESTAMP)
        """,
        ("64156", "50009", "encargo", importe, neto, apoyo, apoyo),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def _insert_ft(db, cid, *, estado, dest=DEV_CONNECT, tid=None, actualizado=None):
    conn = db._connect()
    conn.execute(
        """
        INSERT INTO financial_transfers (
            contacto_id, idempotency_key, amount_cents, currency,
            destination_account_id, professional_codigo, estado, stripe_transfer_id
        ) VALUES (?, ?, 88, 'eur', ?, '50009', ?, ?)
        """,
        (cid, f"transfer-contacto-{cid}", dest, estado, tid),
    )
    if actualizado:
        conn.execute(
            "UPDATE financial_transfers SET actualizado_en = ? WHERE contacto_id = ?",
            (actualizado, cid),
        )
    conn.commit()
    conn.close()


def _mock_event(event_id, event_type, obj):
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data.object = obj
    return event


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_sandra_connect_ausente_retiene_cobro(mock_transfer, sqlite_db):
    cid = _seed(sqlite_db, prof_account="", charges=0)
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "64156")
    assert res["status"] == "error"
    assert res.get("bloqueo") == "connect"
    assert "retenido" in (res.get("message") or "").lower()
    mock_transfer.assert_not_called()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_sandra_destino_dev_se_corrige_al_reintentar(mock_transfer, sqlite_db):
    cid = _seed(sqlite_db, prof_account="acct_live_andrea", charges=1)
    _insert_ft(sqlite_db, cid, estado="RECLAMADA", dest=DEV_CONNECT)
    mock_transfer.return_value = {"id": "tr_live_ok"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "64156")
    assert res["status"] == "success"
    assert res.get("stripe_transfer_id") == "tr_live_ok"
    assert mock_transfer.call_args.kwargs["destination_account_id"] == "acct_live_andrea"


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_sandra_stripe_en_proceso_stale_se_reclama(mock_transfer, sqlite_db):
    cid = _seed(sqlite_db, prof_account="acct_live_andrea", charges=1)
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    _insert_ft(sqlite_db, cid, estado="STRIPE_EN_PROCESO", dest=DEV_CONNECT, actualizado=old)
    mock_transfer.return_value = {"id": "tr_reclaim"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "64156")
    assert res["status"] == "success"
    assert res.get("stripe_transfer_id") == "tr_reclaim"
    mock_transfer.assert_called_once()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_sandra_stripe_en_proceso_fresco_no_duplica(mock_transfer, sqlite_db):
    cid = _seed(sqlite_db, prof_account="acct_live_andrea", charges=1)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    _insert_ft(sqlite_db, cid, estado="STRIPE_EN_PROCESO", dest="acct_live_andrea", actualizado=now)
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "64156")
    assert res["status"] == "success"
    assert res.get("estado") == "transferencia_en_proceso"
    mock_transfer.assert_not_called()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_sandra_account_updated_reintenta_transfer_pendiente(mock_transfer, sqlite_db):
    cid = _seed(sqlite_db, prof_account="acct_live_andrea", charges=0)
    _insert_ft(sqlite_db, cid, estado="RECLAMADA", dest=DEV_CONNECT)
    mock_transfer.return_value = {"id": "tr_onboard"}
    event = _mock_event(
        "evt_acct_sandra",
        "account.updated",
        {
            "id": "acct_live_andrea",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
        },
    )
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        wh = stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "sig")
    assert wh.get("status") == "success"
    assert mock_transfer.call_count == 1
    assert mock_transfer.call_args.kwargs["destination_account_id"] == "acct_live_andrea"
    conn = sqlite_db._connect()
    tid = conn.execute(
        "SELECT stripe_transfer_id FROM financial_transfers WHERE contacto_id=?",
        (cid,),
    ).fetchone()[0]
    charges = conn.execute(
        "SELECT stripe_charges_enabled FROM aliados WHERE codigo='50009'"
    ).fetchone()[0]
    conn.close()
    assert int(charges) == 1
    assert tid == "tr_onboard"


def test_sandra_reintentar_sin_account_id_noop(sqlite_db):
    res = transfer_svc.reintentar_transferencias_pendientes_profesional(sqlite_db, "")
    assert res["status"] == "skipped"
    assert res["reintentos"] == []
