"""Tests Stripe Connect: cobro plataforma + transfer tras confirmación del contratante."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.services import pago_service


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
    return db_module.DBManager(str(tmp_path / "ruana.db"))


def _seed_stripe_contacto(db, importe=500.0):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "Sol", "sol@test.com"))
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "Pro", "pro@test.com", "acct_test123", 1),
    )
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado
        ) VALUES (?, ?, ?, 'acuerdo_alcanzado', 1, ?)
        """,
        ("SOL", "PRO", "Servicio", importe),
    )
    contacto_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return contacto_id


def test_activar_pago_stripe_congela_importe(sqlite_db):
    contacto_id = _seed_stripe_contacto(sqlite_db, 500.0)
    res = pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 500.0)
    assert res["status"] == "success"
    assert res["estado"] == "pendiente_de_pago"
    assert res["estado_pago"] == "esperando_cobro_cliente"
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT precio_congelado, importe_acordado, modo_pago, importe_neto_profesional FROM contactos_ruana WHERE id=?",
        (contacto_id,),
    ).fetchone()
    conn.close()
    assert row[0] == 1
    assert row[1] == 500.0
    assert row[2] == "stripe"
    assert row[3] == 440.0  # 88% de 500 con apoyo 12%


@patch("core.services.pago_service.stripe_client.create_checkout_session")
def test_crear_checkout_usa_importe_bd_no_body(mock_checkout, sqlite_db):
    contacto_id = _seed_stripe_contacto(sqlite_db, 500.0)
    pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 500.0)
    mock_checkout.return_value = {"id": "cs_test", "url": "https://checkout.stripe.test/cs"}
    res = pago_service.crear_checkout_stripe(sqlite_db, contacto_id, "SOL")
    assert res["status"] == "success"
    mock_checkout.assert_called_once()
    assert mock_checkout.call_args.kwargs["amount_cents"] == 50000
    assert mock_checkout.call_args.kwargs["contacto_id"] == contacto_id


def test_crear_checkout_rechaza_profesional(sqlite_db):
    contacto_id = _seed_stripe_contacto(sqlite_db, 500.0)
    pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 500.0)
    res = pago_service.crear_checkout_stripe(sqlite_db, contacto_id, "PRO")
    assert res["status"] == "error"
    assert "contratante" in res["message"].lower()


def test_procesar_pago_confirmado_webhook(sqlite_db):
    contacto_id = _seed_stripe_contacto(sqlite_db, 500.0)
    pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 500.0)
    res = pago_service._procesar_pago_confirmado(sqlite_db, contacto_id, "pi_test_123")
    assert res["status"] == "success"
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado, estado_pago, stripe_payment_intent_id FROM contactos_ruana WHERE id=?",
        (contacto_id,),
    ).fetchone()
    ingreso = conn.execute(
        "SELECT COUNT(*) FROM ingresos_ruana WHERE contacto_id=?", (contacto_id,)
    ).fetchone()[0]
    conn.close()
    assert row[0] == "trabajo_en_progreso"
    assert row[1] == "cobro_confirmado"
    assert row[2] == "pi_test_123"
    assert ingreso == 1


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_confirmar_trabajo_solo_contratante_transfiere(mock_transfer, sqlite_db):
    contacto_id = _seed_stripe_contacto(sqlite_db, 500.0)
    pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 500.0)
    pago_service._procesar_pago_confirmado(sqlite_db, contacto_id, "pi_test_456")
    mock_transfer.return_value = {"id": "tr_test_789"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, contacto_id, "SOL")
    assert res["status"] == "success"
    assert res["estado_pago"] == "cobro_confirmado"
    assert res["estado_financiero"] == "TRANSFERENCIA_ENVIADA"
    mock_transfer.assert_called_once()
    assert mock_transfer.call_args.kwargs["amount_cents"] == 44000
    assert mock_transfer.call_args.kwargs["destination_account_id"] == "acct_test123"


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_confirmar_trabajo_rechaza_profesional(mock_transfer, sqlite_db):
    contacto_id = _seed_stripe_contacto(sqlite_db, 500.0)
    pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 500.0)
    pago_service._procesar_pago_confirmado(sqlite_db, contacto_id, "pi_test_456")
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, contacto_id, "PRO")
    assert res["status"] == "error"
    assert "contrat" in res["message"].lower()
    mock_transfer.assert_not_called()


def test_webhook_idempotente(sqlite_db):
    contacto_id = _seed_stripe_contacto(sqlite_db, 500.0)
    pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 500.0)
    event = MagicMock()
    event.id = "evt_test_idem"
    event.type = "checkout.session.completed"
    event.data.object = {
        "payment_status": "paid",
        "payment_intent": "pi_idem",
        "metadata": {"contacto_id": str(contacto_id)},
    }
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        r1 = pago_service.procesar_webhook_stripe(sqlite_db, b"{}", "sig")
        r2 = pago_service.procesar_webhook_stripe(sqlite_db, b"{}", "sig")
    assert r1["status"] == "success"
    assert r2.get("duplicate") is True


def test_flujo_estados_cobro_retencion_reparto(sqlite_db):
    """Punta a punta: pendiente → cobro confirmado (retenido) → transferencia 88 %."""
    from core.financial.money import calcular_desglose_stripe_cents, importe_bd_a_cents

    contacto_id = _seed_stripe_contacto(sqlite_db, 199.99)
    res = pago_service.activar_pago_stripe_tras_acuerdo(sqlite_db, contacto_id, "SOL", 199.99)
    assert res["status"] == "success"
    assert res["estado"] == "pendiente_de_pago"
    assert res["estado_pago"] == "esperando_cobro_cliente"

    cobro = pago_service._procesar_pago_confirmado(sqlite_db, contacto_id, "pi_flow_19999")
    assert cobro["status"] == "success"
    conn = sqlite_db._connect()
    row = conn.execute(
        """
        SELECT estado, estado_pago, stripe_payment_intent_id, stripe_transfer_id,
               importe_neto_profesional, apoyo_ruana, importe_acordado
        FROM contactos_ruana WHERE id=?
        """,
        (contacto_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "trabajo_en_progreso"
    assert row[1] == "cobro_confirmado"
    assert row[2] == "pi_flow_19999"
    assert not row[3]
    bruto_c, apoyo_c, neto_c, _ = calcular_desglose_stripe_cents(importe_bd_a_cents(199.99))
    assert importe_bd_a_cents(row[4]) == neto_c
    assert importe_bd_a_cents(row[5]) == apoyo_c
    assert neto_c + apoyo_c == bruto_c
    assert neto_c == (bruto_c * 88) // 100 or neto_c == bruto_c - ((bruto_c * 12) // 100)
