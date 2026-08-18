"""Tests FASE 10: seguridad financiera, aprobaciones y permisos centralizados."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.conflict_authorization import CONFLICT_RESOLVE
from core.financial_security_authorization import (
    CONFLICTS_VIEW,
    REFUND_AUTHORIZE,
    REFUND_REQUEST,
    normalizar_permiso,
    tiene_permiso_financiero,
)
from core.financial.refund_estados import CausaReembolso
from core.services import financial_action_approval_service as faas
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RUANA_FINANCIAL_REQUIRE_APPROVAL", "1")
    monkeypatch.setenv("RUANA_FINANCIAL_ALLOW_SELF_APPROVAL", "0")
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
    db = db_module.DBManager(str(tmp_path / "ruana_fase10.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    return db


def _headers(session_headers, codigo="ADMIN_F10", permisos=None):
    return session_headers("admin", codigo, permisos=permisos or ["leer"])


def _seed_contacto(db):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL10", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO10", "P", "p@t.com", "acct_f10", 1),
    )
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, apoyo_ruana, comision,
            stripe_payment_intent_id, stripe_charge_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, 500, 'stripe', 'cobro_confirmado',
                  'PAGO_CONFIRMADO', 'RETENIDO', 440, 60, 60, 'pi_f10', 'ch_f10')
        """,
        ("SOL10", "PRO10", "Srv"),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def test_01_alias_permiso_conflict_view(sqlite_db):
    assert normalizar_permiso("conflict.view") == CONFLICTS_VIEW
    assert tiene_permiso_financiero(["leer"], CONFLICTS_VIEW)


def test_02_legacy_resolver_sin_permiso_403(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.post(
        "/api/admin/payment-conflicts/1/resolver",
        json={"decision": "contratante", "comentario": "test comentario"},
        headers=_headers(session_headers, permisos=["leer"]),
    )
    assert resp.status_code == 403
    assert resp.get_json().get("permiso_requerido") == CONFLICT_RESOLVE


def test_03_legacy_resolver_con_configurar_no_403(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.post(
        "/api/admin/payment-conflicts/999/resolver",
        json={"decision": "contratante", "comentario": "test comentario"},
        headers=_headers(session_headers, permisos=["configurar"]),
    )
    assert resp.status_code != 403


def test_04_idor_contacto_inexistente(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = _headers(session_headers, permisos=["configurar"])
    resp = client.get("/api/admin/financial-refunds/disponible/99999", headers=headers)
    assert resp.status_code == 404


def test_05_flujo_aprobacion_request_y_autorizar(sqlite_db, monkeypatch):
    monkeypatch.setenv("RUANA_FINANCIAL_ALLOW_SELF_APPROVAL", "0")
    cid = _seed_contacto(sqlite_db)
    req = faas.solicitar_accion(
        sqlite_db,
        action_type=faas.ACTION_REFUND_EXECUTE,
        contacto_id=cid,
        actor="SOLICITANTE",
        permiso=REFUND_REQUEST,
        importe_cents=50000,
        currency="eur",
        motivo="solicitud de prueba fase10",
        idempotency_key="idem-f10-01",
    )
    assert req["status"] == "success"
    approval_id = req["approval_id"]

    denied = faas.autorizar_accion(
        sqlite_db, approval_id,
        actor="SOLICITANTE",
        permiso=REFUND_AUTHORIZE,
    )
    assert denied.get("code") == "separation_of_duties"

    ok = faas.autorizar_accion(
        sqlite_db, approval_id,
        actor="AUTORIZADOR",
        permiso=REFUND_AUTHORIZE,
        motivo="aprobado en test",
    )
    assert ok["status"] == "success"
    assert ok["estado"] == "APPROVED"


def test_06_audit_log_tras_solicitud(sqlite_db):
    cid = _seed_contacto(sqlite_db)
    faas.solicitar_accion(
        sqlite_db,
        action_type=faas.ACTION_REFUND_EXECUTE,
        contacto_id=cid,
        actor="AUDITOR_TEST",
        permiso=REFUND_REQUEST,
        importe_cents=10000,
        currency="eur",
        motivo="auditoria fase diez",
        idempotency_key="idem-f10-audit",
    )
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM financial_audit_log WHERE actor_codigo = ? AND accion = ?",
        ("AUDITOR_TEST", "approval_requested"),
    )
    count = c.fetchone()[0]
    conn.close()
    assert count >= 1


def test_07_ejecutar_sin_aprobacion_rechazado(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    headers = _headers(session_headers, permisos=["configurar"])
    resp = client.post(
        "/api/admin/financial-refunds/ejecutar",
        json={
            "contacto_id": cid,
            "importe_solicitado_cents": 50000,
            "parte_ejecutada_cents": 50000,
            "causa_ruana": CausaReembolso.SERVICIO_NO_INICIADO.value,
            "idempotency_key": "ej-sin-aprob",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "approval_id" in (resp.get_json().get("message") or "")


def test_08_solicitar_reembolso_http(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    headers = _headers(session_headers, codigo="REQ_F10", permisos=["escribir"])
    resp = client.post(
        "/api/admin/financial-refunds/solicitar",
        json={
            "contacto_id": cid,
            "importe_solicitado_cents": 25000,
            "motivo": "solicitud http fase10",
            "idempotency_key": "http-req-f10",
        },
        headers=headers,
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "success"
    assert data["estado"] == "REQUESTED"


def test_09_permisos_refund_request_escribir(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    cid = _seed_contacto(sqlite_db)
    headers = _headers(session_headers, permisos=["leer"])
    resp = client.post(
        "/api/admin/financial-refunds/solicitar",
        json={
            "contacto_id": cid,
            "importe_solicitado_cents": 1000,
            "motivo": "debe fallar permiso",
            "idempotency_key": "perm-deny",
        },
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.get_json().get("permiso_requerido") == REFUND_REQUEST


def test_10_ruana_session_cookie_secure_env(monkeypatch):
    monkeypatch.setenv("RUANA_SESSION_COOKIE_SECURE", "true")
    val = __import__("os").environ.get("RUANA_SESSION_COOKIE_SECURE", "").strip().lower()
    assert val in ("1", "true", "yes")
