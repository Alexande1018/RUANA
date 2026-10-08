"""Tests céntimos enteros y reparto 95/5 (FASE 14)."""

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


def test_reparto_95_5_en_centimos():
    bruto = 50000
    apoyo = comision_ruana_cents(bruto)
    neto = neto_profesional_cents(bruto)
    assert apoyo == 2500  # 5 % de 500 €
    assert neto == 47500  # 95 %
    assert apoyo + neto == bruto


def test_calcular_desglose_stripe_cents():
    bruto_c, apoyo_c, neto_c, pct = calcular_desglose_stripe_cents(10000)
    assert bruto_c == 10000
    assert apoyo_c == 500
    assert neto_c == 9500
    assert pct == COMISION_RUANA_PCT / 100


def test_reparto_importes_impares_sin_perdida_de_centimos():
    for bruto in (101, 333, 1999, 1):
        apoyo = comision_ruana_cents(bruto)
        neto = neto_profesional_cents(bruto)
        assert apoyo + neto == bruto
        assert apoyo == (bruto * COMISION_RUANA_PCT) // 100


def test_1999_centimos_no_usa_float():
    assert importe_bd_a_cents("19.99") == 1999
    assert importe_bd_a_cents(19.99) == 1999
    assert cents_a_importe_bd(1999) == 19.99
    assert comision_ruana_cents(1999) == 99
    assert neto_profesional_cents(1999) == 1900


def test_activar_pago_usa_centimos(sqlite_db_fixture):
    """Integración: activar pago Stripe congela neto 95 % en BD."""
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
    assert row[0] == 475.0
    assert row[1] == 25.0


def test_encargo_congelado_al_12_no_se_reescribe(sqlite_db_fixture):
    """Un encargo ya cerrado al 12 % conserva apoyo, neto y porcentaje."""
    from core.financial.money import desglose_congelado_cents
    from core.services import pago_service

    db = sqlite_db_fixture
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)",
        ("SOL12", "Sol", "sol12@test.com"),
    )
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO12", "Pro", "pro12@test.com", "acct_12", 1),
    )
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            modo_pago, precio_congelado, importe_acordado, importe_final,
            apoyo_ruana, comision, comision_porcentaje, importe_neto_profesional,
            estado_pago
        ) VALUES (?, ?, ?, 'pendiente_de_pago', 0, 'stripe', 1, 500, 500, 60, 60, 0.12, 440,
                  'esperando_cobro_cliente')
        """,
        ("SOL12", "PRO12", "Encargo histórico"),
    )
    contacto_id = cursor.lastrowid
    conn.commit()
    conn.close()

    res = pago_service._procesar_pago_confirmado(db, contacto_id, "pi_hist_12")
    assert res["status"] == "success"
    conn = db._connect()
    row = conn.execute(
        """
        SELECT apoyo_ruana, comision, comision_porcentaje, importe_neto_profesional, importe_final
        FROM contactos_ruana WHERE id=?
        """,
        (contacto_id,),
    ).fetchone()
    ingreso = conn.execute(
        "SELECT apoyo_ruana_2pct FROM ingresos_ruana WHERE contacto_id=?",
        (contacto_id,),
    ).fetchone()
    conn.close()
    assert row[0] == 60.0
    assert row[1] == 60.0
    assert row[2] == 0.12
    assert row[3] == 440.0
    assert row[4] == 500.0
    assert ingreso[0] == 60.0
    bruto, apoyo, neto, pct = desglose_congelado_cents(
        {"apoyo_ruana": 60, "importe_neto_profesional": 440, "importe_final": 500},
        50000,
    )
    assert (bruto, apoyo, neto) == (50000, 6000, 44000)
    assert pct == 0.12


def test_disputa_de_encargo_con_apoyo_12_mantiene_la_tasa(sqlite_db_fixture):
    """Resolver una disputa no baja al 5 % un encargo que ya tenía el 12 % guardado."""
    from core.services import pago_service

    db = sqlite_db_fixture
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("SOLD", "Sol"))
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("PROD", "Pro"))
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado,
            importe_final, apoyo_ruana, comision, comision_porcentaje, estado_pago
        ) VALUES (?, ?, ?, 'importe_en_disputa', 100, 12, 12, 0.12, 'pendiente_pago')
        """,
        ("SOLD", "PROD", "Disputa histórica"),
    )
    contacto_id = cursor.lastrowid
    conn.commit()
    conn.close()

    res = pago_service.resolver_conflicto_pago(db, contacto_id, 80.0, admin_codigo="admin")
    assert res["status"] == "success"
    assert res["apoyo_ruana"] == 9.6
    conn = db._connect()
    row = conn.execute(
        "SELECT importe_final, apoyo_ruana, comision_porcentaje FROM contactos_ruana WHERE id=?",
        (contacto_id,),
    ).fetchone()
    conn.close()
    assert row[0] == 80.0
    assert row[1] == 9.6
    assert abs(row[2] - 0.12) < 0.0001


@pytest.fixture
def sqlite_db_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    from core import db_manager as db_module
    return db_module.DBManager(str(tmp_path / "money_f14.db"))
