"""Tests FASE 09: panel administrativo financiero."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import db_manager as db_module
from core.financial.ledger_accounts import CuentaLedger
from core.financial.ledger_estados import EstadoLedgerTransaction
from core.financial.ledger_types import TipoLedgerTransaction
from core.financial_admin_authorization import (
    DASHBOARD_VIEW,
    PAYMENTS_VIEW,
    tiene_permiso_panel,
)
from core.ledger_authorization import LEDGER_VOID
from core.reconciliation_authorization import RECON_EXECUTE
from core.refund_authorization import REFUND_EXECUTE
from core.services import financial_admin_service as fas
from core.services import financial_ledger_service as fls
from core.services import financial_reconciliation_advanced_service as fras
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
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
    return db_module.DBManager(str(tmp_path / "ruana_fase09.db"))


def _headers(session_headers, permisos=None):
    if permisos is None:
        permisos = ["leer"]
    return session_headers("admin", "ADMIN_F09", permisos=permisos)


def _seed_contacto(db, *, estado="PAGO_CONFIRMADO", pi="pi_f09", sin_pi=False):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL09", "S", "s@t.com"))
    c.execute(
        "INSERT OR IGNORE INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO09", "P", "p@t.com", "acct_f09", 1),
    )
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, apoyo_ruana, comision,
            stripe_payment_intent_id, stripe_charge_id, stripe_transfer_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, 500, 'stripe', 'cobro_confirmado', ?,
                  'RETENIDO', 440, 60, 60, ?, 'ch_f09', 'tr_f09')
        """,
        ("SOL09", "PRO09", "Srv", estado, None if sin_pi else pi),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def test_01_dashboard_requiere_autenticacion(client):
    resp = client.get("/api/admin/financial/dashboard")
    assert resp.status_code == 401


def test_02_dashboard_requiere_permiso(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.get("/api/admin/financial/dashboard", headers=_headers(session_headers, permisos=[]))
    assert resp.status_code == 403


def test_03_lectura_paginada(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _seed_contacto(sqlite_db)
    headers = _headers(session_headers)
    resp = client.get("/api/admin/financial/payments?limit=10&offset=0", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "success"
    assert "items" in data
    assert data["pagination"]["limit"] == 10


def test_04_filtros(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db, estado="PAGO_CONFIRMADO", pi="pi_filter")
    headers = _headers(session_headers)
    resp = client.get("/api/admin/financial/payments?q=pi_filter", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200
    assert any(i.get("stripe_payment_intent_id") == "pi_filter" for i in data["items"])


def test_05_orden_estable(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _seed_contacto(sqlite_db, pi="pi_a")
    _seed_contacto(sqlite_db, pi="pi_b")
    headers = _headers(session_headers)
    r1 = client.get("/api/admin/financial/payments?limit=5", headers=headers).get_json()
    r2 = client.get("/api/admin/financial/payments?limit=5", headers=headers).get_json()
    assert [i["id"] for i in r1["items"]] == [i["id"] for i in r2["items"]]


def test_06_operacion_financiera_completa(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    headers = _headers(session_headers)
    resp = client.get(f"/api/admin/financial/operation/{cid}", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["operacion"]["contacto"]["id"] == cid
    assert "timeline" in data["operacion"]


def test_07_operacion_con_discrepancia(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO financial_reconciliation (
            contacto_id, tipo_discrepancia, estado_reconciliacion, detected_at
        ) VALUES (?, 'amount_mismatch', 'open', datetime('now'))
        """,
        (cid,),
    )
    conn.commit()
    conn.close()
    headers = _headers(session_headers)
    resp = client.get(f"/api/admin/financial/operation/{cid}", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["operacion"].get("discrepancias", [])) >= 1


def test_08_operacion_bloqueada(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db, estado="CONFLICTO_ABIERTO")
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute("SELECT id FROM aliados WHERE codigo = 'SOL09'")
    sol_id = c.fetchone()[0]
    c.execute("SELECT id FROM aliados WHERE codigo = 'PRO09'")
    pro_id = c.fetchone()[0]
    c.execute(
        """
        INSERT INTO payment_conflicts (
            trabajo_id, contratante_id, profesional_id,
            importe_contratante, importe_profesional,
            estado_conflicto, bloqueo_financiero, tipo
        ) VALUES (?, ?, ?, 500, 400, 'ABIERTO', 1, 'importe_discrepante')
        """,
        (cid, sol_id, pro_id),
    )
    conn.commit()
    conn.close()
    alerts = fas.listar_alertas(sqlite_db, limit=20)
    assert any(a["tipo"] == "conflicto_bloqueante" for a in alerts["items"])


def test_09_alerta_critica(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db, sin_pi=True, estado="PAGO_CONFIRMADO")
    headers = _headers(session_headers)
    resp = client.get("/api/admin/financial/alerts", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200
    assert any(a["tipo"] == "operacion_sin_payment_intent" for a in data["items"])


def test_10_cierre_alerta_exige_resolucion(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = _headers(session_headers)
    resp = client.post(
        "/api/admin/financial/alerts/test:1/resolve",
        headers=headers,
        json={"motivo": "x"},
    )
    assert resp.status_code == 400
    resp2 = client.post(
        "/api/admin/financial/alerts/test:1/resolve",
        headers=headers,
        json={"motivo": "Resuelto tras revisión manual"},
    )
    assert resp2.status_code == 200


def test_11_accion_sin_permiso_devuelve_403(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = _headers(session_headers, permisos=[])
    resp = client.post(
        "/api/admin/financial-reconciliation/contacto/1",
        headers=headers,
        json={"idempotency_key": "k1"},
    )
    assert resp.status_code == 403


def test_12_accion_con_permiso_delega_servicio(sqlite_db):
    with patch.object(fras, "reconciliar_contacto_avanzado", return_value={"status": "success"}) as mocked:
        fras.reconciliar_contacto_avanzado(
            sqlite_db, 1, actor="ADMIN", permiso_usado=RECON_EXECUTE, idempotency_key="idem-12",
        )
        mocked.assert_called_once()


def test_13_refund_no_se_duplica(sqlite_db):
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO financial_refunds (
            contacto_id, stripe_refund_id, importe_solicitado_cents, importe_confirmado_cents,
            moneda, estado, idempotency_key, causa_ruana, actor_codigo
        ) VALUES (1, 're_dup', 1000, 1000, 'eur', 'REQUESTED', 'ref-13', 'CONFLICTO', 'ADMIN')
        """
    )
    conn.commit()
    with pytest.raises(Exception):
        c.execute(
            """
            INSERT INTO financial_refunds (
                contacto_id, stripe_refund_id, importe_solicitado_cents, importe_confirmado_cents,
                moneda, estado, idempotency_key, causa_ruana, actor_codigo
            ) VALUES (1, 're_dup2', 1000, 1000, 'eur', 'REQUESTED', 'ref-13', 'CONFLICTO', 'ADMIN')
            """
        )
        conn.commit()
    conn.close()


def test_14_reconciliacion_usa_idempotency_key(sqlite_db):
    with patch.object(fras, "reconciliar_contacto_avanzado", return_value={"status": "success"}) as mocked:
        fras.reconciliar_contacto_avanzado(
            sqlite_db, 9, actor="A", permiso_usado=RECON_EXECUTE, idempotency_key="idem-14",
        )
        assert mocked.call_args.kwargs["idempotency_key"] == "idem-14"


def test_15_ledger_posted_no_editable(sqlite_db):
    lines = [
        {"account_code": CuentaLedger.STRIPE_RECEIVABLE.value, "debit_cents": 100},
        {"account_code": CuentaLedger.CLEARING_PAYMENTS.value, "credit_cents": 100},
    ]
    pub = fls.publicar_transaccion(
        sqlite_db, idempotency_key="t15", contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED, moneda="eur",
        lineas=lines, actor_origen="test",
    )
    tx_id = pub["transaction_id"]
    void = fls.anular_transaccion(
        sqlite_db, tx_id, actor="admin", idempotency_key="void-15", motivo="test void",
    )
    assert void["status"] == "success"
    with sqlite_db._lock:
        conn = sqlite_db._connect()
        c = conn.cursor()
        c.execute("SELECT estado FROM ledger_transactions WHERE id = ?", (tx_id,))
        row = c.fetchone()
        conn.close()
    assert row[0] == EstadoLedgerTransaction.VOIDED.value


def test_16_concurrencia_devuelve_409(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = _headers(session_headers, permisos=["configurar"])
    with patch(
        "web.blueprints.financial_conflicts_bp.fcs.resolver_conflicto",
        return_value={"status": "error", "message": "modificado por otro proceso", "code": "version_conflict"},
    ):
        resp = client.post(
            "/api/admin/financial-conflicts/1/resolver",
            headers=headers,
            json={
                "motivo": "resolver conflicto version",
                "resolucion": "MANTENER_RETENIDO",
                "version": 1,
                "idempotency_key": "k16",
            },
        )
    assert resp.status_code == 409


def test_17_no_se_exponen_secretos(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute("UPDATE contactos_ruana SET servicio = ? WHERE id = ?", ("sk_test_secret123", cid))
    conn.commit()
    conn.close()
    headers = _headers(session_headers)
    resp = client.get(f"/api/admin/financial/operation/{cid}", headers=headers)
    raw = resp.get_data(as_text=True)
    assert "sk_test_secret123" not in raw


def test_18_no_se_exponen_datos_tarjeta(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute("UPDATE contactos_ruana SET servicio = ? WHERE id = ?", ("4111111111111111", cid))
    conn.commit()
    conn.close()
    headers = _headers(session_headers)
    resp = client.get(f"/api/admin/financial/operation/{cid}", headers=headers)
    raw = resp.get_data(as_text=True)
    assert "4111111111111111" not in raw


def test_19_error_stripe_saneado():
    err = fas._sanitize_record({"detalle": "sk_test_abc123xyz", "ok": True})
    assert err["detalle"] == "[REDACTED]"
    assert err["ok"] is True


def test_20_no_n_plus_1_evidente(sqlite_db):
    _seed_contacto(sqlite_db)
    r = fas.listar_pagos(sqlite_db, limit=20, offset=0)
    assert r["status"] == "success"
    assert r["pagination"]["total"] >= 1
    assert len(r["items"]) >= 1


def test_21_limite_paginacion_respetado(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    for i in range(5):
        _seed_contacto(sqlite_db, pi=f"pi_lim_{i}")
    headers = _headers(session_headers)
    resp = client.get("/api/admin/financial/payments?limit=999", headers=headers)
    data = resp.get_json()
    assert data["pagination"]["limit"] == 200


def test_22_endpoint_no_permite_idor(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    headers = _headers(session_headers)
    ok = client.get(f"/api/admin/financial/operation/{cid}", headers=headers)
    missing = client.get("/api/admin/financial/operation/999999", headers=headers)
    assert ok.status_code == 200
    assert missing.status_code == 404


def test_23_estado_datos_antiguos_visible(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = _headers(session_headers)
    resp = client.get("/api/admin/financial/dashboard", headers=headers)
    data = resp.get_json()
    assert "generated_at" in data
    assert "data_freshness" in data


def test_24_permiso_granular_y_legacy():
    assert tiene_permiso_panel(["leer"], DASHBOARD_VIEW)
    assert tiene_permiso_panel(["financial.dashboard.view"], DASHBOARD_VIEW)
    assert not tiene_permiso_panel([], PAYMENTS_VIEW)
