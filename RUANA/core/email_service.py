"""Servicio de envío de correos transaccionales para RUANA.

La configuración SMTP se lee desde variables de entorno (ver settings.py).
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from core.settings import get_settings

logger = logging.getLogger(__name__)

ASUNTO_BIENVENIDA = "Bienvenido a RUANA"


def _construir_cuerpo_bienvenida(nombre: str, codigo: str) -> str:
    nombre_limpio = (nombre or "").strip() or "Aliado"
    return (
        f"Hola, {nombre_limpio}.\n\n"
        "Tu registro en RUANA se ha completado correctamente.\n\n"
        "Tu Código de Aliado es:\n\n"
        f"{codigo}\n\n"
        "Guárdalo, ya que será tu identificador permanente dentro de RUANA.\n\n"
        "En tu primer acceso deberás crear un PIN personal de 4 a 6 dígitos.\n"
        "A partir de entonces entrarás con código + PIN.\n\n"
        "Si alguna vez olvidas tu PIN o tu código, podrás recuperarlos desde la pantalla de acceso.\n\n"
        "Bienvenido a la Red Unida de Apoyo para Negocios entre Aliados.\n\n"
        "Equipo RUANA."
    )


def _smtp_configurado() -> bool:
    settings = get_settings()
    return bool(
        settings.smtp_host
        and settings.smtp_user
        and settings.smtp_password
    )


def enviar_correo_bienvenida_aliado(
    nombre: str,
    email: str,
    codigo: str,
) -> bool:
    """Envía el correo de bienvenida con el código de aliado.

    Retorna True si el envío fue exitoso, False en caso contrario.
    No lanza excepciones: los errores se registran en logs.
    """
    codigo_limpio = (codigo or "").strip()
    email_limpio = (email or "").strip()
    nombre_limpio = (nombre or "").strip()

    if not codigo_limpio:
        logger.error(
            "[RUANA][EMAIL] No se envió correo de bienvenida: código de aliado vacío (email=%s)",
            email_limpio or "(sin email)",
        )
        return False

    if not email_limpio:
        logger.error(
            "[RUANA][EMAIL] No se envió correo de bienvenida: email vacío (codigo=%s)",
            codigo_limpio,
        )
        return False

    if not _smtp_configurado():
        logger.warning(
            "[RUANA][EMAIL] SMTP no configurado; omitiendo correo de bienvenida para %s (codigo=%s)",
            email_limpio,
            codigo_limpio,
        )
        return False

    settings = get_settings()
    from_email = settings.smtp_from_email or settings.smtp_user

    msg = EmailMessage()
    msg["Subject"] = ASUNTO_BIENVENIDA
    msg["From"] = from_email
    msg["To"] = email_limpio
    msg.set_content(_construir_cuerpo_bienvenida(nombre_limpio, codigo_limpio))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info(
            "[RUANA][EMAIL] Correo de bienvenida enviado a %s (codigo=%s)",
            email_limpio,
            codigo_limpio,
        )
        return True
    except Exception as exc:
        logger.exception(
            "[RUANA][EMAIL] Error al enviar correo de bienvenida a %s (codigo=%s): %s",
            email_limpio,
            codigo_limpio,
            exc,
        )
        return False


def enviar_correo_recuperacion_acceso(
    email: str,
    tipo: str,
    codigo_temporal: str,
    validez_minutos: int,
) -> bool:
    """Envía código temporal de recuperación de acceso (PIN/código)."""
    email_limpio = (email or "").strip()
    if not email_limpio:
        logger.error("[RUANA][EMAIL] Recuperación omitida: email vacío")
        return False

    if not _smtp_configurado():
        logger.warning(
            "[RUANA][EMAIL] SMTP no configurado; omitiendo correo de recuperación"
        )
        return False

    tipo = (tipo or "").strip().lower()
    if tipo == "pin":
        asunto = "Recuperación de PIN — RUANA"
        cuerpo = (
            "Has solicitado restablecer tu PIN personal en RUANA.\n\n"
            f"Tu código temporal es: {codigo_temporal}\n\n"
            f"Caduca en {validez_minutos} minutos y solo puede usarse una vez.\n\n"
            "Si no solicitaste este cambio, ignora este correo.\n\n"
            "Equipo RUANA."
        )
    elif tipo == "codigo":
        asunto = "Recuperación de código de aliado — RUANA"
        cuerpo = (
            "Has solicitado recuperar tu código de aliado en RUANA.\n\n"
            f"Tu código temporal de verificación es: {codigo_temporal}\n\n"
            f"Caduca en {validez_minutos} minutos y solo puede usarse una vez.\n\n"
            "Si no solicitaste este cambio, ignora este correo.\n\n"
            "Equipo RUANA."
        )
    else:
        asunto = "Recuperación de acceso — RUANA"
        cuerpo = (
            "Has solicitado recuperar tu acceso a RUANA.\n\n"
            f"Tu código temporal de verificación es: {codigo_temporal}\n\n"
            f"Caduca en {validez_minutos} minutos y solo puede usarse una vez.\n\n"
            "Si no solicitaste este cambio, ignora este correo.\n\n"
            "Equipo RUANA."
        )

    settings = get_settings()
    from_email = settings.smtp_from_email or settings.smtp_user

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = from_email
    msg["To"] = email_limpio
    msg.set_content(cuerpo)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("[RUANA][EMAIL] Correo de recuperación enviado")
        return True
    except Exception as exc:
        logger.exception("[RUANA][EMAIL] Error al enviar correo de recuperación: %s", exc)
        return False
