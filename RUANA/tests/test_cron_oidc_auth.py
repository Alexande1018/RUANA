"""Auth cron: secreto compartido + OIDC de Cloud Scheduler."""
from __future__ import annotations

from unittest.mock import patch

from RUANA.web import app as app_module
from RUANA.web import auth_decorators as auth


_SCHEDULER_SA = "ruana-scheduler-invoker@ruana-4293f.iam.gserviceaccount.com"


def _ctx(headers=None):
    return app_module.app.test_request_context("/", headers=headers or {})


def test_cron_secret_acepta_header(monkeypatch):
    monkeypatch.setenv("RUANA_CRON_SECRET", "cron-secret-oidc-test")
    monkeypatch.setattr(auth, "_SCHEDULER_SA", "")
    with _ctx({"X-Ruana-Cron-Secret": "cron-secret-oidc-test"}):
        assert auth._cron_secret_valid() is True


def test_cron_secret_rechaza_header_incorrecto(monkeypatch):
    monkeypatch.setenv("RUANA_CRON_SECRET", "cron-secret-oidc-test")
    monkeypatch.setattr(auth, "_SCHEDULER_SA", "")
    with _ctx({"X-Ruana-Cron-Secret": "otro"}):
        assert auth._cron_secret_valid() is False


def test_cron_secret_rechaza_sin_header(monkeypatch):
    monkeypatch.setenv("RUANA_CRON_SECRET", "cron-secret-oidc-test")
    monkeypatch.setattr(auth, "_SCHEDULER_SA", "")
    with _ctx():
        assert auth._cron_secret_valid() is False


def test_cron_oidc_acepta_token_google_de_sa(monkeypatch):
    monkeypatch.setattr(auth, "_SCHEDULER_SA", _SCHEDULER_SA)
    monkeypatch.delenv("RUANA_CRON_SECRET", raising=False)
    claims = {"email": _SCHEDULER_SA, "email_verified": True}
    with patch.object(auth.id_token, "verify_oauth2_token", return_value=claims) as verify:
        with _ctx({"Authorization": "Bearer google-oidc-token"}):
            assert auth._cron_secret_valid() is True
        verify.assert_called_once()


def test_cron_oidc_rechaza_sa_distinta(monkeypatch):
    monkeypatch.setattr(auth, "_SCHEDULER_SA", _SCHEDULER_SA)
    monkeypatch.setenv("RUANA_CRON_SECRET", "cron-secret-oidc-test")
    claims = {"email": "otro@ruana-4293f.iam.gserviceaccount.com", "email_verified": True}
    with patch.object(auth.id_token, "verify_oauth2_token", return_value=claims):
        with _ctx({"Authorization": "Bearer google-oidc-token"}):
            assert auth._cron_secret_valid() is False


def test_cron_oidc_rechaza_email_no_verificado(monkeypatch):
    monkeypatch.setattr(auth, "_SCHEDULER_SA", _SCHEDULER_SA)
    claims = {"email": _SCHEDULER_SA, "email_verified": False}
    with patch.object(auth.id_token, "verify_oauth2_token", return_value=claims):
        with _ctx({"Authorization": "Bearer google-oidc-token"}):
            assert auth._cron_secret_valid() is False


def test_cron_oidc_rechaza_token_invalido_y_cae_a_secreto(monkeypatch):
    monkeypatch.setattr(auth, "_SCHEDULER_SA", _SCHEDULER_SA)
    monkeypatch.setenv("RUANA_CRON_SECRET", "cron-secret-oidc-test")
    with patch.object(auth.id_token, "verify_oauth2_token", side_effect=ValueError("bad token")):
        with _ctx({
            "Authorization": "Bearer not-a-google-token",
            "X-Ruana-Cron-Secret": "cron-secret-oidc-test",
        }):
            assert auth._cron_secret_valid() is True


def test_cron_oidc_sin_ruana_scheduler_sa_no_abre_oidc(monkeypatch):
    monkeypatch.setattr(auth, "_SCHEDULER_SA", "")
    monkeypatch.setenv("RUANA_CRON_SECRET", "cron-secret-oidc-test")
    with patch.object(auth.id_token, "verify_oauth2_token") as verify:
        with _ctx({"Authorization": "Bearer google-oidc-token"}):
            assert auth._cron_secret_valid() is False
        verify.assert_not_called()


def test_require_admin_escritura_or_cron_acepta_oidc(monkeypatch):
    monkeypatch.setattr(auth, "_SCHEDULER_SA", _SCHEDULER_SA)
    monkeypatch.delenv("RUANA_CRON_SECRET", raising=False)

    @auth.require_admin_escritura_or_cron
    def _vista():
        return {"ok": True}, 200

    claims = {"email": _SCHEDULER_SA, "email_verified": True}
    with patch.object(auth.id_token, "verify_oauth2_token", return_value=claims):
        with _ctx({"Authorization": "Bearer google-oidc-token"}):
            body, status = _vista()
    assert status == 200
    assert body["ok"] is True
