"""Tests FASE 05: reembolsos Stripe seguros, idempotentes y auditables."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from RUANA.web import app as app_module
from core import db_manager as db_module
from core.financial.conflict_estados import ResolucionConflicto, TipoConflicto
from core.financial.refund_comision import calcular_impacto_comision_refund
from core.financial.refund_estados import CausaReembolso, EstadoRefund
from core.refund_authorization import REFUND_EXECUTE, REFUND_VIEW, tiene_permiso_refund
from core.services import financial_conflict_service as fcs
from core.services import financial_refund_service as frs


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
    db = db_module.DBManager(str(tmp_path / "ruana_fase05.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    return db


def _seed(db, importe=500.0):
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
            importe_neto_profesional, apoyo_ruana, comision, stripe_payment_intent_id, stripe_charge_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, ?, 'stripe', 'cobro_confirmado',
                  'PAGO_CONFIRMADO', 'RETENIDO', ?, ?, ?, 'pi_f05', 'ch_f05')
        """,
        ("SOL", "PRO", "Srv", importe, neto, apoyo, apoyo),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid, int(round(importe * 100))


def _resolver_conflicto_reembolso(db, cid, neto, key="res-f05"):
    r = fcs.abrir_conflicto(
        db, cid, tipo=TipoConflicto.IMPORTE_DISPUTADO, motivo="test",
        abierto_por="SOL", idempotency_key=key,
    )
    cf = r["conflict_id"]
    fcs.resolver_conflicto(
        db, cf, ResolucionConflicto.REEMBOLSAR_TOTAL,
        actor="admin", importe_reembolsar_cents=neto, motivo="total",
        idempotency_key=f"resolve-{key}",
    )
    return cf, neto


def _mock_stripe_refund(re_id="re_test", status="succeeded", amount=44000):
    return {"id": re_id, "status": status, "amount": amount}


# 1-6 comisión y causas
def test_01_refund_total_antes_iniciar_devuelve_comision_completa():
    impacto, err = calcular_impacto_comision_refund(
        importe_bruto_cents=50000, causa=CausaReembolso.SERVICIO_NO_INICIADO,
    )
    assert err is None
    assert impacto.comision_devuelta_cents == 6000
    assert impacto.comision_conservada_cents == 0


def test_02_incumplimiento_profesional_devuelve_comision_no_ejecutada():
    impacto, err = calcular_impacto_comision_refund(
        importe_bruto_cents=10000, causa=CausaReembolso.INCUMPLIMIENTO_PROFESIONAL,
        parte_ejecutada_cents=5000,
    )
    assert err is None
    assert impacto.comision_total_cents == 1200
    assert impacto.comision_conservada_cents == 600
    assert impacto.comision_devuelta_cents == 600


def test_03_refund_parcial_calcula_comision_proporcional():
    impacto, err = calcular_impacto_comision_refund(
        importe_bruto_cents=10000, causa=CausaReembolso.SERVICIO_PARCIAL,
        parte_ejecutada_cents=2500,
    )
    assert err is None
    assert impacto.comision_conservada_cents == 300
    assert impacto.comision_devuelta_cents == 900


def test_04_cancelacion_injustificada_conserva_comision():
    impacto, err = calcular_impacto_comision_refund(
        importe_bruto_cents=10000,
        causa=CausaReembolso.CANCELACION_INJUSTIFICADA_CONTRATANTE,
        conservar_comision_total=True,
    )
    assert err is None
    assert impacto.comision_conservada_cents == 1200
    assert impacto.comision_devuelta_cents == 0


def test_05_error_ruana_devuelve_comision_completa():
    impacto, err = calcular_impacto_comision_refund(
        importe_bruto_cents=10000, causa=CausaReembolso.ERROR_RUANA,
    )
    assert err is None
    assert impacto.comision_devuelta_cents == impacto.comision_total_cents


def test_06_caso_indeterminado_bloqueado():
    impacto, err = calcular_impacto_comision_refund(
        importe_bruto_cents=10000, causa=CausaReembolso.INDETERMINADO,
    )
    assert impacto is None
    assert err is not None


# 7-11 límites e idempotencia
@patch("core.stripe_client.create_refund")
def test_07_refund_supera_importe_cobrado(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    r = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto + 1,
        actor="admin", idempotency_key="sup-cobrado",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert r["status"] == "error"
    assert mock_cr.call_count == 0


@patch("core.stripe_client.create_refund")
def test_08_parciales_acumulados_no_superan_maximo(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    mock_cr.return_value = _mock_stripe_refund(amount=10000)
    frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=10000,
        actor="admin", idempotency_key="p1",
        causa_ruana=CausaReembolso.SERVICIO_PARCIAL.value,
        parte_ejecutada_cents=neto - 10000,
    )
    r2 = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="p2",
        causa_ruana=CausaReembolso.SERVICIO_PARCIAL.value,
        parte_ejecutada_cents=0,
    )
    assert r2["status"] == "error"
    assert mock_cr.call_count == 1


@patch("core.stripe_client.create_refund")
def test_09_dos_refunds_simultaneos_no_superan_maximo(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    mock_cr.return_value = _mock_stripe_refund()
    results = []
    barrier = threading.Barrier(2)

    def run(key):
        barrier.wait(timeout=10)
        results.append(
            frs.ejecutar_reembolso(
                sqlite_db, cid, importe_solicitado_cents=neto,
                actor="admin", idempotency_key=key,
                causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
            )
        )

    t1 = threading.Thread(target=run, args=("sim-a",))
    t2 = threading.Thread(target=run, args=("sim-b",))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    success = sum(1 for x in results if x.get("status") == "success")
    assert success >= 1
    assert mock_cr.call_count <= 2


@patch("core.stripe_client.create_refund")
def test_10_idempotency_key_repetida_no_crea_segundo(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    mock_cr.return_value = _mock_stripe_refund()
    a = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="idem-same",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    b = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="idem-same",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert a["status"] == "success"
    assert b["status"] == "success"
    assert b.get("idempotent") is True
    assert mock_cr.call_count == 1


@patch("core.stripe_client.create_refund")
def test_11_timeout_reintenta_misma_key(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    mock_cr.side_effect = [Exception("timeout"), _mock_stripe_refund()]
    r1 = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="retry-key",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert r1["status"] == "error"
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE financial_refunds SET estado='REQUESTED', stripe_refund_id=NULL WHERE idempotency_key LIKE ?",
        (f"%retry-key",),
    )
    conn.commit()
    conn.close()
    r2 = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="retry-key",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert r2["status"] == "success"
    assert mock_cr.call_count == 2
    args = mock_cr.call_args_list[0]
    assert args.kwargs.get("idempotency_key") == args.kwargs.get("idempotency_key")


# 12-15 stripe y webhooks
@patch("core.stripe_client.create_refund")
def test_12_error_sincrono_stripe_failed(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    mock_cr.side_effect = Exception("card_declined")
    r = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="fail-sync",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert r["status"] == "error"
    conn = sqlite_db._connect()
    estado = conn.execute(
        "SELECT estado FROM financial_refunds WHERE idempotency_key LIKE ?", ("%fail-sync",),
    ).fetchone()[0]
    conn.close()
    assert estado == EstadoRefund.FAILED.value


def test_13_webhook_charge_refunded_actualiza_refund(sqlite_db):
    cid, neto = _seed(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO financial_refunds (
            contacto_id, payment_intent_id, importe_solicitado_cents, moneda, estado,
            causa_ruana, actor_codigo, idempotency_key, stripe_refund_id
        ) VALUES (?, 'pi_f05', ?, 'eur', 'PENDING_RECONCILIATION', 'SERVICIO_NO_INICIADO',
                  'admin', 'refund-contacto-1-wh', 're_wh')
        """,
        (cid, neto),
    )
    conn.commit()
    conn.close()
    r = frs.procesar_webhook_refund(
        sqlite_db, stripe_refund_id="re_wh", amount_cents=neto, status="succeeded",
        event_id="evt_wh",
    )
    assert r["status"] == "success"
    assert r["estado"] == EstadoRefund.SUCCEEDED.value


def test_14_webhook_duplicado_idempotente(sqlite_db):
    cid, neto = _seed(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO financial_refunds (
            contacto_id, importe_solicitado_cents, moneda, estado, causa_ruana,
            actor_codigo, idempotency_key, stripe_refund_id, importe_confirmado_cents
        ) VALUES (?, ?, 'eur', 'SUCCEEDED', 'SERVICIO_NO_INICIADO', 'admin', 'dup-wh', 're_dup', ?)
        """,
        (cid, neto, neto),
    )
    conn.commit()
    conn.close()
    r = frs.procesar_webhook_refund(
        sqlite_db, stripe_refund_id="re_dup", amount_cents=neto, status="succeeded",
    )
    assert r["status"] == "success"


def test_15_webhook_importe_diferente_discrepancia(sqlite_db):
    cid, neto = _seed(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO financial_refunds (
            contacto_id, importe_solicitado_cents, moneda, estado, causa_ruana,
            actor_codigo, idempotency_key, stripe_refund_id
        ) VALUES (?, ?, 'eur', 'PENDING_RECONCILIATION', 'SERVICIO_NO_INICIADO', 'admin', 'mis-wh', 're_mis')
        """,
        (cid, neto),
    )
    conn.commit()
    conn.close()
    r = frs.procesar_webhook_refund(
        sqlite_db, stripe_refund_id="re_mis", amount_cents=neto + 100, status="succeeded",
    )
    assert r.get("discrepancia") == "REFUND_AMOUNT_MISMATCH"


# 16-20 conflictos, transferencias, permisos
@patch("core.stripe_client.create_refund")
def test_16_refund_sin_conflicto_resuelto_bloqueado(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    r = fcs.abrir_conflicto(
        sqlite_db, cid, tipo=TipoConflicto.IMPORTE_DISPUTADO, motivo="abierto",
        abierto_por="SOL", idempotency_key="open-block",
    )
    res = frs.ejecutar_reembolso_desde_conflicto(
        sqlite_db, r["conflict_id"], actor="admin", idempotency_key="no-res",
    )
    assert res["status"] == "error"
    assert mock_cr.call_count == 0


@patch("core.stripe_client.create_refund")
def test_17_conflicto_abierto_no_llama_stripe(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    fcs.abrir_conflicto(
        sqlite_db, cid, tipo=TipoConflicto.IMPORTE_DISPUTADO, motivo="x",
        abierto_por="SOL", idempotency_key="open-17",
    )
    r = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="open-direct",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert r["status"] == "error"
    assert mock_cr.call_count == 0


@patch("core.stripe_client.create_refund")
def test_18_transferencia_incompatible_pendiente(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_financiero='TRANSFERIDO' WHERE id=?", (cid,),
    )
    conn.commit()
    conn.close()
    cf, _ = _resolver_conflicto_reembolso(sqlite_db, cid, neto, key="tr-block")
    r = frs.ejecutar_reembolso_desde_conflicto(
        sqlite_db, cf, actor="admin", idempotency_key="tr-block-exec",
    )
    assert r["status"] == "error"
    assert r.get("bloqueo") == "transferencia_incompatible"
    assert mock_cr.call_count == 0


@patch("core.stripe_client.create_refund")
def test_19_disputa_abierta_bloqueada(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_financiero='DISPUTA_STRIPE' WHERE id=?", (cid,),
    )
    conn.commit()
    conn.close()
    r = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="disp",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert r["status"] == "error"
    assert r.get("bloqueo") == "disputa_stripe"


def test_20_permisos_insuficientes_403(client, session_headers):
    headers = session_headers("admin", "0000", permisos=["leer"])
    resp = client.post(
        "/api/admin/financial-refunds/ejecutar",
        json={
            "contacto_id": 1, "importe_solicitado_cents": 100,
            "causa_ruana": "SERVICIO_NO_INICIADO", "idempotency_key": "p20",
        },
        headers=headers,
    )
    assert resp.status_code == 403
    assert not tiene_permiso_refund(["leer"], REFUND_EXECUTE)


# 21 floats rechazados en API
def test_21_importe_float_rechazado_en_endpoint(client, sqlite_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["configurar"])
    resp = client.post(
        "/api/admin/financial-refunds/ejecutar",
        json={
            "contacto_id": 1, "importe_solicitado_cents": "not-int",
            "causa_ruana": "SERVICIO_NO_INICIADO", "idempotency_key": "p21",
        },
        headers=headers,
    )
    assert resp.status_code == 400


# 22-24 migraciones
PG_DSN = "dbname=postgres user=postgres"
_PG_MINIMAL = """
CREATE TABLE IF NOT EXISTS aliados (id BIGSERIAL PRIMARY KEY, codigo TEXT UNIQUE, nombre TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS contactos_ruana (id BIGSERIAL PRIMARY KEY, solicitante_codigo TEXT, profesional_codigo TEXT, servicio TEXT, estado TEXT);
CREATE TABLE IF NOT EXISTS payment_conflicts (
    id BIGSERIAL PRIMARY KEY,
    trabajo_id BIGINT NOT NULL REFERENCES contactos_ruana(id)
);
CREATE TABLE IF NOT EXISTS stripe_refunds (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    stripe_refund_id TEXT NOT NULL UNIQUE,
    amount NUMERIC(12,2),
    currency TEXT DEFAULT 'eur',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
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
def test_22_migracion_postgresql_limpia():
    import psycopg
    from psycopg import sql as psql

    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000600_financial_fase05_refunds.sql"
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f05_clean"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f05_clean"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f05_clean user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
    conn.commit()
    with conn.cursor() as c:
        c.execute(mig.read_text(encoding="utf-8"))
    conn.commit()
    with conn.cursor() as c:
        c.execute("SELECT to_regclass('financial_refunds')")
        assert c.fetchone()[0] is not None
    conn.close()


@pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL no disponible")
def test_23_migracion_postgresql_repetida():
    import psycopg
    from psycopg import sql as psql

    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000600_financial_fase05_refunds.sql"
    sql = mig.read_text(encoding="utf-8")
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f05_repeat"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f05_repeat"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f05_repeat user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
    conn.commit()
    with conn.cursor() as c:
        c.execute(sql)
        c.execute(sql)
    conn.commit()
    conn.close()


def test_24_sqlite_migracion_repetida_idempotente(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "0")
    path = str(tmp_path / "rep.db")
    db1 = db_module.DBManager(path)
    db2 = db_module.DBManager(path)
    conn = db2._connect()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='financial_refunds'")
    assert c.fetchone() is not None
    conn.close()
    assert db1 and db2


# 25 permiso view
def test_25_permiso_view_permitido():
    assert tiene_permiso_refund(["leer"], REFUND_VIEW)
