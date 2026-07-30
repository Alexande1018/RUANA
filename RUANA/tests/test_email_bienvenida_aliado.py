"""Tests del servicio de correo de bienvenida al registrarse."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.email_service import (
    ASUNTO_BIENVENIDA,
    _construir_cuerpo_bienvenida,
    enviar_correo_bienvenida_aliado,
)


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_email_test.db"))


def test_construir_cuerpo_bienvenida_contiene_nombre_y_codigo():
    cuerpo = _construir_cuerpo_bienvenida("María López", "12345")
    assert "María López" in cuerpo
    assert "12345" in cuerpo
    assert "Tu Código de Aliado es:" in cuerpo
    assert "Equipo RUANA." in cuerpo


def test_enviar_correo_sin_codigo_no_envia():
    with patch("core.email_service.smtplib.SMTP") as smtp_mock:
        ok = enviar_correo_bienvenida_aliado("Juan", "juan@test.com", "")
    assert ok is False
    smtp_mock.assert_not_called()


def test_enviar_correo_sin_email_no_envia():
    with patch("core.email_service.smtplib.SMTP") as smtp_mock:
        ok = enviar_correo_bienvenida_aliado("Juan", "", "12345")
    assert ok is False
    smtp_mock.assert_not_called()


def test_enviar_correo_sin_smtp_configurado_no_envia(monkeypatch):
    monkeypatch.delenv("RUANA_SMTP_PASSWORD", raising=False)
    from core import settings as settings_module

    settings_module.get_settings.cache_clear()

    with patch("core.email_service.smtplib.SMTP") as smtp_mock:
        ok = enviar_correo_bienvenida_aliado("Juan", "juan@test.com", "12345")

    assert ok is False
    smtp_mock.assert_not_called()
    settings_module.get_settings.cache_clear()


def test_enviar_correo_exitoso(monkeypatch):
    monkeypatch.setenv("RUANA_SMTP_PASSWORD", "test-app-password")
    from core import settings as settings_module

    settings_module.get_settings.cache_clear()

    smtp_instance = MagicMock()
    smtp_instance.__enter__ = MagicMock(return_value=smtp_instance)
    smtp_instance.__exit__ = MagicMock(return_value=False)

    with patch("core.email_service.smtplib.SMTP", return_value=smtp_instance) as smtp_mock:
        ok = enviar_correo_bienvenida_aliado("Juan Pérez", "juan@test.com", "54321")

    assert ok is True
    smtp_mock.assert_called_once()
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once()
    smtp_instance.send_message.assert_called_once()
    sent_msg = smtp_instance.send_message.call_args[0][0]
    assert sent_msg["Subject"] == ASUNTO_BIENVENIDA
    assert sent_msg["To"] == "juan@test.com"
    assert "54321" in sent_msg.get_content()

    settings_module.get_settings.cache_clear()


def test_enviar_correo_fallo_smtp_no_lanza(monkeypatch):
    monkeypatch.setenv("RUANA_SMTP_PASSWORD", "test-app-password")
    from core import settings as settings_module

    settings_module.get_settings.cache_clear()

    with patch("core.email_service.smtplib.SMTP", side_effect=OSError("connection refused")):
        ok = enviar_correo_bienvenida_aliado("Juan", "juan@test.com", "12345")

    assert ok is False
    settings_module.get_settings.cache_clear()


def test_registro_envia_correo_sin_bloquear_si_falla(client, sqlite_db, monkeypatch):
    """El registro debe completarse aunque falle el envío del correo."""
    from RUANA.web import app as app_module

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    with patch(
        "RUANA.web.app.enviar_correo_bienvenida_aliado",
        side_effect=RuntimeError("SMTP caído"),
    ):
        response = client.post(
            "/api/aliados/registrar",
            json={
                "nombre": "Test Correo",
                "marca": "TC",
                "oficio": "Electricidad",
                "codigo_postal": "28013",
                "email": "testcorreo@example.com",
                "telefono": "+34600111222",
            },
        )

    assert response.status_code == 201, response.get_json()
    data = response.get_json()
    assert data.get("status") == "success"
    assert data.get("codigo")


def test_registro_llama_envio_correo_con_codigo(client, sqlite_db, monkeypatch):
    from RUANA.web import app as app_module

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    with patch("RUANA.web.app.enviar_correo_bienvenida_aliado", return_value=True) as send_mock:
        response = client.post(
            "/api/aliados/registrar",
            json={
                "nombre": "Ana Ruana",
                "marca": "AR",
                "oficio": "Fontanería y fontanería-gas",
                "codigo_postal": "28013",
                "email": "ana.ruana@example.com",
                "telefono": "+34600333444",
            },
        )

    assert response.status_code == 201
    send_mock.assert_called_once()
    kwargs = send_mock.call_args.kwargs
    assert kwargs["nombre"] == "Ana Ruana"
    assert kwargs["email"] == "ana.ruana@example.com"
    assert kwargs["codigo"] == response.get_json()["codigo"]
