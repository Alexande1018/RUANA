"""Servicio de dominio chat (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de chat vía ChatRepo.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.repositories.chat_repo import ChatRepo

_repo = ChatRepo()

# --- Extraído de DBManager (chat) ---

def listar_mensajes_soporte_aliado(db, conversacion_id: int, aliado_codigo: str) -> List[Dict[str, Any]]:
    codigo = str(aliado_codigo or '').strip()
    if not codigo:
        return []
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if not _repo.conversacion_soporte_visible_aliado(cursor, conversacion_id, codigo):
                return []
            return [dict(r) for r in _repo.listar_mensajes_soporte(cursor, conversacion_id)]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

def listar_mensajes_soporte_admin(db, conversacion_id: int) -> List[Dict[str, Any]]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(r) for r in _repo.listar_mensajes_soporte(cursor, conversacion_id)]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

def enviar_mensaje_soporte_aliado(db, conversacion_id: int, aliado_codigo: str, mensaje: str) -> Dict[str, Any]:
    codigo = str(aliado_codigo or '').strip()
    msg = str(mensaje or '').strip()
    if not codigo or not msg:
        return {'status': 'error', 'message': 'Datos incompletos'}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if _repo.select_id_conversacion_soporte_aliado(cursor, conversacion_id, codigo) is None:
                return {'status': 'error', 'message': 'Conversación no encontrada'}
            _repo.insertar_mensaje_soporte_aliado(cursor, conversacion_id, codigo, msg)
            _repo.update_conversacion_tras_mensaje_aliado(cursor, msg[:220], conversacion_id)
            conn.commit()
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def listar_mensajes_contacto(db, contacto_id: int) -> List[Dict[str, Any]]:
    """
    Lista TODOS los mensajes del chat interno RUANA para un contacto.
    No filtra por emisor_codigo ni receptor_codigo; devuelve la conversación completa.
    La validación de permisos (solo solicitante y profesional pueden ver) se realiza
    en la capa API antes de invocar este método.
    Campos devueltos: id, contacto_id, emisor_codigo, texto, creado_en.
    Orden: creado_en ASC.
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(row) for row in _repo.listar_mensajes_contacto(cursor, contacto_id)]
        except Exception as e:
            print(f"Error listar_mensajes_contacto: {e}")
            return []
        finally:
            conn.close()

def _chat_expiry_metadata(db, ref: Optional[datetime]) -> Dict[str, Any]:
    ref = db._parse_timestamp(ref)
    if not ref:
        return {
            'chat_referencia_en': None,
            'chat_expira_en': None,
            'chat_horas_restantes': db.CHAT_HORAS_VIGENCIA,
            'chat_horas_vigencia': db.CHAT_HORAS_VIGENCIA,
        }
    expira_en = ref + timedelta(hours=db.CHAT_HORAS_VIGENCIA)
    segundos_restantes = (expira_en - db._chat_now()).total_seconds()
    horas_restantes = max(0, int((segundos_restantes + 3599) // 3600))
    return {
        'chat_referencia_en': ref.isoformat(),
        'chat_expira_en': expira_en.isoformat(),
        'chat_horas_restantes': horas_restantes,
        'chat_horas_vigencia': db.CHAT_HORAS_VIGENCIA,
    }

def _chat_esta_expirado(db, ref: Optional[datetime]) -> bool:
    ref = db._parse_timestamp(ref)
    if not ref:
        return False
    return (db._chat_now() - ref).total_seconds() > db.CHAT_HORAS_VIGENCIA * 3600

def _chat_referencia_ts(db, cursor, contacto_id: int) -> Optional[datetime]:
    """
    Timestamp de referencia para vigencia del chat: última actividad.
    A) Si hay mensajes → último mensaje. B) Si no → fecha_aceptacion o creado_en del contacto.
    """
    ultimo_msg = _repo.max_creado_en_mensajes(cursor, contacto_id)
    if ultimo_msg:
        return db._parse_timestamp(ultimo_msg)
    row = _repo.select_fechas_contacto(cursor, contacto_id)
    if not row:
        return None
    fa, ce = row[0], row[1]
    dt_fa = db._parse_timestamp(fa)
    dt_ce = db._parse_timestamp(ce)
    if dt_fa and dt_ce:
        return max(dt_fa, dt_ce)
    return dt_fa or dt_ce

def estado_chat_contacto(db, contacto_id: int, codigo: str) -> Dict[str, Any]:
    """Devuelve chat_expirado (bool) y mensajes_restantes (int). Vigencia 48h desde última actividad.
    También se considera expirado si el contacto está en estado final (p. ej. trabajo_cerrado cuando
    las dos partes confirmaron el valor y se envió la alerta de pago)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_id_estado(cursor, contacto_id)
            if not row:
                return db._chat_estado_cerrado()
            estado = (row[1] or '').strip()
            if estado in db._ESTADOS_FINALES_CONTACTO:
                return db._chat_estado_cerrado()
            ref = db._parse_timestamp(db._chat_referencia_ts(cursor, contacto_id))
            expirado = db._chat_esta_expirado(ref)
            count = _repo.contar_mensajes(cursor, contacto_id)
            restantes = max(0, db.CHAT_MAX_MENSAJES_TOTAL - count)
            estado_chat = {
                'chat_expirado': expirado,
                'mensajes_restantes': restantes,
                'chat_max_mensajes': db.CHAT_MAX_MENSAJES_TOTAL,
            }
            estado_chat.update(db._chat_expiry_metadata(ref))
            if expirado:
                estado_chat['mensajes_restantes'] = 0
                estado_chat['chat_horas_restantes'] = 0
            return estado_chat
        except Exception as e:
            print(f"Error estado_chat_contacto: {e}")
            estado_chat = {
                'chat_expirado': False,
                'mensajes_restantes': db.CHAT_MAX_MENSAJES_TOTAL,
                'chat_max_mensajes': db.CHAT_MAX_MENSAJES_TOTAL,
            }
            estado_chat.update(db._chat_expiry_metadata(None))
            return estado_chat
        finally:
            conn.close()

def enviar_mensaje_chat(db, contacto_id: int, emisor_codigo: str, texto: str) -> Dict[str, Any]:
    """
    Envía un mensaje al chat interno RUANA. Confiable y bilateral: emisor y receptor
    lo ven inmediatamente vía GET /api/chat_mensajes (listar_mensajes_contacto devuelve todos).
    Limites: 30 mensajes totales por conversacion, 48h de vigencia desde ultima actividad.
    """
    # --- Validación previa: texto no vacío ---
    texto_clean = (texto or "").strip()
    if not texto_clean:
        return {'status': 'error', 'message': 'El mensaje no puede estar vacío'}

    emisor_norm = str(emisor_codigo or "").strip()
    if not emisor_norm:
        return {'status': 'error', 'message': 'emisor_codigo es obligatorio'}

    resultado: Dict[str, Any] = {'status': 'error', 'message': 'unknown'}
    profesional_para_regla5: Optional[str] = None
    codigo_penal_agotado: Optional[str] = None
    contacto_penal_agotado: Optional[int] = None

    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # --- 1. Validar que el contacto existe ---
            row = _repo.select_contacto_chat(cursor, contacto_id)
            if not row:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            contacto = dict(row)

            # --- 2. Validar que emisor es solicitante o profesional (normalizar tipos) ---
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            if emisor_norm not in (sol, pro):
                return {'status': 'error', 'message': 'No tienes permiso para escribir en este chat'}

            # --- 3. Validar que el contacto NO está en estado final ---
            estado = (contacto.get('estado') or '').strip()
            if estado in db._ESTADOS_FINALES_CONTACTO:
                return {'status': 'error', 'message': 'Contacto cerrado; no se pueden enviar más mensajes.'}

            # --- 4. Validar vigencia: no expirado (48h desde último mensaje o aceptación/creación) ---
            ref = db._parse_timestamp(db._chat_referencia_ts(cursor, contacto_id))
            if db._chat_esta_expirado(ref):
                return {
                    'status': 'error',
                    'message': 'Este chat ha expirado (48h desde la última actividad). Cierra el contacto desde el panel para resolver.'
                }

            # --- 5. Validar que el chat no supera el limite total de mensajes ---
            count_total = _repo.contar_mensajes(cursor, contacto_id)
            if count_total >= db.CHAT_MAX_MENSAJES_TOTAL:
                return {
                    'status': 'error',
                    'message': 'Este chat ha llegado al limite de 30 mensajes. Usa el panel para cerrar el contacto o resolverlo.'
                }

            # --- 6. Inserción: guardar mensaje (visible para ambos aliados vía listar_mensajes_contacto) ---
            receptor_codigo = pro if emisor_norm == sol else sol
            cols_msg = _repo.columnas_chat_mensajes(cursor)
            if 'receptor_codigo' in cols_msg:
                msg_id = _repo.insertar_mensaje_con_receptor(
                    cursor, contacto_id, emisor_norm, receptor_codigo, texto_clean
                )
            else:
                msg_id = _repo.insertar_mensaje_sin_receptor(
                    cursor, contacto_id, emisor_norm, texto_clean
                )

            # --- 7. Actualizacion de estado: si el chat llega al limite total -> chat_agotado ---
            chat_agotado_ahora = False
            if count_total + 1 >= db.CHAT_MAX_MENSAJES_TOTAL:
                chat_agotado_ahora = _repo.update_contacto_chat_agotado(cursor, contacto_id) > 0

            conn.commit()

            # --- 8. Retorno: mensaje insertado (ambos aliados lo verán en GET /api/chat_mensajes) ---
            msg_row = _repo.select_mensaje_por_id(cursor, msg_id)
            resultado = {'status': 'success', 'mensaje': dict(msg_row)}
            # Regla 5 solo si quien escribe es el profesional
            if emisor_norm == pro:
                profesional_para_regla5 = pro
            # Penalización 7: quien agota el chat (mensaje 30) sin resultado declarado → -2
            if chat_agotado_ahora:
                codigo_penal_agotado = emisor_norm
                contacto_penal_agotado = int(contacto_id)
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

    if profesional_para_regla5:
        try:
            hito = db.evaluar_regla5_respuestas_chat(profesional_para_regla5)
            if hito:
                db.aplicar_cambio_score(hito[0], hito[1], hito[2])
        except Exception:
            pass
    if codigo_penal_agotado and contacto_penal_agotado:
        try:
            db.aplicar_penalizacion_chat_agotado_sin_resultado(
                contacto_penal_agotado, codigo_penal_agotado
            )
        except Exception:
            pass
    return resultado

def listar_contactos_recientes_con_chat(db, limite: int = 100) -> List[Dict[str, Any]]:
    """Lista contactos recientes con número de mensajes y fecha del último mensaje (para admin)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cols = _repo.columnas_contactos_ruana(cursor)
            motivo_col = 'c.motivo_contacto, ' if 'motivo_contacto' in cols else ''
            urgente_col = 'COALESCE(c.es_urgente, 0) AS es_urgente, c.urgente_marcado_en, ' if 'es_urgente' in cols else ''
            lista = [dict(row) for row in _repo.listar_contactos_recientes_con_chat(
                cursor, motivo_col, urgente_col, limite
            )]
            for d in lista:
                if 'es_urgente' in d:
                    d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
            return lista
        except Exception as e:
            print(f"Error listar_contactos_recientes_con_chat: {e}")
            return []
        finally:
            conn.close()

def listar_chat_messages(db, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Lista mensajes de chat para admin. Un solo source of truth: chat_mensajes + JOIN aliados."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(row) for row in _repo.listar_chat_messages_admin(cursor, limit, offset)]
        except Exception as e:
            print(f"Error listar_chat_messages: {e}")
            return []
        finally:
            conn.close()

