"""Servicio de dominio: PIN personal y recuperación de acceso aliado."""

from __future__ import annotations

import hashlib
import os
import random
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.aliado_pin_auth import (
    GENERIC_CREDENTIALS_ERROR,
    PIN_BLOQUEO_SEGUNDOS,
    PIN_MAX_INTENTOS,
    crear_setup_token,
    esta_bloqueado_por_pin,
    hash_pin,
    validar_formato_pin,
    validar_setup_token,
    verificar_pin,
)
from core.repositories.aliado_repo import AliadoRepo
from core.services import schema_service

_repo = AliadoRepo()

RECUPERACION_OTP_MINUTOS = int(os.environ.get("RUANA_RECUPERACION_OTP_MINUTOS", "15"))
RECUPERACION_MAX_INTENTOS = int(os.environ.get("RUANA_RECUPERACION_MAX_INTENTOS", "5"))
RECUPERACION_MENSAJE_GENERICO = (
    "Si los datos son correctos, recibirás un correo con instrucciones en unos minutos."
)


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _hash_otp(codigo: str, salt: str) -> str:
    material = f"{salt}:{(codigo or '').strip()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _generar_otp() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def _asegurar_esquema_pin(db) -> None:
    schema_service.ensure_aliados_pin_schema(db)


def aliado_tiene_pin(aliado: Optional[Dict[str, Any]]) -> bool:
    if not aliado:
        return False
    return bool((aliado.get("pin_hash") or "").strip())


def validar_login_aliado(db, codigo: str, pin: Optional[str]) -> Dict[str, Any]:
    """Valida credenciales de login. No crea sesión."""
    codigo = (codigo or "").strip()
    pin = (pin or "").strip()

    aliado = db.obtener_aliado_por_codigo(codigo)
    if not aliado:
        return {"ok": False, "message": GENERIC_CREDENTIALS_ERROR, "http_status": 401}

    estado = aliado.get("estado")
    if estado == "expulsado":
        return {
            "ok": False,
            "message": "Código desactivado. Se requiere nueva invitación para volver.",
            "http_status": 403,
        }
    if estado == "pendiente_validacion":
        return {
            "ok": False,
            "message": "Tu cuenta está pendiente de validación. No puedes acceder al panel hasta que un administrador la active.",
            "http_status": 403,
        }
    if estado == "rechazado":
        return {"ok": False, "message": "Tu solicitud de registro no fue aceptada.", "http_status": 403}
    if estado == "suspendido_temporal":
        return {"ok": False, "message": "Acceso suspendido temporalmente.", "http_status": 403}
    if estado == "en_espera":
        return {
            "ok": False,
            "message": "Estás en la lista de Suplentes. En cuanto se libere una plaza en tu zona, el equipo RUANA te incorporará y podrás acceder al panel.",
            "http_status": 403,
        }

    if not aliado_tiene_pin(aliado):
        return {
            "ok": True,
            "pin_setup_required": True,
            "codigo": codigo,
            "setup_token": crear_setup_token(codigo),
        }

    if not pin:
        return {"ok": False, "message": GENERIC_CREDENTIALS_ERROR, "http_status": 401}

    if esta_bloqueado_por_pin(aliado):
        return {"ok": False, "message": GENERIC_CREDENTIALS_ERROR, "http_status": 401}

    if not verificar_pin(pin, aliado.get("pin_hash") or ""):
        _registrar_intento_pin_fallido(db, codigo)
        return {"ok": False, "message": GENERIC_CREDENTIALS_ERROR, "http_status": 401}

    _resetear_intentos_pin(db, codigo)
    return {"ok": True, "codigo": codigo}


def establecer_pin_inicial(db, setup_token: str, pin: str, pin_confirmacion: str) -> Dict[str, Any]:
    codigo = validar_setup_token(setup_token)
    if not codigo:
        return {"status": "error", "message": "La sesión de configuración ha expirado. Vuelve a iniciar sesión."}

    if not validar_formato_pin(pin):
        return {"status": "error", "message": "El PIN debe tener entre 4 y 6 dígitos numéricos."}
    if pin != (pin_confirmacion or "").strip():
        return {"status": "error", "message": "Los PIN no coinciden."}

    aliado = db.obtener_aliado_por_codigo(codigo)
    if not aliado:
        return {"status": "error", "message": GENERIC_CREDENTIALS_ERROR}

    if aliado_tiene_pin(aliado):
        return {"status": "error", "message": "Este aliado ya tiene un PIN configurado."}

    _asegurar_esquema_pin(db)

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            _repo.update_pin_hash(cursor, codigo, hash_pin(pin))
            _repo.reset_pin_intentos(cursor, codigo)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return {"status": "error", "message": str(exc)}
        finally:
            conn.close()

    return {"status": "success", "codigo": codigo, "message": "PIN configurado correctamente."}


def cambiar_pin(db, codigo: str, pin_actual: str, pin_nuevo: str, pin_confirmacion: str) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    if not validar_formato_pin(pin_nuevo):
        return {"status": "error", "message": "El nuevo PIN debe tener entre 4 y 6 dígitos numéricos."}
    if pin_nuevo != (pin_confirmacion or "").strip():
        return {"status": "error", "message": "El nuevo PIN y la confirmación no coinciden."}
    if pin_actual == pin_nuevo:
        return {"status": "error", "message": "El nuevo PIN debe ser distinto al actual."}

    aliado = db.obtener_aliado_por_codigo(codigo)
    if not aliado or not aliado_tiene_pin(aliado):
        return {"status": "error", "message": "No hay un PIN configurado para esta cuenta."}

    if esta_bloqueado_por_pin(aliado):
        return {"status": "error", "message": GENERIC_CREDENTIALS_ERROR}

    if not verificar_pin(pin_actual, aliado.get("pin_hash") or ""):
        _registrar_intento_pin_fallido(db, codigo)
        return {"status": "error", "message": "El PIN actual no es correcto."}

    _asegurar_esquema_pin(db)

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            _repo.update_pin_hash(cursor, codigo, hash_pin(pin_nuevo))
            _repo.reset_pin_intentos(cursor, codigo)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return {"status": "error", "message": str(exc)}
        finally:
            conn.close()

    return {"status": "success", "message": "PIN actualizado correctamente."}


def solicitar_recuperacion(
    db,
    *,
    tipo: str,
    email: Optional[str] = None,
    codigo: Optional[str] = None,
) -> Dict[str, Any]:
    tipo = (tipo or "").strip().lower()
    if tipo not in ("pin", "codigo", "ambos"):
        return {"status": "error", "message": "Tipo de recuperación no válido."}

    email_norm = _normalizar_email(email or "")
    codigo = (codigo or "").strip()

    if tipo == "pin":
        if not codigo:
            return {"status": "error", "message": "Introduce tu código de aliado."}
        aliado = db.obtener_aliado_por_codigo(codigo)
        if not aliado:
            return {"status": "success", "message": RECUPERACION_MENSAJE_GENERICO}
        email_norm = _normalizar_email(aliado.get("email") or "")
        if not email_norm:
            return {"status": "success", "message": RECUPERACION_MENSAJE_GENERICO}
    else:
        if not email_norm or "@" not in email_norm:
            return {"status": "error", "message": "Introduce un email válido."}
        with db._lock:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                row = _repo.select_aliado_por_email_ocupado(cursor, email_norm)
                aliado = dict(row) if row else None
            finally:
                conn.close()
        if not aliado:
            return {"status": "success", "message": RECUPERACION_MENSAJE_GENERICO}
        codigo = (aliado.get("codigo") or "").strip()

    otp = _generar_otp()
    salt = secrets.token_hex(16)
    expira = _ahora_utc() + timedelta(minutes=RECUPERACION_OTP_MINUTOS)

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            token_id = _repo.insert_recuperacion(
                cursor,
                email=email_norm,
                codigo_aliado=codigo,
                tipo=tipo,
                otp_hash=_hash_otp(otp, salt),
                otp_salt=salt,
                expira_en=expira.isoformat(),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            return {"status": "success", "message": RECUPERACION_MENSAJE_GENERICO}
        finally:
            conn.close()

    from core.email_service import enviar_correo_recuperacion_acceso

    enviar_correo_recuperacion_acceso(email_norm, tipo, otp, RECUPERACION_OTP_MINUTOS)
    return {
        "status": "success",
        "message": RECUPERACION_MENSAJE_GENERICO,
        "recovery_token": token_id,
    }


def verificar_recuperacion(db, recovery_token: int, codigo_temporal: str) -> Dict[str, Any]:
    fila = _obtener_recuperacion_activa(db, recovery_token)
    if not fila:
        return {"status": "error", "message": "Código de recuperación inválido o caducado."}

    if int(fila.get("intentos_fallidos") or 0) >= RECUPERACION_MAX_INTENTOS:
        return {"status": "error", "message": "Demasiados intentos. Solicita un nuevo código."}

    otp_hash = _hash_otp(codigo_temporal, fila.get("otp_salt") or "")
    if otp_hash != (fila.get("otp_hash") or ""):
        _incrementar_intento_recuperacion(db, recovery_token)
        return {"status": "error", "message": "Código de recuperación incorrecto."}

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            _repo.marcar_recuperacion_verificada(cursor, recovery_token)
            if (fila.get("tipo") or "").lower() == "codigo":
                _repo.marcar_recuperacion_usada(cursor, recovery_token)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return {"status": "error", "message": str(exc)}
        finally:
            conn.close()

    payload: Dict[str, Any] = {
        "status": "success",
        "message": "Identidad verificada.",
        "tipo": fila.get("tipo"),
        "recovery_token": recovery_token,
    }
    tipo = (fila.get("tipo") or "").lower()
    if tipo in ("codigo", "ambos"):
        payload["codigo"] = fila.get("codigo_aliado")
    if tipo == "ambos":
        payload["pin_setup_required"] = True
    return payload


def restablecer_pin_recuperacion(
    db,
    recovery_token: int,
    pin_nuevo: str,
    pin_confirmacion: str,
) -> Dict[str, Any]:
    fila = _obtener_recuperacion_verificada(db, recovery_token)
    if not fila:
        return {"status": "error", "message": "La verificación ha expirado. Solicita un nuevo código."}

    tipo = (fila.get("tipo") or "").lower()
    if tipo not in ("pin", "ambos"):
        return {"status": "error", "message": "Esta recuperación no permite restablecer el PIN."}

    if not validar_formato_pin(pin_nuevo):
        return {"status": "error", "message": "El PIN debe tener entre 4 y 6 dígitos numéricos."}
    if pin_nuevo != (pin_confirmacion or "").strip():
        return {"status": "error", "message": "Los PIN no coinciden."}

    codigo = (fila.get("codigo_aliado") or "").strip()
    if not codigo:
        return {"status": "error", "message": "No se pudo identificar la cuenta."}

    _asegurar_esquema_pin(db)

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            _repo.update_pin_hash(cursor, codigo, hash_pin(pin_nuevo))
            _repo.reset_pin_intentos(cursor, codigo)
            _repo.marcar_recuperacion_usada(cursor, recovery_token)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return {"status": "error", "message": str(exc)}
        finally:
            conn.close()

    return {"status": "success", "message": "PIN restablecido correctamente.", "codigo": codigo}


def _registrar_intento_pin_fallido(db, codigo: str) -> None:
    _asegurar_esquema_pin(db)
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            intentos = _repo.increment_pin_intentos(cursor, codigo)
            if intentos >= PIN_MAX_INTENTOS:
                bloqueado_hasta = (_ahora_utc() + timedelta(seconds=PIN_BLOQUEO_SEGUNDOS)).isoformat()
                _repo.set_pin_bloqueado_hasta(cursor, codigo, bloqueado_hasta)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()


def _resetear_intentos_pin(db, codigo: str) -> None:
    _asegurar_esquema_pin(db)
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            _repo.reset_pin_intentos(cursor, codigo)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()


def _obtener_recuperacion_activa(db, token_id: int) -> Optional[Dict[str, Any]]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            row = _repo.select_recuperacion_por_id(cursor, token_id)
            if not row:
                return None
            fila = dict(row)
            if fila.get("usado_en"):
                return None
            if not fila.get("verificado"):
                expira = fila.get("expira_en")
                if expira and _parse_iso(expira) < _ahora_utc():
                    return None
            return fila
        finally:
            conn.close()


def _obtener_recuperacion_verificada(db, token_id: int) -> Optional[Dict[str, Any]]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            row = _repo.select_recuperacion_por_id(cursor, token_id)
            if not row:
                return None
            fila = dict(row)
            if fila.get("usado_en"):
                return None
            if not fila.get("verificado"):
                return None
            expira = fila.get("expira_en")
            if expira and _parse_iso(expira) < _ahora_utc():
                return None
            return fila
        finally:
            conn.close()


def _incrementar_intento_recuperacion(db, token_id: int) -> None:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        try:
            _repo.increment_recuperacion_intentos(cursor, token_id)
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()


def _parse_iso(valor: str) -> datetime:
    texto = str(valor or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(texto)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
