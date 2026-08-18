"""Tests FASE 13A: bloqueantes P0 de auditoría (seguridad Stripe, secretos, ledger, esquema, legacy)."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.conflict_authorization import CONFLICT_RESOLVE
from core.financial.ledger_accounts import CuentaLedger
from core.financial.ledger_estados import EstadoLedgerTransaction
from core.financial.ledger_types import TipoLedgerTransaction
from core.financial_schema_health import (
    REQUIRED_FINANCIAL_TABLES,
    assert_esquema_financiero_completo,
    verificar_esquema_financiero,
)
from core.runtime_environment import is_production, is_test_context, ruana_env
from core.services import financial_ledger_service as fls
from core.services import stripe_webhook_service
from core.startup_validation import (
    StartupConfigurationError,
    validate_cookie_policy,
    validate_secrets,
    validate_startup_configuration,
    validate_stripe_key_prefix_at_runtime,
    validate_stripe_mode_and_keys,
)
from core.stripe_mode_guard import validate_event_livemode
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "0")
    monkeypatch.setenv("RUANA_ENV", "test")
    monkeypatch.setenv("RUANA_STRIPE_MODE", "test")
    return db_module.DBManager(str(tmp_path / "ruana_fase13a.db"))


def _balanced_lines(amount: int = 100000):
    return [
        {"account_code": CuentaLedger.STRIPE_RECEIVABLE.value, "debit_cents": amount},
        {"account_code": CuentaLedger.CLEARING_PAYMENTS.value, "credit_cents": amount},
    ]


def _settings(**overrides):
    base = {
        "flask_secret_key": "x" * 32,
        "stripe_secret_key": "sk_test_valid_key",
        "stripe_webhook_secret": "whsec_" + ("x" * 24),
        "postgres_configured": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# --- P0-1 Stripe test/live ---


def test_stripe_mode_test_requiere_sk_test():
    validate_stripe_mode_and_keys(
        stripe_mode="test", stripe_secret_key="sk_test_abc", production=False
    )


def test_stripe_mode_live_requiere_sk_live():
    validate_stripe_mode_and_keys(
        stripe_mode="live", stripe_secret_key="sk_live_abc", production=False
    )


def test_stripe_mode_test_rechaza_sk_live():
    with pytest.raises(StartupConfigurationError, match="sk_test_"):
        validate_stripe_key_prefix_at_runtime(
            stripe_mode="test", stripe_secret_key="sk_live_abc"
        )


def test_stripe_mode_live_rechaza_sk_test():
    with pytest.raises(StartupConfigurationError, match="sk_live_"):
        validate_stripe_key_prefix_at_runtime(
            stripe_mode="live", stripe_secret_key="sk_test_abc"
        )


def test_stripe_produccion_exige_modo_explicito(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "ruana-prod")
    assert is_production()
    with pytest.raises(StartupConfigurationError, match="RUANA_STRIPE_MODE"):
        validate_stripe_mode_and_keys(stripe_mode="", stripe_secret_key="sk_test_x", production=True)


def test_livemode_test_evento_en_modo_test():
    event = {"id": "evt_test", "livemode": False}
    assert validate_event_livemode(event)["status"] == "success"


def test_livemode_live_evento_en_modo_live(monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_MODE", "live")
    event = {"id": "evt_live", "livemode": True}
    assert validate_event_livemode(event)["status"] == "success"


def test_livemode_mismatch_test_en_live(monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_MODE", "live")
    r = validate_event_livemode({"id": "evt_bad", "livemode": False})
    assert r["status"] == "error"
    assert r["code"] == "stripe_livemode_mismatch"


def test_livemode_mismatch_live_en_test(monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_MODE", "test")
    r = validate_event_livemode({"id": "evt_bad", "livemode": True})
    assert r["status"] == "error"


def test_webhook_rechaza_livemode_cruzado(sqlite_db, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_MODE", "test")
    event = MagicMock()
    event.id = "evt_cross"
    event.type = "ping"
    event.livemode = True
    event.data.object = {}
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        res = stripe_webhook_service.procesar_webhook(sqlite_db, b"{}", "sig")
    assert res["status"] == "error"
    assert res.get("code") == "stripe_livemode_mismatch"


# --- P0-2 Secretos ---


def test_secretos_produccion_rechazan_default_flask():
    with pytest.raises(StartupConfigurationError, match="FLASK_SECRET_KEY"):
        validate_secrets(
            flask_secret_key="ruana_secret_key_dev",
            stripe_secret_key="sk_live_" + "x" * 20,
            stripe_webhook_secret="whsec_" + "x" * 24,
            cron_secret="cron_" + "x" * 20,
            production=True,
        )


def test_secretos_produccion_rechazan_vacios():
    with pytest.raises(StartupConfigurationError):
        validate_secrets(
            flask_secret_key="",
            stripe_secret_key="sk_live_" + "x" * 20,
            stripe_webhook_secret="whsec_" + "x" * 24,
            cron_secret="cron_" + "x" * 20,
            production=True,
        )


def test_secretos_test_context_permite_relajado(monkeypatch):
    monkeypatch.setenv("RUANA_ENV", "test")
    assert is_test_context()
    validate_secrets(
        flask_secret_key="ruana_secret_key_dev",
        stripe_secret_key="",
        stripe_webhook_secret="",
        cron_secret="",
        production=False,
    )


def test_startup_configuration_en_test(monkeypatch):
    monkeypatch.setenv("RUANA_ENV", "test")
    monkeypatch.setenv("RUANA_STRIPE_MODE", "test")
    validate_startup_configuration(_settings())


# --- P0-3 Cookies ---


def test_cookies_produccion_exigen_secure():
    with pytest.raises(StartupConfigurationError, match="SESSION_COOKIE_SECURE"):
        validate_cookie_policy(session_cookie_secure=False, production=True)


def test_app_cookie_secure_en_test_no_produccion():
    assert app_module.app.config.get("SESSION_COOKIE_SECURE") is False


# --- P0-4 Ledger inmutable ---


def test_ledger_posted_update_sql_bloqueado(sqlite_db):
    fls.publicar_transaccion(
        sqlite_db,
        idempotency_key="p13-update",
        contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED,
        moneda="eur",
        lineas=_balanced_lines(),
        actor_origen="test",
    )
    conn = sqlite_db._connect()
    with pytest.raises(sqlite3.IntegrityError, match="downgrade|inmutables"):
        conn.execute(
            "UPDATE ledger_transactions SET estado = 'DRAFT' "
            "WHERE idempotency_key = 'p13-update'"
        )
        conn.commit()
    conn.close()


def test_ledger_posted_delete_sql_bloqueado(sqlite_db):
    fls.publicar_transaccion(
        sqlite_db,
        idempotency_key="p13-delete",
        contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED,
        moneda="eur",
        lineas=_balanced_lines(),
        actor_origen="test",
    )
    conn = sqlite_db._connect()
    with pytest.raises(sqlite3.IntegrityError, match="eliminar"):
        conn.execute(
            "DELETE FROM ledger_transactions WHERE idempotency_key = 'p13-delete'"
        )
        conn.commit()
    conn.close()


def test_ledger_entry_posted_update_bloqueado(sqlite_db):
    fls.publicar_transaccion(
        sqlite_db,
        idempotency_key="p13-entry",
        contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED,
        moneda="eur",
        lineas=_balanced_lines(),
        actor_origen="test",
    )
    conn = sqlite_db._connect()
    with pytest.raises(sqlite3.IntegrityError, match="inmutables"):
        conn.execute(
            "UPDATE ledger_entries SET credit_cents = 1 "
            "WHERE ledger_transaction_id = "
            "(SELECT id FROM ledger_transactions WHERE idempotency_key='p13-entry')"
        )
        conn.commit()
    conn.close()


def test_ledger_void_compensatorio_permitido(sqlite_db):
    pub = fls.publicar_transaccion(
        sqlite_db,
        idempotency_key="p13-void-src",
        contacto_id=1,
        tipo=TipoLedgerTransaction.PAYMENT_RECEIVED,
        moneda="eur",
        lineas=_balanced_lines(),
        actor_origen="test",
    )
    tx_id = pub["transaction_id"]
    void = fls.anular_transaccion(
        sqlite_db,
        tx_id,
        actor="admin_test",
        idempotency_key="p13-void-inv",
        motivo="corrección auditoría",
    )
    assert void["status"] == "success"
    assert void["estado"] == EstadoLedgerTransaction.VOIDED.value
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado, reversa_de_id FROM ledger_transactions WHERE id = ?",
        (void["compensation_id"],),
    ).fetchone()
    conn.close()
    assert row is not None


# --- P0-5 Esquema financiero ---


def test_esquema_financiero_completo_sqlite(sqlite_db):
    conn = sqlite_db._connect()
    r = verificar_esquema_financiero(conn.cursor())
    conn.close()
    assert r["ok"] is True
    assert not r["faltantes"]
    for t in REQUIRED_FINANCIAL_TABLES:
        assert t in r["presentes"]


def test_esquema_incompleto_no_tumba_arranque_sqlite(tmp_path, monkeypatch):
    """FASE 13A hotfix: esquema incompleto alerta pero no impide importar la app."""
    monkeypatch.setenv("RUANA_ENV", "test")
    db_path = tmp_path / "incomplete.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE payment_conflicts (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="Esquema financiero incompleto"):
        conn2 = sqlite3.connect(str(db_path))
        try:
            assert_esquema_financiero_completo(conn2.cursor())
        finally:
            conn2.close()


def test_schema_health_endpoint_ok(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ADM13", permisos=["leer"])
    resp = client.get("/api/admin/financial/schema-health", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True


# --- P0-6 Legacy bypass ---


def test_legacy_payment_conflicts_escritura_no_resuelve(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ESC13", permisos=["escribir"])
    resp = client.post(
        "/api/admin/payment-conflicts/1/resolver",
        json={"decision": "contratante", "comentario": "bypass intent"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.get_json().get("permiso_requerido") == CONFLICT_RESOLVE


def test_legacy_payment_conflicts_configurar_retorna_410(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "CFG13", permisos=["configurar"])
    resp = client.post(
        "/api/admin/payment-conflicts/1/resolver",
        json={"decision": "contratante", "comentario": "legacy"},
        headers=headers,
    )
    assert resp.status_code == 410
    assert resp.get_json().get("code") == "legacy_endpoint_removed"


def test_legacy_conflictos_pago_escribir_retorna_410(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers("admin", "ESC13B", permisos=["escribir"])
    resp = client.post(
        "/api/admin/conflictos-pago/1/resolver",
        json={"importe_valido": 100.0},
        headers=headers,
    )
    assert resp.status_code == 410
    assert resp.get_json().get("code") == "legacy_endpoint_removed"


def test_ruana_env_test_en_pytest():
    assert ruana_env() == "test"
