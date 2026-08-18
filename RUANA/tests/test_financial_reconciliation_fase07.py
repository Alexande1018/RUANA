"""Tests FASE 07: reconciliación financiera avanzada RUANA ↔ Stripe."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import db_manager as db_module
from core.financial.discrepancia import TipoDiscrepancia
from core.financial.estados import EstadoFinanciero
from core.financial.reconciliation_estados import EstadoReconciliacionAvanzada
from core.reconciliation_authorization import (
    RECON_EXECUTE,
    RECON_RESOLVE,
    RECON_VIEW,
    tiene_permiso_recon,
)
from core.services import financial_conflict_service as fcs
from core.services import financial_reconciliation_advanced_service as fras
from core.services import financial_reconciliation_service as reconciliation
from core.financial.conflict_estados import TipoConflicto
from core.financial.reconciliation_snapshot import build_ruana_snapshot, merge_stripe_into_snapshot


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
    return db_module.DBManager(str(tmp_path / "ruana_fase07.db"))


def _seed(
    db,
    importe=500.0,
    estado_financiero="PAGO_CONFIRMADO",
    pi="pi_f07",
    charge="ch_f07",
    transfer="tr_f07",
    account="acct_test",
):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "S", "s@t.com"))
    c.execute(
        "INSERT OR IGNORE INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "P", "p@t.com", account, 1),
    )
    apoyo = round(importe * 0.12, 2)
    neto = round(importe - apoyo, 2)
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, apoyo_ruana, comision,
            stripe_payment_intent_id, stripe_charge_id, stripe_transfer_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, ?, 'stripe', 'cobro_confirmado', ?,
                  'RETENIDO', ?, ?, ?, ?, ?, ?)
        """,
        ("SOL", "PRO", "Srv", importe, estado_financiero, neto, apoyo, apoyo, pi, charge, transfer),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid, int(round(importe * 100))


def _contacto_dict(db, cid):
    conn = db._connect()
    conn.row_factory = __import__("sqlite3").Row
    row = conn.execute(
        """
        SELECT cr.*, a.stripe_account_id
        FROM contactos_ruana cr
        LEFT JOIN aliados a ON a.codigo = cr.profesional_codigo
        WHERE cr.id = ?
        """,
        (cid,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def _fetcher_ok(contacto, **overrides):
    """Mock fetcher con cadena Stripe coincidente."""
    bruto = int(round(float(contacto.get("importe_acordado") or 0) * 100))
    neto = int(round(float(contacto.get("importe_neto_profesional") or 0) * 100))
    pi = str(contacto.get("stripe_payment_intent_id") or "")
    charge = str(contacto.get("stripe_charge_id") or "")
    transfer = str(contacto.get("stripe_transfer_id") or "")
    account = str(contacto.get("stripe_account_id") or "acct_test")

    def ok(data):
        return {"status": "ok", "data": data, "error_code": "", "http_status": 200}

    def pending(code="server_error"):
        return {"status": "pending", "data": None, "error_code": code, "http_status": 503}

    def missing():
        return {"status": "missing", "data": None, "error_code": "missing", "http_status": 404}

    fetcher = {
        "payment_intent": lambda *_a, **_k: ok({
            "id": pi, "amount": bruto, "currency": "eur", "status": "succeeded",
            "latest_charge": charge,
        }),
        "charge": lambda *_a, **_k: ok({
            "id": charge, "amount": bruto, "currency": "eur",
            "balance_transaction": "txn_bt",
        }),
        "balance_transaction": lambda *_a, **_k: ok({
            "id": "txn_bt", "fee": 150, "net": bruto - 150,
        }),
        "transfer": lambda *_a, **_k: ok({
            "id": transfer, "amount": neto, "destination": account,
        }),
        "account": lambda *_a, **_k: ok({"id": account}),
        "refunds": lambda *_a, **_k: ok({"data": []}),
    }
    fetcher.update(overrides)
    return fetcher


def test_01_payment_intent_completo_coincidente(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=_fetcher_ok(contacto),
        idempotency_key="t01",
    )
    assert r["status"] == "success"
    assert r["estado"] in (
        EstadoReconciliacionAvanzada.MATCHED.value,
        EstadoReconciliacionAvanzada.MATCHED_WITH_WARNINGS.value,
    )


def test_02_charge_ausente_stripe(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["charge"] = lambda *_a, **_k: {
        "status": "missing", "data": None, "error_code": "missing", "http_status": 404,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t02",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value
    conn = sqlite_db._connect()
    tipos = [row[0] for row in conn.execute(
        "SELECT tipo_discrepancia FROM financial_reconciliation WHERE contacto_id=? AND estado_reconciliacion='open'", (cid,),
    ).fetchall()]
    conn.close()
    assert TipoDiscrepancia.CHARGE_MISSING_STRIPE.value in tipos


def test_03_charge_ausente_ruana(sqlite_db):
    cid, _ = _seed(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET stripe_charge_id=NULL WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    contacto = _contacto_dict(sqlite_db, cid)
    bruto = int(round(float(contacto["importe_acordado"]) * 100))
    neto = int(round(float(contacto["importe_neto_profesional"]) * 100))
    fetcher = _fetcher_ok(contacto)
    fetcher["payment_intent"] = lambda *_a, **_k: {
        "status": "ok",
        "data": {
            "id": contacto["stripe_payment_intent_id"], "amount": bruto, "currency": "eur",
            "status": "succeeded", "latest_charge": "ch_f07",
        },
        "error_code": "", "http_status": 200,
    }
    fetcher["charge"] = lambda *_a, **_k: {
        "status": "ok",
        "data": {"id": "ch_f07", "amount": bruto, "currency": "eur", "balance_transaction": "txn_bt"},
        "error_code": "", "http_status": 200,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t03",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value


def test_04_balance_transaction_ausente(sqlite_db):
    ruana = build_ruana_snapshot({"id": 1, "importe_acordado": 500, "stripe_charge_id": "ch_x"})
    ruana["identidad"]["balance_transaction_id"] = "txn_expected"
    stripe = merge_stripe_into_snapshot(
        build_ruana_snapshot({"id": 1, "importe_acordado": 500}),
        charge={"id": "ch_x", "amount": 50000, "currency": "eur", "balance_transaction": "txn_other"},
        balance_transaction={"id": "txn_other", "fee": 100, "net": 49900},
    )
    estado, discs, _ = fras.comparar_snapshots(ruana, stripe)
    assert TipoDiscrepancia.BALANCE_TRANSACTION_MISMATCH in discs
    assert estado == EstadoReconciliacionAvanzada.MISMATCH


def test_05_transfer_ausente(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["transfer"] = lambda *_a, **_k: {
        "status": "missing", "data": None, "error_code": "missing", "http_status": 404,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t05",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value


def test_06_destination_incorrecto(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    bruto = int(round(float(contacto["importe_acordado"]) * 100))
    neto = int(round(float(contacto["importe_neto_profesional"]) * 100))
    fetcher["transfer"] = lambda *_a, **_k: {
        "status": "ok", "data": {"id": contacto["stripe_transfer_id"], "amount": neto, "destination": "acct_wrong"},
        "error_code": "", "http_status": 200,
    }
    fetcher["account"] = lambda *_a, **_k: {
        "status": "ok", "data": {"id": "acct_wrong"}, "error_code": "", "http_status": 200,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t06",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value


def test_07_importe_incorrecto(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["payment_intent"] = lambda *_a, **_k: {
        "status": "ok",
        "data": {"id": contacto["stripe_payment_intent_id"], "amount": 99999, "currency": "eur", "status": "succeeded"},
        "error_code": "", "http_status": 200,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t07",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value


def test_08_moneda_incorrecta(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    bruto = int(round(float(contacto["importe_acordado"]) * 100))
    fetcher = _fetcher_ok(contacto)
    fetcher["payment_intent"] = lambda *_a, **_k: {
        "status": "ok",
        "data": {"id": contacto["stripe_payment_intent_id"], "amount": bruto, "currency": "usd", "status": "succeeded"},
        "error_code": "", "http_status": 200,
    }
    fetcher["charge"] = lambda *_a, **_k: {
        "status": "ok",
        "data": {"id": contacto["stripe_charge_id"], "amount": bruto, "currency": "usd", "balance_transaction": "txn_bt"},
        "error_code": "", "http_status": 200,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t08",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value


def test_09_fee_stripe_incorrecta(sqlite_db):
    ruana = build_ruana_snapshot({"id": 1, "importe_acordado": 500})
    ruana["importes_cents"]["fee_stripe"] = 200
    stripe = merge_stripe_into_snapshot(
        build_ruana_snapshot({"id": 1, "importe_acordado": 500}),
        balance_transaction={"id": "txn", "fee": 150, "net": 49850},
    )
    _, discs, _ = fras.comparar_snapshots(ruana, stripe)
    assert TipoDiscrepancia.FEE_MISMATCH in discs


def test_10_refunds_incompletos(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["refunds"] = lambda *_a, **_k: {
        "status": "ok",
        "data": {"data": [{"id": "re_1", "amount": 10000}]},
        "error_code": "", "http_status": 200,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t10",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value


def test_11_disputes_incompletas(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    bruto = int(round(float(contacto["importe_acordado"]) * 100))
    fetcher = _fetcher_ok(contacto)
    fetcher["charge"] = lambda *_a, **_k: {
        "status": "ok",
        "data": {
            "id": contacto["stripe_charge_id"], "amount": bruto, "currency": "eur",
            "balance_transaction": "txn_bt", "dispute": "dp_1",
        },
        "error_code": "", "http_status": 200,
    }
    fetcher["dispute"] = lambda *_a, **_k: {
        "status": "ok", "data": {"id": "dp_1", "amount": bruto, "status": "needs_response"},
        "error_code": "", "http_status": 200,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t11",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.MISMATCH.value


def test_12_conflicto_abierto_blocked(sqlite_db):
    cid, _ = _seed(sqlite_db)
    fcs.abrir_conflicto(
        sqlite_db, cid, tipo=TipoConflicto.IMPORTE_DISPUTADO, motivo="test",
        abierto_por="SOL", idempotency_key="cf-t12",
    )
    r = fras.reconciliar_contacto_avanzado(sqlite_db, cid, idempotency_key="t12")
    assert r["estado"] == EstadoReconciliacionAvanzada.BLOCKED.value


def test_13_disputa_abierta_blocked(sqlite_db):
    cid, _ = _seed(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO financial_disputes (
            contacto_id, stripe_dispute_id, amount_cents, estado_interno, bloqueo_financiero
        ) VALUES (?, 'dp_blk', 50000, 'ABIERTO', 1)
        """,
        (cid,),
    )
    conn.commit()
    conn.close()
    r = fras.reconciliar_contacto_avanzado(sqlite_db, cid, idempotency_key="t13")
    assert r["estado"] == EstadoReconciliacionAvanzada.BLOCKED.value


def test_14_transferido_conserva_historial(sqlite_db):
    cid, _ = _seed(sqlite_db, estado_financiero=EstadoFinanciero.TRANSFERIDO.value)
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO financial_disputes (
            contacto_id, stripe_dispute_id, amount_cents, estado_interno,
            bloqueo_financiero, estado_financiero_historico
        ) VALUES (?, 'dp_hist', 50000, 'ABIERTO', 1, 'TRANSFERIDO')
        """,
        (cid,),
    )
    conn.commit()
    estado_antes = conn.execute(
        "SELECT estado_financiero FROM contactos_ruana WHERE id=?", (cid,),
    ).fetchone()[0]
    conn.close()
    assert estado_antes == EstadoFinanciero.TRANSFERIDO.value
    r = fras.reconciliar_contacto_avanzado(sqlite_db, cid, idempotency_key="t14")
    assert r["estado"] == EstadoReconciliacionAvanzada.BLOCKED.value
    conn = sqlite_db._connect()
    estado_despues = conn.execute(
        "SELECT estado_financiero FROM contactos_ruana WHERE id=?", (cid,),
    ).fetchone()[0]
    conn.close()
    assert estado_despues == EstadoFinanciero.TRANSFERIDO.value


def test_15_timeout_stripe_pending(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["payment_intent"] = lambda *_a, **_k: {
        "status": "pending", "data": None, "error_code": "server_error", "http_status": 504,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t15",
    )
    assert r["estado"] == EstadoReconciliacionAvanzada.PENDING.value


def test_16_rate_limit_pending(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["charge"] = lambda *_a, **_k: {
        "status": "pending", "data": None, "error_code": "rate_limit", "http_status": 429,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t16",
    )
    assert r["estado"] in (
        EstadoReconciliacionAvanzada.PENDING.value,
        EstadoReconciliacionAvanzada.MISMATCH.value,
    )


def test_17_error_5xx_pending_o_mismatch(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["transfer"] = lambda *_a, **_k: {
        "status": "pending", "data": None, "error_code": "server_error", "http_status": 500,
    }
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t17",
    )
    assert r["estado"] in (
        EstadoReconciliacionAvanzada.PENDING.value,
        EstadoReconciliacionAvanzada.MISMATCH.value,
    )


def test_18_ejecucion_repetida_idempotente(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    r1 = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t18",
    )
    r2 = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t18",
    )
    assert r1["estado"] in (
        EstadoReconciliacionAvanzada.MATCHED.value,
        EstadoReconciliacionAvanzada.MATCHED_WITH_WARNINGS.value,
    )
    assert r2.get("idempotent") is True


def test_19_discrepancia_no_duplicada(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fetcher = _fetcher_ok(contacto)
    fetcher["transfer"] = lambda *_a, **_k: {
        "status": "missing", "data": None, "error_code": "missing", "http_status": 404,
    }
    fras.reconciliar_contacto_avanzado(sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t19a")
    fras.reconciliar_contacto_avanzado(sqlite_db, cid, stripe_fetcher=fetcher, idempotency_key="t19b")
    conn = sqlite_db._connect()
    n = conn.execute(
        """
        SELECT COUNT(*) FROM financial_reconciliation
        WHERE contacto_id=? AND tipo_discrepancia=? AND estado_reconciliacion='open'
        """,
        (cid, TipoDiscrepancia.TRANSFER_MISSING_STRIPE.value),
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_20_lote_continua_tras_fallo(sqlite_db):
    c1, _ = _seed(sqlite_db, pi="pi_l1", charge="ch_l1", transfer="tr_l1")
    c2, _ = _seed(sqlite_db, pi="pi_l2", charge="ch_l2", transfer="tr_l2")
    original = fras.reconciliar_contacto_avanzado

    def patched(db, contacto_id, **kwargs):
        if contacto_id == c1:
            raise RuntimeError("fallo aislado")
        c = _contacto_dict(db, contacto_id)
        kwargs["stripe_fetcher"] = _fetcher_ok(c)
        return original(db, contacto_id, **kwargs)

    with patch.object(fras, "reconciliar_contacto_avanzado", side_effect=patched):
        r = fras.ejecutar_lote(sqlite_db, limit=10)
    assert r["status"] == "success"
    assert r["metricas"]["total"] >= 2
    assert r["metricas"]["error"] >= 1


def test_21_limite_lote_respetado(sqlite_db):
    for i in range(5):
        _seed(sqlite_db, pi=f"pi_b{i}", charge=f"ch_b{i}", transfer=f"tr_b{i}")
    contacto_cache = {}

    def patched(db, contacto_id, **kwargs):
        if contacto_id not in contacto_cache:
            contacto_cache[contacto_id] = _contacto_dict(db, contacto_id)
        kwargs["stripe_fetcher"] = _fetcher_ok(contacto_cache[contacto_id])
        return fras.reconciliar_contacto_avanzado.__wrapped__(db, contacto_id, **kwargs) if hasattr(
            fras.reconciliar_contacto_avanzado, "__wrapped__"
        ) else fras.reconciliar_contacto_avanzado(db, contacto_id, **kwargs)

    with patch.object(fras, "reconciliar_contacto_avanzado") as mock_recon:
        mock_recon.side_effect = lambda db, cid, **kw: {
            "status": "success", "estado": EstadoReconciliacionAvanzada.MATCHED.value,
        }
        r = fras.ejecutar_lote(sqlite_db, limit=2)
    assert r["metricas"]["total"] == 2


@patch("core.stripe_client.create_transfer")
@patch("core.stripe_client.create_refund")
def test_22_reconciliacion_no_crea_transfer(mock_refund, mock_transfer, sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=_fetcher_ok(contacto), idempotency_key="t22",
    )
    mock_transfer.assert_not_called()
    mock_refund.assert_not_called()


def test_23_reconciliacion_no_crea_refund(sqlite_db):
    """Alias explícito: reconciliación no invoca Refund.create."""
    with patch("core.stripe_client.create_refund") as mock_cr:
        cid, _ = _seed(sqlite_db)
        contacto = _contacto_dict(sqlite_db, cid)
        fras.reconciliar_contacto_avanzado(
            sqlite_db, cid, stripe_fetcher=_fetcher_ok(contacto), idempotency_key="t23",
        )
        mock_cr.assert_not_called()


def test_24_permisos_view_execute_resolve():
    assert tiene_permiso_recon(["leer"], RECON_VIEW)
    assert not tiene_permiso_recon(["leer"], RECON_EXECUTE)
    assert tiene_permiso_recon(["configurar"], RECON_RESOLVE)


def test_24b_permisos_insuficientes_403(client, session_headers):
    headers = session_headers("admin", "0000", permisos=["leer"])
    resp = client.post(
        "/api/admin/financial-reconciliation/contacto/1",
        json={"idempotency_key": "p24"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert not tiene_permiso_recon(["leer"], RECON_EXECUTE)


PG_DSN = "dbname=postgres user=postgres"
_PG_MINIMAL = """
CREATE TABLE IF NOT EXISTS aliados (id BIGSERIAL PRIMARY KEY, codigo TEXT UNIQUE, nombre TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS contactos_ruana (id BIGSERIAL PRIMARY KEY, solicitante_codigo TEXT, profesional_codigo TEXT, servicio TEXT, estado TEXT);
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
def test_25_migracion_postgresql_limpia():
    import psycopg
    from psycopg import sql as psql

    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000800_financial_fase07_reconciliation.sql"
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f07_clean"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f07_clean"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f07_clean user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
    conn.commit()
    with conn.cursor() as c:
        c.execute(mig.read_text(encoding="utf-8"))
    conn.commit()
    with conn.cursor() as c:
        c.execute("SELECT to_regclass('financial_reconciliation_executions')")
        assert c.fetchone()[0] is not None
    conn.close()


@pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL no disponible")
def test_26_migracion_postgresql_repetida():
    import psycopg
    from psycopg import sql as psql

    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000800_financial_fase07_reconciliation.sql"
    sql = mig.read_text(encoding="utf-8")
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f07_repeat"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f07_repeat"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f07_repeat user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
    conn.commit()
    with conn.cursor() as c:
        c.execute(sql)
        c.execute(sql)
    conn.commit()
    conn.close()


def test_27_sqlite_migracion_repetida_idempotente(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "0")
    path = str(tmp_path / "rep_f07.db")
    db1 = db_module.DBManager(path)
    db2 = db_module.DBManager(path)
    conn = db2._connect()
    c = conn.cursor()
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='financial_reconciliation_executions'",
    )
    assert c.fetchone() is not None
    conn.close()
    assert db1 and db2


def test_28_resolver_ejecucion_admin(sqlite_db):
    cid, _ = _seed(sqlite_db)
    contacto = _contacto_dict(sqlite_db, cid)
    r = fras.reconciliar_contacto_avanzado(
        sqlite_db, cid, stripe_fetcher=_fetcher_ok(contacto), idempotency_key="t28",
    )
    exec_id = r["execution_id"]
    res = fras.resolver_ejecucion(
        sqlite_db, exec_id, actor="admin", motivo="revisado manualmente",
    )
    assert res["status"] == "success"
    assert res["estado"] == EstadoReconciliacionAvanzada.RESOLVED.value
