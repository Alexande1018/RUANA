"""Tests céntimos enteros y reparto 88/12 (FASE 14)."""

from decimal import Decimal

import pytest

from core.financial.money import (
    COMISION_RUANA_PCT,
    calcular_desglose_stripe_cents,
    cents_a_importe_bd,
    comision_ruana_cents,
    importe_bd_a_cents,
    neto_profesional_cents,
)


def test_importe_bd_a_cents_sin_float_aritmetico():
    assert importe_bd_a_cents(500) == 50000
    assert importe_bd_a_cents(500.0) == 50000
    assert importe_bd_a_cents("499.99") == 49999
    assert importe_bd_a_cents(Decimal("12.34")) == 1234
    assert importe_bd_a_cents(None) == 0


def test_reparto_88_12_en_centimos():
    bruto = 50000
    apoyo = comision_ruana_cents(bruto)
    neto = neto_profesional_cents(bruto)
    assert apoyo == 6000  # 12 % de 500 €
    assert neto == 44000  # 88 %
    assert apoyo + neto == bruto


def test_calcular_desglose_stripe_cents():
    bruto_c, apoyo_c, neto_c, pct = calcular_desglose_stripe_cents(10000)
    assert bruto_c == 10000
    assert apoyo_c == 1200
    assert neto_c == 8800
    assert pct == COMISION_RUANA_PCT / 100


def test_reparto_importes_impares_sin_perdida_de_centimos():
    for bruto in (101, 333, 1999, 1):
        apoyo = comision_ruana_cents(bruto)
        neto = neto_profesional_cents(bruto)
        assert apoyo + neto == bruto
        assert apoyo == (bruto * 12) // 100


def test_1999_centimos_no_usa_float():
    assert importe_bd_a_cents("19.99") == 1999
    assert importe_bd_a_cents(19.99) == 1999
    assert cents_a_importe_bd(1999) == 19.99
    assert comision_ruana_cents(1999) == 239
    assert neto_profesional_cents(1999) == 1760


def test_activar_pago_usa_centimos(sqlite_db_fixture):
    """Integración: activar pago Stripe congela neto 88 % en BD."""
    from core.services import pago_service

    db = sqlite_db_fixture
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)",
        ("SOL14", "Sol", "sol14@test.com"),
    )
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO14", "Pro", "pro14@test.com", "acct_14", 1),
    )
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado
        ) VALUES (?, ?, ?, 'acuerdo_alcanzado', 1, ?)
        """,
        ("SOL14", "PRO14", "Servicio F14", 500.0),
    )
    contacto_id = cursor.lastrowid
    conn.commit()
    conn.close()

    res = pago_service.activar_pago_stripe_tras_acuerdo(db, contacto_id, "SOL14", 500.0)
    assert res["status"] == "success"
    conn = db._connect()
    row = conn.execute(
        "SELECT importe_neto_profesional, apoyo_ruana FROM contactos_ruana WHERE id=?",
        (contacto_id,),
    ).fetchone()
    conn.close()
    assert row[0] == 440.0
    assert row[1] == 60.0


@pytest.fixture
def sqlite_db_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    from core import db_manager as db_module
    return db_module.DBManager(str(tmp_path / "money_f14.db"))
