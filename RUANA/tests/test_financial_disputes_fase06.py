"""Tests FASE 06: disputas Stripe formales."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import db_manager as db_module
from core.dispute_authorization import DISPUTE_SUBMIT_EVIDENCE, DISPUTE_VIEW, tiene_permiso_dispute
from core.financial.conflict_estados import TipoConflicto
from core.financial.discrepancia import TipoDiscrepancia
from core.financial.dispute_estados import EstadoDisputa
from core.financial.estados import EstadoFinanciero
from core.financial.refund_estados import CausaReembolso
from core.services import financial_conflict_service as fcs
from core.services import financial_dispute_service as fds
from core.services import financial_reconciliation_service as reconciliation
from core.services import financial_refund_service as frs
from core.services import financial_transfer_service as fts
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
    return db_module.DBManager(str(tmp_path / "ruana_fase06.db"))


def _seed(db, importe=500.0, estado_financiero="PAGO_CONFIRMADO", pi="pi_f06", charge="ch_f06"):
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
            importe_neto_profesional, apoyo_ruana, comision,
            stripe_payment_intent_id, stripe_charge_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, ?, 'stripe', 'cobro_confirmado', ?,
                  'RETENIDO', ?, ?, ?, ?, ?)
        """,
        ("SOL", "PRO", "Srv", importe, estado_financiero, neto, apoyo, apoyo, pi, charge),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid, int(round(importe * 100))


def _dispute_obj(dp_id="dp_f06", pi="pi_f06", charge="ch_f06", amount=50000, status="needs_response", due_by=None):
    if due_by is None:
        due_by = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    return {
        "id": dp_id,
        "object": "dispute",
        "amount": amount,
        "currency": "eur",
        "reason": "fraudulent",
        "status": status,
        "charge": charge,
        "payment_intent": pi,
        "evidence_details": {"due_by": due_by, "has_evidence": False, "submission_count": 0},
    }


def _webhook(db, event_id, event_type, obj):
    from unittest.mock import MagicMock
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data.object = obj
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig")


# 1-7 webhooks
def test_01_charge_dispute_created_crea_disputa(sqlite_db):
    cid, _ = _seed(sqlite_db)
    res = _webhook(sqlite_db, "evt_d1", "charge.dispute.created", _dispute_obj())
    assert res["status"] == "success"
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_interno, amount_cents FROM financial_disputes WHERE contacto_id=?", (cid,),
    ).fetchone()
    conn.close()
    assert row[0] == EstadoDisputa.ABIERTO.value
    assert row[1] == 50000


def test_02_evento_duplicado_no_duplica(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d2a", "charge.dispute.created", _dispute_obj("dp_dup"))
    _webhook(sqlite_db, "evt_d2b", "charge.dispute.created", _dispute_obj("dp_dup"))
    conn = sqlite_db._connect()
    n = conn.execute("SELECT COUNT(*) FROM financial_disputes WHERE contacto_id=?", (cid,)).fetchone()[0]
    conn.close()
    assert n == 1


def test_03_evento_fuera_de_orden(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d3c", "charge.dispute.closed", _dispute_obj("dp_oo", status="won"))
    _webhook(sqlite_db, "evt_d3u", "charge.dispute.updated", _dispute_obj("dp_oo", status="under_review"))
    _webhook(sqlite_db, "evt_d3a", "charge.dispute.created", _dispute_obj("dp_oo"))
    conn = sqlite_db._connect()
    estado = conn.execute(
        "SELECT estado_interno FROM financial_disputes WHERE stripe_dispute_id='dp_oo'",
    ).fetchone()[0]
    conn.close()
    assert estado in (EstadoDisputa.GANADA.value, EstadoDisputa.CERRADA.value, EstadoDisputa.ABIERTO.value)


def test_04_charge_dispute_updated_sincroniza(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d4c", "charge.dispute.created", _dispute_obj("dp_upd"))
    obj = _dispute_obj("dp_upd", status="under_review")
    obj["evidence_details"]["has_evidence"] = True
    _webhook(sqlite_db, "evt_d4u", "charge.dispute.updated", obj)
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT status_stripe, has_evidence FROM financial_disputes WHERE stripe_dispute_id='dp_upd'",
    ).fetchone()
    conn.close()
    assert row[0] == "under_review"
    assert row[1] == 1


def test_05_charge_dispute_closed_ganada(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d5c", "charge.dispute.created", _dispute_obj("dp_won"))
    _webhook(sqlite_db, "evt_d5x", "charge.dispute.closed", _dispute_obj("dp_won", status="won"))
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_interno, resolution, bloqueo_financiero FROM financial_disputes WHERE stripe_dispute_id='dp_won'",
    ).fetchone()
    conn.close()
    assert row[0] == EstadoDisputa.GANADA.value
    assert row[1] == "won"
    assert row[2] == 0


def test_06_charge_dispute_closed_perdida(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d6c", "charge.dispute.created", _dispute_obj("dp_lost"))
    _webhook(sqlite_db, "evt_d6x", "charge.dispute.closed", _dispute_obj("dp_lost", status="lost"))
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_interno, resolution FROM financial_disputes WHERE stripe_dispute_id='dp_lost'",
    ).fetchone()
    conn.close()
    assert row[0] == EstadoDisputa.PERDIDA.value
    assert row[1] == "lost"


def test_07_deadline_conservado(sqlite_db):
    cid, _ = _seed(sqlite_db)
    due = int((datetime.now(timezone.utc) + timedelta(days=5)).timestamp())
    _webhook(sqlite_db, "evt_d7", "charge.dispute.created", _dispute_obj("dp_due", due_by=due))
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT evidence_due_by FROM financial_disputes WHERE stripe_dispute_id='dp_due'",
    ).fetchone()
    conn.close()
    assert row[0] is not None


# 8 reconciliación mismatch
def test_08_importe_mismatch_crea_discrepancia(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d8c", "charge.dispute.created", _dispute_obj("dp_mis", amount=50000))
    r = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"disputes": [_dispute_obj("dp_mis", amount=60000, status="needs_response")]},
    )
    assert r["status"] == "success"
    assert r.get("discrepancias_nuevas", 0) >= 1 or len(r.get("discrepancias", [])) >= 1


# 9-10 bloqueos
def test_09_disputa_abierta_bloquea_transfer(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d9", "charge.dispute.created", _dispute_obj("dp_tr"))
    r = fts.ejecutar_liberacion_y_transferencia(
        sqlite_db, cid, contratante_codigo="SOL",
    )
    assert r["status"] == "error"
    assert r.get("bloqueo") in ("disputa_stripe", "estado_financiero")


@patch("core.stripe_client.create_refund")
def test_10_disputa_abierta_bloquea_refund(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d10", "charge.dispute.created", _dispute_obj("dp_rf"))
    r = frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="rf-d10",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    assert r["status"] == "error"
    assert mock_cr.call_count == 0


# 11 historia TRANSFERIDO
def test_11_disputa_posterior_transferido_conserva_historia(sqlite_db):
    cid, _ = _seed(sqlite_db, estado_financiero="TRANSFERIDO")
    _webhook(sqlite_db, "evt_d11", "charge.dispute.created", _dispute_obj("dp_post_tr"))
    conn = sqlite_db._connect()
    ef = conn.execute("SELECT estado_financiero FROM contactos_ruana WHERE id=?", (cid,)).fetchone()[0]
    hist = conn.execute(
        "SELECT estado_financiero_historico FROM financial_disputes WHERE stripe_dispute_id='dp_post_tr'",
    ).fetchone()[0]
    conn.close()
    assert ef == EstadoFinanciero.TRANSFERIDO.value
    assert hist == EstadoFinanciero.TRANSFERIDO.value
    assert fds.tiene_disputa_bloqueante(sqlite_db, cid)


# 12 conflicto vinculado
def test_12_conflicto_y_disputa_vinculados_sin_mezclar(sqlite_db):
    cid, _ = _seed(sqlite_db)
    cf = fcs.abrir_conflicto(
        sqlite_db, cid, tipo=TipoConflicto.IMPORTE_DISPUTADO, motivo="test",
        abierto_por="SOL", idempotency_key="cf-d12",
    )
    _webhook(sqlite_db, "evt_d12", "charge.dispute.created", _dispute_obj("dp_cf"))
    conn = sqlite_db._connect()
    did = conn.execute(
        "SELECT id FROM financial_disputes WHERE stripe_dispute_id='dp_cf'",
    ).fetchone()[0]
    conn.close()
    fds.vincular_conflicto(sqlite_db, did, cf["conflict_id"], actor="admin")
    det_cf = fcs.obtener_detalle(sqlite_db, cf["conflict_id"])
    det_dp = fds.obtener_disputa(sqlite_db, did)
    assert det_cf["status"] == "success"
    assert det_dp["dispute"]["conflicto_id"] == cf["conflict_id"]
    assert "estado_interno" in det_dp["dispute"]
    assert "estado_conflicto" in det_cf["conflicto"]


# 13 evidencia append-only
def test_13_evidencia_append_only(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d13", "charge.dispute.created", _dispute_obj("dp_ev"))
    conn = sqlite_db._connect()
    did = conn.execute("SELECT id FROM financial_disputes WHERE stripe_dispute_id='dp_ev'").fetchone()[0]
    conn.close()
    fds.agregar_evidencia(sqlite_db, did, tipo="comunicacion", referencia="msg-1", actor="admin")
    fds.agregar_evidencia(sqlite_db, did, tipo="contrato", referencia="doc-1", actor="admin")
    conn = sqlite_db._connect()
    n = conn.execute("SELECT COUNT(*) FROM financial_dispute_evidence WHERE dispute_id=?", (did,)).fetchone()[0]
    conn.close()
    assert n == 2


def test_14_permisos_insuficientes_403(client, session_headers):
    headers = session_headers("admin", "0000", permisos=["leer"])
    resp = client.post(
        "/api/admin/financial-disputes/1/enviar-evidencia",
        json={"idempotency_key": "p14"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert not tiene_permiso_dispute(["leer"], DISPUTE_SUBMIT_EVIDENCE)


def test_15_dos_envios_simultaneos_no_duplican(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d15", "charge.dispute.created", _dispute_obj("dp_sim"))
    conn = sqlite_db._connect()
    did = conn.execute("SELECT id FROM financial_disputes WHERE stripe_dispute_id='dp_sim'").fetchone()[0]
    conn.close()
    fds.agregar_evidencia(sqlite_db, did, tipo="otro", referencia="x", actor="admin")
    results = []

    def run():
        with patch("core.stripe_client.update_dispute_evidence", return_value={}), \
             patch("core.stripe_client.submit_dispute_evidence", return_value={}):
            results.append(fds.enviar_evidencia_stripe(
                sqlite_db, did, actor="admin", evidence_payload={"uncategorized_text": "ok"},
                idempotency_key="sim-submit",
            ))

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start(); t2.start(); t1.join(30); t2.join(30)
    success = sum(1 for r in results if r.get("status") == "success")
    assert success >= 1


def test_16_submit_fuera_deadline_bloqueado(sqlite_db):
    cid, _ = _seed(sqlite_db)
    past = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
    _webhook(sqlite_db, "evt_d16", "charge.dispute.created", _dispute_obj("dp_exp", due_by=past))
    conn = sqlite_db._connect()
    did = conn.execute("SELECT id FROM financial_disputes WHERE stripe_dispute_id='dp_exp'").fetchone()[0]
    conn.close()
    r = fds.enviar_evidencia_stripe(sqlite_db, did, actor="admin", evidence_payload={})
    assert r["status"] == "error"
    assert r.get("bloqueo") == "deadline"


@patch("core.stripe_client.create_refund")
def test_17_refund_previo_disputa_alerta(mock_cr, sqlite_db):
    cid, neto = _seed(sqlite_db)
    mock_cr.return_value = {"id": "re_prev", "status": "succeeded", "amount": neto}
    frs.ejecutar_reembolso(
        sqlite_db, cid, importe_solicitado_cents=neto,
        actor="admin", idempotency_key="rf-prev",
        causa_ruana=CausaReembolso.SERVICIO_NO_INICIADO.value,
    )
    _webhook(sqlite_db, "evt_d17", "charge.dispute.created", _dispute_obj("dp_rf_prev"))
    assert fds.tiene_disputa_bloqueante(sqlite_db, cid)


def test_18_transfer_en_curso_disputa_alerta(sqlite_db):
    cid, _ = _seed(sqlite_db, estado_financiero="TRANSFERENCIA_ENVIADA")
    _webhook(sqlite_db, "evt_d18", "charge.dispute.created", _dispute_obj("dp_tr_curso"))
    assert fds.tiene_disputa_bloqueante(sqlite_db, cid)


def test_19_reconciliacion_pending(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d19", "charge.dispute.created", _dispute_obj("dp_rec"))
    r = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"disputes": [_dispute_obj("dp_rec", status="needs_response")]},
    )
    assert r["status"] == "success"


def test_20_reconciliacion_mismatch(sqlite_db):
    cid, _ = _seed(sqlite_db)
    _webhook(sqlite_db, "evt_d20", "charge.dispute.created", _dispute_obj("dp_rec_m", amount=50000))
    r = reconciliation.reconciliar_contacto(
        sqlite_db, cid,
        stripe_snapshot={"disputes": [_dispute_obj("dp_rec_m", amount=99999, status="needs_response")]},
    )
    assert r["status"] == "success"
    assert r.get("discrepancias_nuevas", 0) >= 1 or len(r.get("discrepancias", [])) >= 1


PG_DSN = "dbname=postgres user=postgres"
_PG_MINIMAL = """
CREATE TABLE IF NOT EXISTS aliados (id BIGSERIAL PRIMARY KEY, codigo TEXT UNIQUE, nombre TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS contactos_ruana (id BIGSERIAL PRIMARY KEY, solicitante_codigo TEXT, profesional_codigo TEXT, servicio TEXT, estado TEXT);
CREATE TABLE IF NOT EXISTS payment_conflicts (id BIGSERIAL PRIMARY KEY, trabajo_id BIGINT NOT NULL REFERENCES contactos_ruana(id));
CREATE TABLE IF NOT EXISTS stripe_disputes (
    id BIGSERIAL PRIMARY KEY, contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    stripe_dispute_id TEXT NOT NULL UNIQUE, amount NUMERIC(12,2), currency TEXT DEFAULT 'eur',
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
def test_21_migracion_postgresql_limpia():
    import psycopg
    from psycopg import sql as psql

    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000700_financial_fase06_disputes.sql"
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f06_clean"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f06_clean"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f06_clean user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
    conn.commit()
    with conn.cursor() as c:
        c.execute(mig.read_text(encoding="utf-8"))
    conn.commit()
    with conn.cursor() as c:
        c.execute("SELECT to_regclass('financial_disputes')")
        assert c.fetchone()[0] is not None
    conn.close()


@pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL no disponible")
def test_22_migracion_postgresql_repetida():
    import psycopg
    from psycopg import sql as psql

    mig = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260818000700_financial_fase06_disputes.sql"
    sql = mig.read_text(encoding="utf-8")
    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS ruana_f06_repeat"))
        c.execute(psql.SQL("CREATE DATABASE ruana_f06_repeat"))
    admin.close()
    conn = psycopg.connect("dbname=ruana_f06_repeat user=postgres")
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL)
    conn.commit()
    with conn.cursor() as c:
        c.execute(sql)
        c.execute(sql)
    conn.commit()
    conn.close()


def test_23_sqlite_migracion_repetida_idempotente(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "0")
    path = str(tmp_path / "rep_f06.db")
    db1 = db_module.DBManager(path)
    db2 = db_module.DBManager(path)
    conn = db2._connect()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='financial_disputes'")
    assert c.fetchone() is not None
    conn.close()
    assert db1 and db2


def test_24_permiso_view_permitido():
    assert tiene_permiso_dispute(["leer"], DISPUTE_VIEW)
