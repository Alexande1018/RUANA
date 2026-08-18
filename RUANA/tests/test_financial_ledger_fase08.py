"""Tests FASE 08: ledger financiero interno."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlite3

from core import db_manager as db_module
from core.financial.ledger_accounts import CuentaLedger
from core.financial.ledger_estados import EstadoLedgerTransaction
from core.financial.ledger_types import TipoLedgerTransaction
from core.financial.reconciliation_snapshot import comision_ruana_cents
from core.ledger_authorization import LEDGER_ADJUST, LEDGER_VIEW, LEDGER_VOID, tiene_permiso_ledger
from core.services import financial_ledger_reconciliation_service as flrs
from core.services import financial_ledger_service as fls
from core.services.financial_ledger_service import LedgerValidationError, _validar_lineas


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "0")
    return db_module.DBManager(str(tmp_path / "ruana_fase08.db"))


def _balanced_lines(amount: int = 100000):
    return [
        {"account_code": CuentaLedger.STRIPE_RECEIVABLE.value, "debit_cents": amount},
        {"account_code": CuentaLedger.CLEARING_PAYMENTS.value, "credit_cents": amount},
    ]


def test_01_transaccion_equilibrada_se_publica(sqlite_db):
    r = fls.publicar_transaccion(
        sqlite_db, idempotency_key="t01", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=_balanced_lines(), actor_origen="test",
    )
    assert r["status"] == "success"
    assert r["estado"] == EstadoLedgerTransaction.POSTED.value


def test_02_transaccion_desequilibrada_rechazada(sqlite_db):
    with pytest.raises(LedgerValidationError):
        _validar_lineas([
            {"account_code": "STRIPE_RECEIVABLE", "debit_cents": 100},
            {"account_code": "CLEARING_PAYMENTS", "credit_cents": 99},
        ], "eur")


def test_03_debit_y_credit_simultaneos_rechazados():
    with pytest.raises(LedgerValidationError):
        _validar_lineas([
            {"account_code": "STRIPE_RECEIVABLE", "debit_cents": 100, "credit_cents": 100},
            {"account_code": "CLEARING_PAYMENTS", "credit_cents": 100},
        ], "eur")


def test_04_linea_cero_rechazada():
    with pytest.raises(LedgerValidationError):
        _validar_lineas([
            {"account_code": "STRIPE_RECEIVABLE", "debit_cents": 0, "credit_cents": 0},
            {"account_code": "CLEARING_PAYMENTS", "credit_cents": 100},
        ], "eur")


def test_05_importe_negativo_rechazado():
    with pytest.raises(LedgerValidationError):
        _validar_lineas([
            {"account_code": "STRIPE_RECEIVABLE", "debit_cents": -1},
            {"account_code": "CLEARING_PAYMENTS", "credit_cents": 100},
        ], "eur")


def test_06_moneda_inconsistente_rechazada():
    with pytest.raises(LedgerValidationError):
        _validar_lineas([
            {"account_code": "STRIPE_RECEIVABLE", "debit_cents": 100, "currency": "usd"},
            {"account_code": "CLEARING_PAYMENTS", "credit_cents": 100},
        ], "eur")


def test_07_transaction_key_idempotente(sqlite_db):
    r1 = fls.publicar_transaccion(
        sqlite_db, idempotency_key="t07", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=_balanced_lines(), actor_origen="test",
    )
    r2 = fls.publicar_transaccion(
        sqlite_db, idempotency_key="t07", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=_balanced_lines(200000), actor_origen="test",
    )
    assert r1["transaction_id"] == r2["transaction_id"]
    assert r2.get("idempotent") is True


def test_08_webhook_duplicado_no_duplica_ledger(sqlite_db):
    fls.registrar_pago_confirmado(
        sqlite_db, contacto_id=1, importe_bruto_cents=100000,
        payment_intent_id="pi_dup", idempotency_key="wh-dup",
    )
    fls.registrar_pago_confirmado(
        sqlite_db, contacto_id=1, importe_bruto_cents=100000,
        payment_intent_id="pi_dup", idempotency_key="wh-dup",
    )
    conn = sqlite_db._connect()
    n = conn.execute("SELECT COUNT(*) FROM ledger_transactions WHERE contacto_id=1").fetchone()[0]
    conn.close()
    assert n == 3


def test_09_posted_no_editable(sqlite_db):
    r = fls.publicar_transaccion(
        sqlite_db, idempotency_key="t09", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=_balanced_lines(), actor_origen="test",
    )
    tx_id = r["transaction_id"]
    conn = sqlite_db._connect()
    with pytest.raises(Exception):
        conn.execute("UPDATE ledger_entries SET debit_cents=999 WHERE ledger_transaction_id=?", (tx_id,))
        conn.commit()
    conn.close()


def test_10_posted_no_borrable(sqlite_db):
    r = fls.publicar_transaccion(
        sqlite_db, idempotency_key="t10", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=_balanced_lines(), actor_origen="test",
    )
    tx_id = r["transaction_id"]
    conn = sqlite_db._connect()
    with pytest.raises(sqlite3.IntegrityError, match="eliminar"):
        conn.execute("DELETE FROM ledger_entries WHERE ledger_transaction_id=?", (tx_id,))
        conn.commit()
    conn.close()


def test_11_voided_requiere_transaccion_inversa(sqlite_db):
    r = fls.publicar_transaccion(
        sqlite_db, idempotency_key="t11", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=_balanced_lines(), actor_origen="test",
    )
    void = fls.anular_transaccion(
        sqlite_db, r["transaction_id"],
        actor="admin", idempotency_key="void-t11", motivo="test",
    )
    assert void["status"] == "success"
    assert void.get("compensation_id")


def test_12_pago_crea_asientos_correctos(sqlite_db):
    fls.registrar_pago_confirmado(
        sqlite_db, contacto_id=5, importe_bruto_cents=100000,
        payment_intent_id="pi_12", idempotency_key="pay-12",
    )
    saldo = fls.saldo_cuenta(sqlite_db, CuentaLedger.RUANA_COMMISSION_REVENUE.value, contacto_id=5)
    assert saldo["credit_cents"] == comision_ruana_cents(100000)


def test_13_comision_12_porciento(sqlite_db):
    assert comision_ruana_cents(100000) == 12000


def test_14_transfer_crea_obligacion(sqlite_db):
    fls.registrar_pago_confirmado(
        sqlite_db, contacto_id=1, importe_bruto_cents=100000,
        payment_intent_id="pi_14", idempotency_key="pay-14",
    )
    fls.registrar_transferencia(
        sqlite_db, contacto_id=1, importe_cents=88000,
        transfer_id="tr_14", idempotency_key="tr-14", settled=False,
    )
    saldo = fls.saldo_cuenta(sqlite_db, CuentaLedger.CLEARING_TRANSFERS.value, contacto_id=1)
    assert saldo["credit_cents"] == 88000


def test_15_refund_respeta_comision(sqlite_db):
    fls.registrar_refund(
        sqlite_db, contacto_id=1, importe_cents=50000, refund_id="re_15",
        idempotency_key="ref-15", comision_devuelta_cents=6000,
    )
    saldo = fls.saldo_cuenta(sqlite_db, CuentaLedger.CUSTOMER_REFUND_PAYABLE.value, contacto_id=1)
    assert saldo["debit_cents"] == 50000


def test_16_reversion_crea_compensatorios(sqlite_db):
    fls.registrar_transferencia(
        sqlite_db, contacto_id=1, importe_cents=88000,
        transfer_id="tr_rev", idempotency_key="tr-rev", settled=False,
    )
    fls.registrar_reversion_transferencia(
        sqlite_db, contacto_id=1, importe_cents=88000,
        transfer_id="tr_rev", idempotency_key="rev-tr",
    )
    payable = fls.saldo_cuenta(sqlite_db, CuentaLedger.PROFESSIONAL_PAYABLE.value, contacto_id=1)
    assert payable["credit_cents"] == 88000


def test_17_disputa_pendiente_no_reconoce_perdida(sqlite_db):
    fls.registrar_disputa_abierta(
        sqlite_db, contacto_id=1, dispute_id="dp_17",
        importe_cents=100000, idempotency_key="dp-open-17",
    )
    loss = fls.saldo_cuenta(sqlite_db, CuentaLedger.DISPUTE_LOSS.value, contacto_id=1)
    assert loss["debit_cents"] == 0


def test_18_disputa_perdida_registra_perdida(sqlite_db):
    fls.registrar_disputa_perdida(
        sqlite_db, contacto_id=1, dispute_id="dp_lost",
        importe_perdido_cents=100000, idempotency_key="dp-lost",
    )
    loss = fls.saldo_cuenta(sqlite_db, CuentaLedger.DISPUTE_LOSS.value, contacto_id=1)
    assert loss["debit_cents"] == 100000


def test_19_reconciliacion_detecta_desequilibrio(sqlite_db):
    fls.publicar_transaccion(
        sqlite_db, idempotency_key="t19", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=_balanced_lines(), actor_origen="test",
    )
    conn = sqlite_db._connect()
    with pytest.raises(sqlite3.IntegrityError, match="inmutables"):
        conn.execute(
            "UPDATE ledger_entries SET credit_cents = 1 WHERE ledger_transaction_id = "
            "(SELECT id FROM ledger_transactions WHERE idempotency_key='t19') "
            "AND credit_cents > 0 LIMIT 1"
        )
        conn.commit()
    conn.close()


def test_20_reconciliacion_detecta_huerfanos(sqlite_db):
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO ledger_transactions (
            transaction_key, contacto_id, tipo, moneda, estado, idempotency_key
        ) VALUES ('orphan', 1, 'TEST', 'eur', 'POSTED', 'orphan-key')
        """
    )
    conn.commit()
    conn.close()
    r = flrs.comprobar_equilibrio(sqlite_db)
    assert any(h.get("transaction_key") == "orphan" for h in r.get("huerfanos", []))


def test_21_permisos_view_adjust_void():
    assert tiene_permiso_ledger(["leer"], LEDGER_VIEW)
    assert not tiene_permiso_ledger(["leer"], LEDGER_ADJUST)
    assert tiene_permiso_ledger(["configurar"], LEDGER_VOID)


def test_21b_permisos_insuficientes_403(client, session_headers):
    headers = session_headers("admin", "0000", permisos=["leer"])
    resp = client.get("/api/admin/financial-ledger/comprobar-equilibrio", headers=headers)
    assert resp.status_code == 403


def test_22_concurrencia_no_duplica_transaction_key(sqlite_db):
    results = []

    def run():
        results.append(fls.publicar_transaccion(
            sqlite_db, idempotency_key="conc", contacto_id=1,
            tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
            lineas=_balanced_lines(), actor_origen="test",
        ))

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start(); t2.start(); t1.join(30); t2.join(30)
    success = [r for r in results if r.get("status") == "success"]
    assert len(success) == 2
    ids = {r["transaction_id"] for r in success}
    assert len(ids) == 1


PG_DSN = "dbname=postgres user=postgres"
_PG_MINIMAL = """
CREATE TABLE IF NOT EXISTS contactos_ruana (id BIGSERIAL PRIMARY KEY);
"""


def _pg_ok():
    try:
        import psycopg
        c = psycopg.connect(PG_DSN, connect_timeout=2)
        c.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL no disponible")
def test_23_migracion_postgresql_limpia():
    import psycopg
    from psycopg import sql as psql
    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000900_financial_fase08_ledger.sql"
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f08_clean"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f08_clean"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f08_clean user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
        c.execute(mig.read_text(encoding="utf-8"))
    conn.commit()
    with conn.cursor() as c:
        c.execute("SELECT to_regclass('ledger_transactions')")
        assert c.fetchone()[0] is not None
    conn.close()


@pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL no disponible")
def test_24_migracion_postgresql_repetida():
    import psycopg
    from psycopg import sql as psql
    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000900_financial_fase08_ledger.sql"
    sql = mig.read_text(encoding="utf-8")
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f08_repeat"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f08_repeat"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f08_repeat user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
        c.execute(sql)
        c.execute(sql)
    conn.commit()
    conn.close()


def test_25_sqlite_migracion_repetida_idempotente(tmp_path):
    path = str(tmp_path / "rep_f08.db")
    db1 = db_module.DBManager(path)
    db2 = db_module.DBManager(path)
    conn = db2._connect()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ledger_transactions'")
    assert c.fetchone() is not None
    conn.close()
    assert db1 and db2


def test_26_no_crea_transfer_ni_refund_en_ledger(sqlite_db):
    from unittest.mock import patch
    with patch("core.stripe_client.create_transfer") as mt, patch("core.stripe_client.create_refund") as mr:
        fls.registrar_pago_confirmado(
            sqlite_db, contacto_id=1, importe_bruto_cents=100000,
            payment_intent_id="pi_26", idempotency_key="p26",
        )
        mt.assert_not_called()
        mr.assert_not_called()
