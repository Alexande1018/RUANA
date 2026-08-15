"""Servicio de dominio negociacion (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de negociación vía NegociacionRepo (negociacion_manager permanece aparte).
"""
from __future__ import annotations
import re


from datetime import datetime, timedelta

import json
import sqlite3
from typing import Any, Dict, List, Optional

from core import negociacion_manager as neg_mgr
from core.repositories.negociacion_repo import NegociacionRepo

_repo = NegociacionRepo()

# --- Extraído de DBManager (negociacion) ---

def _iniciar_negociacion_en_cursor(db, cursor, contacto_id: int, servicio: str,
                                    solicitante_codigo: str, precio_referencia: str = '') -> None:
    estado = neg_mgr.estado_inicial(precio_referencia=precio_referencia)
    neg_json = neg_mgr.serializar_negociacion(estado)
    _repo.update_negociacion_json(cursor, neg_json, contacto_id)

def _insertar_evento_negociacion(db, cursor, contacto_id: int, tipo: str, campo: str,
                                  valor: str, emisor_codigo: str, mensaje: str) -> None:
    _repo.insertar_evento(
        cursor, contacto_id, tipo, campo, valor, emisor_codigo, mensaje
    )

def _cargar_contacto_negociacion(db, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
    row = _repo.select_contacto(cursor, contacto_id)
    return dict(row) if row else None

def listar_eventos_negociacion(db, contacto_id: int) -> List[Dict[str, Any]]:
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(r) for r in _repo.listar_eventos(cursor, contacto_id)]
        except Exception as e:
            print(f"Error listar_eventos_negociacion: {e}")
            return []
        finally:
            conn.close()

def obtener_negociacion_contacto(db, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
    codigo = (codigo_aliado or '').strip()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            rol = neg_mgr._rol_en_contacto(codigo, sol, pro)
            if not rol:
                return {'status': 'error', 'message': 'No autorizado'}
            eventos = db.listar_eventos_negociacion(contacto_id)
            payload = neg_mgr.construir_payload(contacto, eventos, rol)
            return {'status': 'success', **payload}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def proponer_negociacion(db, contacto_id: int, codigo_aliado: str,
                         campo: str, valor: str) -> Dict[str, Any]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            if contacto.get('estado') in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado', 'acuerdo_alcanzado'):
                return {'status': 'error', 'message': 'Este contacto ya no admite cambios en la negociación'}
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
            if not rol:
                return {'status': 'error', 'message': 'No autorizado'}
            estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
            estado, msg, tipo = neg_mgr.proponer_campo(estado, rol, campo, valor)
            neg_json = neg_mgr.serializar_negociacion(estado)
            _repo.update_negociacion_json(cursor, neg_json, contacto_id)
            db._insertar_evento_negociacion(cursor, contacto_id, tipo, campo, valor, codigo_aliado, msg)
            conn.commit()
            eventos = db.listar_eventos_negociacion(contacto_id)
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            payload = neg_mgr.construir_payload(contacto, eventos, rol)
            return {'status': 'success', 'message': msg, **payload}
        except ValueError as ve:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(ve)}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def proponer_propuesta_completa_negociacion(db, contacto_id: int, codigo_aliado: str, valores: Dict[str, str],
    precio_catalogo: str = '',
) -> Dict[str, Any]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            if contacto.get('estado') in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado', 'acuerdo_alcanzado'):
                return {'status': 'error', 'message': 'Este contacto ya no admite cambios en la negociación'}
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
            if not rol:
                return {'status': 'error', 'message': 'No autorizado'}
            estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
            estado, msg_resumen, eventos = neg_mgr.proponer_propuesta_completa(
                estado, rol, valores, precio_referencia=precio_catalogo or '',
            )
            neg_json = neg_mgr.serializar_negociacion(estado)
            _repo.update_negociacion_json(cursor, neg_json, contacto_id)
            db._insertar_evento_negociacion(
                cursor, contacto_id, neg_mgr.TIPO_SISTEMA, None, None, codigo_aliado, msg_resumen,
            )
            for campo, valor, msg in eventos:
                db._insertar_evento_negociacion(
                    cursor, contacto_id, neg_mgr.TIPO_PROPUESTA, campo, valor, codigo_aliado, msg,
                )
            conn.commit()
            eventos_list = db.listar_eventos_negociacion(contacto_id)
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            payload = neg_mgr.construir_payload(contacto, eventos_list, rol)
            return {'status': 'success', 'message': msg_resumen, **payload}
        except ValueError as ve:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(ve)}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def contraoferta_negociacion(db, contacto_id: int, codigo_aliado: str,
                              campo: str, valor: str, renegociar: bool = False) -> Dict[str, Any]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            if contacto.get('estado') in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado'):
                return {'status': 'error', 'message': 'Este contacto ya está cerrado'}
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
            if not rol:
                return {'status': 'error', 'message': 'No autorizado'}
            estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
            if renegociar:
                estado, msg = neg_mgr.reabrir_campo_negociacion(estado, rol, campo, valor)
                tipo = neg_mgr.TIPO_CONTRAOFERTA
            else:
                estado, msg, tipo = neg_mgr.contraoferta_campo(estado, rol, campo, valor)
            neg_json = neg_mgr.serializar_negociacion(estado)
            nuevo_estado_contacto = contacto.get('estado')
            if contacto.get('estado') == 'acuerdo_alcanzado':
                nuevo_estado_contacto = 'iniciado'
            _repo.update_negociacion_json_y_estado(
                cursor, neg_json, nuevo_estado_contacto, contacto_id
            )
            db._insertar_evento_negociacion(cursor, contacto_id, tipo, campo, valor, codigo_aliado, msg)
            conn.commit()
            eventos = db.listar_eventos_negociacion(contacto_id)
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            payload = neg_mgr.construir_payload(contacto, eventos, rol)
            return {'status': 'success', 'message': msg, **payload}
        except ValueError as ve:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(ve)}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def _precio_valor_desde_contacto(db, contacto: Dict[str, Any]) -> Any:
    """Obtiene el valor de precio desde columnas/snapshot/negociacion_json."""
    if contacto.get('importe_acordado') is not None:
        try:
            return float(contacto.get('importe_acordado'))
        except (TypeError, ValueError):
            pass
    resumen = db._parse_acuerdo_resumen_campo(contacto.get('acuerdo_resumen_json')) or {}
    campos = resumen.get('campos') or {}
    if campos.get('precio') is not None:
        return campos.get('precio')
    estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
    try:
        return estado['campos']['precio']['valor']
    except Exception:
        return None

def _construir_acuerdo_resumen_json(db,
    estado: Dict[str, Any],
    contacto: Dict[str, Any],
) -> str:
    """Snapshot inmutable del acuerdo para historial «Mis acuerdos»."""
    campos_valores = {}
    for c in neg_mgr.CAMPOS_ORDEN:
        campos_valores[c] = (estado.get('campos') or {}).get(c, {}).get('valor')
    payload = {
        'contacto_id': contacto.get('id'),
        'solicitante_codigo': str(contacto.get('solicitante_codigo') or '').strip(),
        'profesional_codigo': str(contacto.get('profesional_codigo') or '').strip(),
        'servicio_contacto': (contacto.get('servicio') or '').strip(),
        'campos': campos_valores,
        'resumen': neg_mgr.resumen_acuerdo(estado),
    }
    return json.dumps(payload, ensure_ascii=False)

def aceptar_negociacion(db, contacto_id: int, codigo_aliado: str, campo: str,
                        observaciones_profesional: str = '') -> Dict[str, Any]:
    completo = False
    payload = None
    solicitante_codigo = ''
    precio_para_cierre = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
            if not rol:
                return {'status': 'error', 'message': 'No autorizado'}
            estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
            estado, msg, tipo, completo, eventos_extra = neg_mgr.aceptar_campo(
                estado, rol, campo, observaciones_profesional
            )
            neg_json = neg_mgr.serializar_negociacion(estado)
            nuevo_estado = contacto.get('estado') or 'iniciado'
            resumen_json = None
            solicitante_codigo = sol
            if completo:
                nuevo_estado = 'acuerdo_alcanzado'
                resumen_json = db._construir_acuerdo_resumen_json(estado, contacto)
                _repo.set_fecha_trabajo_en_progreso_si_null(cursor, contacto_id)
                msg_sistema = (
                    'Acuerdo alcanzado. El precio aceptado es el importe oficial del encargo '
                    'y se genera el Apoyo RUANA. Resumen: '
                    + ', '.join(
                        f"{neg_mgr.CAMPOS_LABELS[c]}: {estado['campos'][c]['valor']}"
                        for c in neg_mgr.CAMPOS_ORDEN
                    )
                )
                db._insertar_evento_negociacion(
                    cursor, contacto_id, neg_mgr.TIPO_SISTEMA, None, '', None, msg_sistema
                )
            if completo and resumen_json is not None:
                try:
                    precio_raw = estado['campos']['precio']['valor']
                except Exception:
                    precio_raw = None
                importe_oficial = db._parse_importe_acuerdo(precio_raw)
                precio_para_cierre = precio_raw if precio_raw is not None else importe_oficial
                _repo.update_acuerdo_completo(
                    cursor, neg_json, nuevo_estado, resumen_json, importe_oficial, contacto_id
                )
            else:
                _repo.update_negociacion_json_y_estado(
                    cursor, neg_json, nuevo_estado, contacto_id
                )
            db._insertar_evento_negociacion(cursor, contacto_id, tipo, campo,
                estado['campos'][campo]['valor'], codigo_aliado, msg)
            for ev_campo, ev_valor, ev_msg, ev_tipo in eventos_extra:
                db._insertar_evento_negociacion(
                    cursor, contacto_id, ev_tipo, ev_campo, ev_valor, pro if ev_campo == 'precio' else codigo_aliado, ev_msg,
                )
            conn.commit()
            eventos = db.listar_eventos_negociacion(contacto_id)
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            payload = neg_mgr.construir_payload(contacto, eventos, rol)
            payload = {'status': 'success', 'message': msg, 'completo': completo, **payload}
            if contacto.get('importe_acordado') is not None:
                try:
                    payload['importe_acordado'] = float(contacto['importe_acordado'])
                except (TypeError, ValueError):
                    pass
        except ValueError as ve:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(ve)}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

    # Fuera del lock: el precio aceptado cierra el encargo y genera Apoyo RUANA (sin confirmación extra).
    if completo and payload and payload.get('status') == 'success':
        return db._cerrar_encargo_tras_acuerdo(
            contacto_id,
            solicitante_codigo or '',
            precio_para_cierre,
            codigo_aliado,
            'Acuerdo alcanzado. Precio aceptado como importe oficial.',
            payload,
        )
    return payload if payload else {'status': 'error', 'message': 'No se pudo aceptar el punto'}

def cerrar_negociacion(db, contacto_id: int, actor_codigo: str,
                       motivo: str = '') -> Dict[str, Any]:
    """
    Cierra la negociación:
    - Si hay acuerdo / trabajo ya cerrado por precio aceptado: confirma el cierre por esta parte
      (bilateral, solo acuse de recibo del resumen).
    - Si aún no hay acuerdo: finaliza como no concretado.
    """
    codigo = (actor_codigo or '').strip()
    sol = pro = None
    need_trabajo = False
    precio_valor = None
    mensaje_cierre = ''
    payload_base = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            rol = neg_mgr._rol_en_contacto(codigo, sol, pro)
            if not rol:
                return {'status': 'error', 'message': 'No autorizado'}
            estado_actual = (contacto.get('estado') or '').strip()

            # Ya cerrado por cobro automático tras aceptar precio: solo acuse bilateral del resumen
            if estado_actual == 'trabajo_cerrado' and (
                contacto.get('acuerdo_resumen_json') or contacto.get('importe_acordado') is not None
            ):
                col = (
                    'cierre_confirmado_solicitante_en'
                    if rol == 'solicitante'
                    else 'cierre_confirmado_profesional_en'
                )
                if not contacto.get(col):
                    _repo.set_timestamp_col(cursor, col, contacto_id)
                    conn.commit()
                contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
                eventos = db.listar_eventos_negociacion(contacto_id)
                payload = neg_mgr.construir_payload(contacto, eventos, rol)
                return {
                    'status': 'success',
                    'message': 'El encargo ya está cerrado con el precio acordado.',
                    'completo': True,
                    'cierre_automatico': True,
                    **payload,
                }

            if estado_actual in db._ESTADOS_FINALES_CONTACTO:
                return {
                    'status': 'error',
                    'message': f'El contacto ya está cerrado ({estado_actual}).',
                }

            # --- Confirmación bilateral tras acuerdo (si aún no se aplicó cobro) ---
            if estado_actual == 'acuerdo_alcanzado' or (
                neg_mgr.parse_negociacion(contacto.get('negociacion_json')).get('completo')
                and estado_actual not in ('cerrado_no_concretado', 'no_concretado')
            ):
                if estado_actual != 'acuerdo_alcanzado':
                    _repo.marcar_acuerdo_alcanzado(cursor, contacto_id)
                    estado_actual = 'acuerdo_alcanzado'

                col = (
                    'cierre_confirmado_solicitante_en'
                    if rol == 'solicitante'
                    else 'cierre_confirmado_profesional_en'
                )
                ya = bool(contacto.get(col))
                if not ya:
                    _repo.set_timestamp_col(cursor, col, contacto_id)
                    quien = 'contratante' if rol == 'solicitante' else 'profesional'
                    msg_evento = (
                        f'El {quien} ha cerrado la negociación y confirma el acuerdo. '
                        'Pendiente la confirmación de la otra parte.'
                    )
                    db._insertar_evento_negociacion(
                        cursor, contacto_id, neg_mgr.TIPO_SISTEMA, None, None, codigo, msg_evento,
                    )
                    if not contacto.get('acuerdo_resumen_json'):
                        estado_neg = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
                        resumen_json = db._construir_acuerdo_resumen_json(estado_neg, contacto)
                        _repo.set_acuerdo_resumen_si_vacio(cursor, resumen_json, contacto_id)

                conn.commit()
                contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
                eventos = db.listar_eventos_negociacion(contacto_id)
                payload_base = neg_mgr.construir_payload(contacto, eventos, rol)
                payload_base = {
                    'status': 'success',
                    'message': 'Has confirmado el acuerdo. Esperando a la otra parte.'
                    if not (
                        contacto.get('cierre_confirmado_solicitante_en')
                        and contacto.get('cierre_confirmado_profesional_en')
                    )
                    else 'Ambas partes confirmaron el acuerdo.',
                    'completo': True,
                    **payload_base,
                }
                conf_sol = bool(contacto.get('cierre_confirmado_solicitante_en'))
                conf_pro = bool(contacto.get('cierre_confirmado_profesional_en'))
                if conf_sol and conf_pro:
                    need_trabajo = True
                    estado_neg = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
                    try:
                        precio_valor = estado_neg['campos']['precio']['valor']
                    except Exception:
                        precio_valor = None
                    mensaje_cierre = 'Ambas partes confirmaron el acuerdo.'
                else:
                    return payload_base

            else:
                # --- Abandono sin acuerdo ---
                quien = 'contratante' if rol == 'solicitante' else 'profesional'
                msg_evento = (
                    f'La negociación ha sido cerrada por el {quien}. '
                    'El contacto queda finalizado sin acuerdo.'
                )
                db._insertar_evento_negociacion(
                    cursor, contacto_id, neg_mgr.TIPO_SISTEMA, None, None, codigo, msg_evento,
                )
                _repo.marcar_cerrado_no_concretado(cursor, contacto_id)
                detalles = f'aliados={sol},{pro} motivo={motivo or "cerrar_negociacion"} actor={codigo}'
                db._audit_log(cursor, 'contacto', contacto_id, 'cerrar_negociacion',
                                'aliado', codigo, detalles)
                conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

    if need_trabajo and payload_base is not None:
        return db._cerrar_encargo_tras_acuerdo(
            contacto_id,
            sol or '',
            precio_valor,
            codigo,
            mensaje_cierre,
            payload_base,
        )

    if sol:
        db.aplicar_cambio_score(sol, -1, 'contacto_cerrado_no_concretado')
    if pro:
        db.aplicar_cambio_score(pro, -1, 'contacto_cerrado_no_concretado')
    return {'status': 'success', 'id': contacto_id, 'estado': 'cerrado_no_concretado'}

def dismiss_resumen_acuerdo(db, contacto_id: int, actor_codigo: str) -> Dict[str, Any]:
    """El aliado oculta el panel flotante del resumen hasta nueva acción."""
    codigo = (actor_codigo or '').strip()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = db._cargar_contacto_negociacion(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            rol = neg_mgr._rol_en_contacto(codigo, sol, pro)
            if not rol:
                return {'status': 'error', 'message': 'No autorizado'}
            col = (
                'resumen_dismiss_solicitante_en'
                if rol == 'solicitante'
                else 'resumen_dismiss_profesional_en'
            )
            _repo.set_timestamp_col(cursor, col, contacto_id)
            conn.commit()
            return {'status': 'success', 'id': contacto_id, 'dismissed': True}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def listar_negociaciones_admin(db, limite: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_admin(cursor, limite, offset)
            result = []
            for row in rows:
                d = dict(row)
                neg = neg_mgr.parse_negociacion(d.get('negociacion_json'))
                d['paso_actual'] = neg.get('paso_actual')
                d['acuerdo_completo'] = bool(neg.get('completo')) or d.get('estado') == 'acuerdo_alcanzado'
                d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                precio = neg.get('campos', {}).get('precio', {}).get('valor') or ''
                d['precio_acordado'] = precio
                result.append(d)
            return result
        except Exception as e:
            print(f"Error listar_negociaciones_admin: {e}")
            return []
        finally:
            conn.close()

def eliminar_negociacion_admin(db, contacto_id: int, admin_codigo: str = '') -> Dict[str, Any]:
    """Elimina contacto y toda su negociación (solo admin)."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if not _repo.existe_contacto(cursor, contacto_id):
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            for tabla in (
                'negociacion_eventos', 'chat_mensajes', 'confirmaciones_trabajo',
                'contacto_panel_oculto', 'contacto_penalizaciones_aplicadas',
                'chat_mensajes', 'ingresos_ruana', 'payment_conflicts',
            ):
                try:
                    _repo.delete_relacionados_por_contacto(cursor, tabla, contacto_id)
                except Exception:
                    pass
            try:
                _repo.delete_notificaciones_contacto(cursor, contacto_id)
            except Exception:
                pass
            _repo.delete_contacto(cursor, contacto_id)
            db._audit_log(cursor, 'contacto', contacto_id, 'negociacion_eliminada_admin',
                            'admin', admin_codigo or '', f'contacto_id={contacto_id}')
            conn.commit()
            return {'status': 'success', 'message': 'Negociación eliminada', 'contacto_id': contacto_id}
        except Exception as e:
            if conn:
                conn.rollback()
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()
# --- Extraído de DBManager (negociacion) ---

def _cerrar_encargo_tras_acuerdo(db,
    contacto_id: int,
    solicitante_codigo: str,
    precio_valor: Any,
    codigo_viewer: str,
    mensaje_acuerdo: str,
    payload_base: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Tras confirmación bilateral del acuerdo, aplica la misma lógica que «Sí hubo trabajo»
    usando el importe oficial negociado (sin reingreso manual).
    """
    contacto = db.obtener_contacto_por_id(contacto_id) or {}
    importe = db._importe_oficial_contacto(contacto)
    if importe is None:
        importe = db._parse_importe_acuerdo(precio_valor)
    if importe is None:
        out = dict(payload_base)
        out['cierre_automatico'] = False
        out['cierre_aviso'] = (
            'Acuerdo alcanzado, pero no hay un precio numérico oficial. '
            'Revisa el precio en la negociación.'
        )
        return out

    from core.services import pago_service
    if pago_service.puede_usar_stripe_para_contacto(db, contacto):
        stripe_res = pago_service.activar_pago_stripe_tras_acuerdo(
            db,
            contacto_id,
            (solicitante_codigo or '').strip(),
            float(importe),
        )
        if stripe_res.get('status') == 'success':
            refreshed = db.obtener_negociacion_contacto(contacto_id, codigo_viewer)
            if refreshed.get('status') == 'success':
                refreshed['completo'] = True
                refreshed['cierre_automatico'] = True
                refreshed['modo_pago'] = 'stripe'
                refreshed['message'] = (
                    (mensaje_acuerdo or 'Acuerdo alcanzado.')
                    + ' Precio congelado. El contratante puede pagar con Stripe.'
                )
                refreshed['estado_cierre'] = stripe_res.get('estado')
                refreshed['estado_pago'] = stripe_res.get('estado_pago')
                refreshed['importe_acordado'] = stripe_res.get('importe_acordado')
                return refreshed
            out = dict(payload_base)
            out['cierre_automatico'] = True
            out['modo_pago'] = 'stripe'
            out['estado_contacto'] = stripe_res.get('estado')
            out['estado_cierre'] = stripe_res.get('estado')
            out['estado_pago'] = stripe_res.get('estado_pago')
            out['importe_acordado'] = stripe_res.get('importe_acordado')
            return out

    cierre = db.registrar_importe_contacto(
        contacto_id,
        'solicitante',
        importe,
        'EUR',
        usuario=(solicitante_codigo or '').strip(),
        usar_precio_acordado=True,
    )
    if not cierre or cierre.get('status') != 'success':
        out = dict(payload_base)
        out['cierre_automatico'] = False
        out['cierre_aviso'] = (cierre or {}).get('message') or (
            'Acuerdo alcanzado. No se pudo registrar el cobro del Apoyo RUANA con el precio aceptado.'
        )
        return out

    refreshed = db.obtener_negociacion_contacto(contacto_id, codigo_viewer)
    if refreshed.get('status') == 'success':
        refreshed['completo'] = True
        refreshed['cierre_automatico'] = True
        refreshed['message'] = (
            (mensaje_acuerdo or 'Acuerdo alcanzado.')
            + ' Precio aceptado como importe oficial; se genera el Apoyo RUANA.'
        )
        refreshed['estado_cierre'] = cierre.get('estado')
        if cierre.get('importe_acordado') is not None:
            refreshed['importe_acordado'] = cierre.get('importe_acordado')
        return refreshed

    out = dict(payload_base)
    out['cierre_automatico'] = True
    out['estado_contacto'] = cierre.get('estado') or 'trabajo_cerrado'
    out['estado_cierre'] = cierre.get('estado')
    return out

def listar_acuerdos_aliado(db,
    codigo_aliado: str,
    limite: int = 100,
    estado: Optional[str] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    rol: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Historial «Mis acuerdos»: todos los contactos del aliado, cualquier estado.

    Orden por defecto: más reciente → más antiguo (fecha de acuerdo, cierre,
    actualización o creación). Filtros opcionales: estado, rango de fechas y rol.
    """
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return []
    limite = max(1, min(int(limite or 100), 200))
    estado_f = (estado or '').strip()
    rol_f = (rol or '').strip().lower()
    if rol_f not in ('', 'todos', 'contrate', 'contratado'):
        rol_f = ''
    desde_f = (desde or '').strip()[:10]
    hasta_f = (hasta or '').strip()[:10]
    # Validar formato YYYY-MM-DD de forma laxa
    def _fecha_ok(v: str) -> bool:
        if not v or len(v) < 10:
            return False
        try:
            datetime.strptime(v[:10], '%Y-%m-%d')
            return True
        except ValueError:
            return False

    if not _fecha_ok(desde_f):
        desde_f = ''
    if not _fecha_ok(hasta_f):
        hasta_f = ''

    fecha_ref_sql = (
        "COALESCE(acuerdo_alcanzado_en, fecha_cierre, actualizado_en, creado_en)"
    )
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            where = [
                "(TRIM(CAST(solicitante_codigo AS TEXT)) = ?"
                " OR TRIM(CAST(profesional_codigo AS TEXT)) = ?)"
            ]
            params: List[Any] = [codigo, codigo]

            if rol_f == 'contrate':
                where.append("TRIM(CAST(solicitante_codigo AS TEXT)) = ?")
                params.append(codigo)
            elif rol_f == 'contratado':
                where.append("TRIM(CAST(profesional_codigo AS TEXT)) = ?")
                params.append(codigo)

            if estado_f:
                where.append("estado = ?")
                params.append(estado_f)

            if desde_f:
                where.append(f"date({fecha_ref_sql}) >= date(?)")
                params.append(desde_f)
            if hasta_f:
                where.append(f"date({fecha_ref_sql}) <= date(?)")
                params.append(hasta_f)

            params.append(limite)
            rows = _repo.listar_acuerdos_aliado(cursor, ' AND '.join(where), params)
            out = []
            for row in rows:
                d = dict(row)
                sol = str(d.get('solicitante_codigo') or '').strip()
                est = (d.get('estado') or '').strip()
                rol_item = 'contrate' if sol == codigo else 'contratado'
                resumen = db._parse_acuerdo_resumen_campo(d.get('acuerdo_resumen_json')) or {}
                out.append({
                    'contacto_id': d.get('id'),
                    'rol': rol_item,
                    'rol_label': 'Contrataste' if rol_item == 'contrate' else 'Te contrataron',
                    'estado': est,
                    'estado_label': db.CONTACTO_ESTADO_LABELS.get(est, est or 'Sin estado'),
                    'servicio': (
                        resumen.get('servicio_contacto')
                        or d.get('servicio')
                        or ''
                    ).strip(),
                    'contraparte_codigo': (
                        str(d.get('profesional_codigo') or '').strip()
                        if rol_item == 'contrate'
                        else sol
                    ),
                    'campos': resumen.get('campos') or {},
                    'resumen': resumen.get('resumen') or [],
                    'acuerdo_alcanzado_en': d.get('acuerdo_alcanzado_en'),
                    'fecha_cierre': d.get('fecha_cierre'),
                    'fecha_referencia': d.get('fecha_referencia') or d.get('creado_en'),
                    'creado_en': d.get('creado_en'),
                    'actualizado_en': d.get('actualizado_en'),
                    'importe_final': d.get('importe_final'),
                    'tiene_resumen_acuerdo': bool(resumen),
                    'ambos_confirmaron_cierre': bool(
                        d.get('cierre_confirmado_solicitante_en')
                        and d.get('cierre_confirmado_profesional_en')
                    ),
                })
            return out
        except Exception as e:
            print(f"Error listar_acuerdos_aliado: {e}")
            return []
        finally:
            if conn:
                conn.close()

def listar_resumenes_acuerdo_visibles(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """Acuerdos cuyo resumen flotante aún no ha descartado este aliado."""
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return []
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_resumenes_visibles(cursor, codigo)
            out = []
            for row in rows:
                d = dict(row)
                sol = str(d.get('solicitante_codigo') or '').strip()
                pro = str(d.get('profesional_codigo') or '').strip()
                rol = 'solicitante' if sol == codigo else 'profesional'
                resumen = db._parse_acuerdo_resumen_campo(d.get('acuerdo_resumen_json')) or {}
                flags = db._flags_cierre_acuerdo(d, rol)
                out.append({
                    'contacto_id': d.get('id'),
                    'estado': d.get('estado'),
                    'rol': rol,
                    'servicio': (resumen.get('servicio_contacto') or d.get('servicio') or '').strip(),
                    'resumen': resumen.get('resumen') or [],
                    'campos': resumen.get('campos') or {},
                    'acuerdo_alcanzado_en': d.get('acuerdo_alcanzado_en'),
                    'contraparte_codigo': pro if rol == 'solicitante' else sol,
                    **flags,
                })
            return out
        except Exception as e:
            print(f"Error listar_resumenes_acuerdo_visibles: {e}")
            return []
        finally:
            if conn:
                conn.close()


def _parse_importe_acuerdo(db, valor: Any) -> Optional[float]:
    """Extrae un importe numérico > 0 del valor acordado en negociación (p. ej. «150», «150€»)."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor) if float(valor) > 0 else None
    texto = str(valor).strip()
    if not texto:
        return None
    texto = texto.replace(',', '.').replace('€', ' ').replace('EUR', ' ').replace('eur', ' ')
    match = re.search(r'(\d+(?:\.\d+)?)', texto)
    if not match:
        return None
    try:
        importe = float(match.group(1))
    except (TypeError, ValueError):
        return None
    return importe if importe > 0 else None


def _flags_cierre_acuerdo(db, contacto: Dict[str, Any], rol: str) -> Dict[str, Any]:
    conf_sol = bool(contacto.get('cierre_confirmado_solicitante_en'))
    conf_pro = bool(contacto.get('cierre_confirmado_profesional_en'))
    yo = conf_sol if rol == 'solicitante' else conf_pro
    dismiss = bool(
        contacto.get('resumen_dismiss_solicitante_en')
        if rol == 'solicitante'
        else contacto.get('resumen_dismiss_profesional_en')
    )
    return {
        'cierre_confirmado_solicitante': conf_sol,
        'cierre_confirmado_profesional': conf_pro,
        'yo_confirme_cierre': yo,
        'ambos_confirmaron_cierre': conf_sol and conf_pro,
        'resumen_dismissed': dismiss,
    }


def _parse_acuerdo_resumen_campo(db, raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None or raw == '':
        return None
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _importe_oficial_contacto(db, contacto: Dict[str, Any]) -> Optional[float]:
    """Importe oficial del encargo (precio negociado)."""
    return db._parse_importe_acuerdo(db._precio_valor_desde_contacto(contacto))

