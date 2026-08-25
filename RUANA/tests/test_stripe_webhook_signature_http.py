"""Tests HTTP del webhook Stripe con firma HMAC (sin secretos reales en repo)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import db_manager as db_module

# Solo para tests: no es un signing secret de producción ni de Stripe Dashboard.
_WHSEC_TEST = "whsec_pytest_webhook_secret_24"


def _sign_payload(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    signed = f"{ts}.{payload.decode('utf-8')}"
    sig = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _diag_event_payload(event_id: str = "evt_http_sig_test") -> bytes:
    body = {
        "id": event_id,
        "object": "event",
        "type": "diag.ping",
        "livemode": False,
        "data": {"object": {"id": "obj_http", "object": "ping"}},
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def webhook_http_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", _WHSEC_TEST)
    monkeypatch.setenv("RUANA_STRIPE_MODE", "test")
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
            stripe_webhook_secret=_WHSEC_TEST,
        ),
    )
    db = db_module.DBManager(str(tmp_path / "wh_http.db"))
    return db


@pytest.fixture
def webhook_client(webhook_http_env, monkeypatch):
    from RUANA.web import app as app_module

    monkeypatch.setattr(app_module, "get_db", lambda: webhook_http_env)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_http_valid_signature_not_400(webhook_client):
    payload = _diag_event_payload()
    sig = _sign_payload(payload, _WHSEC_TEST)
    resp = webhook_client.post(
        "/api/stripe/webhook",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": sig,
        },
    )
    assert resp.status_code != 400
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["event_type"] == "diag.ping"


def test_http_altered_body_returns_400(webhook_client):
    payload = _diag_event_payload("evt_http_altered")
    sig = _sign_payload(payload, _WHSEC_TEST)
    tampered = payload[:-1] + (b"x" if payload[-1:] != b"x" else b"y")
    resp = webhook_client.post(
        "/api/stripe/webhook",
        data=tampered,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": sig,
        },
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Firma webhook inválida"


def test_http_missing_signature_returns_400(webhook_client):
    payload = _diag_event_payload("evt_http_no_sig")
    resp = webhook_client.post(
        "/api/stripe/webhook",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"


def test_http_processing_error_after_valid_signature_returns_500(
    webhook_http_env, webhook_client,
):
    payload = _diag_event_payload("evt_http_proc_fail")
    sig = _sign_payload(payload, _WHSEC_TEST)
    with patch(
        "core.services.stripe_webhook_service._handle_desconocido",
        side_effect=RuntimeError("simulated_failure"),
    ):
        resp = webhook_client.post(
            "/api/stripe/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": sig,
            },
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Error interno del servidor"
