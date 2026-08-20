"""Servicio de dominio contacto (Campamento Base).

Extracción desde DBManager. Las fachadas permanecen en DBManager.
SQL de contactos vía ContactoRepo; cross-domain vía callbacks db.*.
"""
from __future__ import annotations

from decimal import InvalidOperation

from core.db_constants import RUANA_ROOT
from pathlib import Path


import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core import negociacion_manager as neg_mgr
from core.financial.money import (
    calcular_desglose_stripe_cents,
    cents_a_importe_bd,
    comision_ruana_cents,
    importe_bd_a_cents,
)
from core.repositories.contacto_repo import ContactoRepo

_repo = ContactoRepo()


def crear_contacto_ruana(
    db,
    solicitante_codigo: str,
    profesional_codigo: str,
    servicio: str = "",
    motivo_contacto: str = "",
    es_urgente: bool = False,
    precio_catalogo: str = "",
) -> Dict[str, Any]:
    """
    Crea un nuevo contacto RUANA en estado 'iniciado'.
    motivo_contacto: obligatorio para el flujo de chat (quién contactó a quién y por qué).
    es_urgente: solo el solicitante puede marcarlo al iniciar el chat (Regla 6).
    """
    with db._lock:
        try:
            if not solicitante_codigo or not profesional_codigo:
                return {
                    'status': 'error',
                    'message': 'Solicitante y profesional son obligatorios'
                }

            conn = db._connect()
            cursor = conn.cursor()

            if not _repo.existe_aliado(cursor, solicitante_codigo):
                return {
                    'status': 'error',
                    'message': f'Solicitante {solicitante_codigo} no existe como aliado'
                }
            if not _repo.existe_aliado(cursor, profesional_codigo):
                return {
                    'status': 'error',
                    'message': f'Profesional {profesional_codigo} no existe como aliado'
                }
            if db.tiene_pagos_ruana_pendientes(profesional_codigo):
                return {
                    'status': 'error',
                    'message': 'El profesional tiene pagos pendientes con RUANA y no puede recibir nuevos encargos hasta regularizar la situación.'
                }

            columnas = _repo.columnas_contactos_ruana(cursor)
            motivo_val = (motivo_contacto or '').strip() or None
            urgente_flag = 1 if es_urgente else 0
            tiene_motivo = 'motivo_contacto' in columnas
            tiene_urgente = 'es_urgente' in columnas

            contacto_id = _repo.insertar_contacto_iniciado(
                cursor,
                solicitante_codigo,
                profesional_codigo,
                servicio or '',
                motivo_val,
                urgente_flag,
                tiene_motivo,
                tiene_urgente,
            )

            # Iniciar negociación guiada con servicio propuesto por el contratante
            db._iniciar_negociacion_en_cursor(
                cursor, contacto_id, servicio or '', solicitante_codigo,
                precio_referencia=precio_catalogo or '',
            )

            conn.commit()

            return {
                'status': 'success',
                'id': contacto_id,
                'estado': 'iniciado',
                'solicitante_codigo': solicitante_codigo,
                'profesional_codigo': profesional_codigo,
                'servicio': servicio or '',
                'motivo_contacto': motivo_val,
                'es_urgente': bool(urgente_flag) if tiene_urgente else False,
                'creado_en': datetime.now().isoformat()
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()


def obtener_contacto_por_id(db, contacto_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene un contacto RUANA por su ID interno"""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            return _repo.select_por_id(cursor, contacto_id)
        except Exception as e:
            print(f"Error obteniendo contacto RUANA: {e}")
            return None
        finally:
            conn.close()


def aceptar_contacto_ruana(db, contacto_id: int, profesional_codigo: str) -> Dict[str, Any]:
    """
    Marca un contacto como 'aceptado' por el profesional y habilita contacto externo.
    Solo permite la transición desde estado 'iniciado'.
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            contacto = _repo.select_por_id(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}

            if contacto['profesional_codigo'] != profesional_codigo:
                return {
                    'status': 'error',
                    'message': 'El profesional no coincide con el contacto'
                }

            if contacto['estado'] != 'iniciado':
                return {
                    'status': 'error',
                    'message': f"Transición inválida desde estado {contacto['estado']}"
                }

            _repo.update_aceptado(cursor, contacto_id)

            conn.commit()
            return {
                'status': 'success',
                'id': contacto_id,
                'estado': 'aceptado'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()


def marcar_trabajo_en_progreso(db, contacto_id: int) -> Dict[str, Any]:
    """Transición a estado 'trabajo_en_progreso' desde 'aceptado' o 'iniciado'."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            estado_actual = _repo.select_estado(cursor, contacto_id)
            if estado_actual is None:
                return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}

            if estado_actual not in ('iniciado', 'aceptado'):
                return {
                    'status': 'error',
                    'message': f"Transición inválida desde estado {estado_actual}"
                }

            _repo.update_trabajo_en_progreso(cursor, contacto_id)

            conn.commit()
            return {
                'status': 'success',
                'id': contacto_id,
                'estado': 'trabajo_en_progreso'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()


def _encargo_con_precio_confirmado(db, contacto: Dict[str, Any]) -> bool:
    """True cuando ambas partes ya fijaron el precio del encargo (negocio en curso)."""
    estado = (contacto.get('estado') or '').strip()
    if estado in ('acuerdo_alcanzado', 'pendiente_de_pago', 'trabajo_cerrado'):
        return True
    if (contacto.get('modo_pago') or '').strip() == 'stripe' and estado == 'trabajo_en_progreso':
        return True
    if contacto.get('acuerdo_resumen_json'):
        return True
    if db._importe_oficial_contacto(contacto) is not None:
        return True
    neg = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
    return bool(neg.get('completo'))


def marcar_cerrado_no_concretado(db, contacto_id: int, motivo: str = "",
                                 actor_codigo: str = "") -> Dict[str, Any]:
    """
    Cierra el contacto como no concretado. Transacción atómica:
    - Estado → cerrado_no_concretado, pendiente_resolucion = 0.
    - -1 punto Score RUANA a cada aliado.
    - audit_log. No permitir si ya está en estado final.
    """
    sol = prof = None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contacto = _repo.select_para_cierre(cursor, contacto_id)
            if not contacto:
                return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
            estado_actual = (contacto.get('estado') or '').strip()
            if _encargo_con_precio_confirmado(db, contacto):
                return {
                    'status': 'error',
                    'message': (
                        'No se puede marcar como no concretado: el precio del encargo '
                        'ya está confirmado por ambas partes.'
                    ),
                }
            if estado_actual in db._ESTADOS_FINALES_CONTACTO:
                return {
                    'status': 'error',
                    'message': f'El contacto ya está cerrado o en estado final ({estado_actual}).'
                }

            sol = contacto.get('solicitante_codigo')
            prof = contacto.get('profesional_codigo')

            _repo.update_cerrado_no_concretado(cursor, contacto_id)

            detalles = f'aliados={sol},{prof} motivo={motivo or "cierre sin trabajo"}'
            db._audit_log(cursor, 'contacto', contacto_id, 'no_concretado',
                            'aliado', actor_codigo, detalles)
            conn.commit()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    if sol:
        db.aplicar_cambio_score(sol, -1, 'contacto_cerrado_no_concretado')
    if prof:
        db.aplicar_cambio_score(prof, -1, 'contacto_cerrado_no_concretado')
    return {'status': 'success', 'id': contacto_id, 'estado': 'cerrado_no_concretado'}


def marcar_en_conversacion(db, contacto_id: int, actor_codigo: str = "") -> Dict[str, Any]:
    """
    Marca el contacto como 'en_conversacion', posponer_recordatorio = 1 y fecha_pospuesto_hasta = now + posponer_horas.
    La alerta se oculta solo hasta esa fecha (límite temporal configurable).
    """
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            row = _repo.select_id_estado(cursor, contacto_id)
            if not row:
                return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
            estado_actual = (row[1] or '').strip()
            if estado_actual in db._ESTADOS_FINALES_CONTACTO:
                return {
                    'status': 'error',
                    'message': f'El contacto ya está en estado final ({estado_actual}).'
                }

            horas = db._get_posponer_horas()
            hasta = (datetime.now() + timedelta(hours=horas)).strftime('%Y-%m-%d %H:%M:%S')
            columnas = _repo.columnas_contactos_ruana(cursor)
            if 'fecha_pospuesto_hasta' in columnas:
                _repo.update_en_conversacion(cursor, contacto_id, hasta=hasta)
            else:
                _repo.update_en_conversacion(cursor, contacto_id, hasta=None)

            db._audit_log(cursor, 'contacto', contacto_id, 'en_conversacion',
                            'aliado', actor_codigo, f'posponer_recordatorio=1,hasta={hasta}')
            conn.commit()
            return {'status': 'success', 'id': contacto_id, 'estado': 'en_conversacion'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


def ocultar_contacto_del_panel(db, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
    """
    Marca el contacto como oculto en el panel personal de este aliado (Finalizar chat).
    El contacto deja de mostrarse en contactos abiertos para ese codigo_aliado.
    """
    codigo_aliado = (codigo_aliado or "").strip()
    if not codigo_aliado:
        return {'status': 'error', 'message': 'Código de aliado obligatorio'}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            row = _repo.select_participantes(cursor, contacto_id)
            if not row:
                return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
            sol, prof = row[1], row[2]
            if codigo_aliado not in (str(sol or '').strip(), str(prof or '').strip()):
                return {'status': 'error', 'message': 'No tienes permiso para finalizar este chat'}
            _repo.insertar_panel_oculto(cursor, contacto_id, codigo_aliado)
            conn.commit()
            return {'status': 'success', 'id': contacto_id}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


def registrar_importe_contacto(db, contacto_id: int, parte: str,
                               importe: float = None, moneda: str = "EUR",
                               usuario: str = "",
                               usar_precio_acordado: bool = False) -> Dict[str, Any]:
    """
    Registra la confirmación de importe por el contratante.
    Si existe precio negociado (importe_acordado), ese es el valor oficial y se ignora
    cualquier importe distinto enviado por el cliente.

    # DEPRECADO para uso normal — solo accesible vía panel admin como respaldo de
    # emergencia. Ver PROMPT_CURSOR_ELIMINAR_FLUJO_MANUAL.md.
    """
    resultado = None
    evaluar_regla7 = False
    with db._lock:
        conn = None
        try:
            parte = (parte or "").strip().lower()
            if parte not in ("solicitante", "profesional"):
                return {'status': 'error', 'message': "Parte debe ser 'solicitante' o 'profesional'"}

            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            contacto = _repo.select_por_id(cursor, contacto_id)
            if not contacto:
                conn.close()
                return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
            if (contacto.get('modo_pago') or '').strip() == 'stripe':
                conn.close()
                return {
                    'status': 'error',
                    'message': (
                        'Este encargo se gestiona con pago Stripe. '
                        'El cobro manual solo está disponible desde el panel de administración.'
                    ),
                    'estado': contacto.get('estado'),
                }
            estado_actual = contacto['estado']

            if estado_actual in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado'):
                conn.close()
                msg = 'Este contacto ya está cerrado. Ambas partes han confirmado el importe.' if estado_actual == 'trabajo_cerrado' else f'Contacto ya cerrado con estado {estado_actual}'
                return {'status': 'error', 'message': msg, 'estado': estado_actual}

            oficial = db._importe_oficial_contacto(contacto)
            if oficial is not None:
                importe_val = cents_a_importe_bd(importe_bd_a_cents(oficial))
                # Persistir columna si aún no estaba
                if contacto.get('importe_acordado') is None:
                    _repo.update_importe_acordado(cursor, contacto_id, importe_val)
            elif usar_precio_acordado:
                conn.close()
                return {
                    'status': 'error',
                    'message': 'No hay precio acordado numérico en la negociación. No se puede confirmar el importe.',
                }
            else:
                if importe is None:
                    conn.close()
                    return {'status': 'error', 'message': 'Importe obligatorio'}
                try:
                    cents = importe_bd_a_cents(importe)
                    importe_val = cents_a_importe_bd(cents)
                except (TypeError, ValueError, InvalidOperation):
                    conn.close()
                    return {'status': 'error', 'message': 'Importe debe ser numérico'}
                if cents <= 0:
                    conn.close()
                    return {'status': 'error', 'message': 'Importe debe ser mayor que cero'}

            # Resolver aliado_id desde usuario (código); normalizar a string para búsqueda
            usuario_str = str(usuario or "").strip()
            aliado = db.obtener_aliado_por_codigo(usuario_str)
            if not aliado:
                conn.close()
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            aliado_id = aliado.get('id')
            if not aliado_id:
                conn.close()
                return {'status': 'error', 'message': 'Aliado no encontrado'}

            solicitante_codigo = str(contacto.get('solicitante_codigo') or '').strip()
            if usuario_str != solicitante_codigo or parte != 'solicitante':
                conn.close()
                return {
                    'status': 'error',
                    'message': 'El importe solo puede confirmarlo el aliado que contrató el encargo.'
                }

            # No permitir doble declaración por el mismo aliado
            if _repo.existe_confirmacion_trabajo(cursor, contacto_id, aliado_id):
                estado_ahora = _repo.select_estado(cursor, contacto_id) or ''
                conn.close()
                if estado_ahora == 'trabajo_cerrado':
                    return {'status': 'error', 'message': 'Este contacto ya está cerrado. Ambas partes han confirmado el importe.', 'estado': 'trabajo_cerrado'}
                return {'status': 'error', 'message': 'Ya has declarado el importe para este contacto. Solo puedes declarar una vez; la otra parte debe declarar el suyo con su propia cuenta.'}

            if parte == 'solicitante':
                _repo.update_importe_solicitante(
                    cursor, contacto_id, importe_val, moneda, usuario_str
                )
            else:
                _repo.update_importe_profesional(
                    cursor, contacto_id, importe_val, moneda, usuario_str
                )

            _repo.insertar_confirmacion_trabajo(cursor, contacto_id, aliado_id, importe_val)
            db._audit_log(cursor, 'contacto', contacto_id, 'declaracion_importe', 'aliado', usuario_str,
                            f'parte={parte} importe={importe_val}')

            contacto = _repo.select_por_id(cursor, contacto_id)
            importe_sol = contacto.get('importe_solicitante')
            importe_prof = contacto.get('importe_profesional')

            if importe_sol is not None:
                if importe_prof is None or importe_bd_a_cents(importe_sol) == importe_bd_a_cents(importe_prof):
                    _, apoyo_c, _, comision_pct = calcular_desglose_stripe_cents(
                        importe_bd_a_cents(importe_sol)
                    )
                    apoyo_ruana = cents_a_importe_bd(apoyo_c)
                    _repo.update_trabajo_cerrado(
                        cursor, contacto_id, importe_sol, apoyo_ruana, comision_pct
                    )
                    _repo.insertar_ingreso_ruana(cursor, contacto_id, importe_sol, apoyo_ruana)
                    db._audit_log(cursor, 'contacto', contacto_id, 'cierre_confirmado', 'sistema', '',
                                    f'importe={importe_sol} apoyo_ruana={apoyo_ruana}')
                    prof_codigo = (contacto.get('profesional_codigo') or '').strip() or str(contacto.get('profesional_codigo') or '')
                    db._insert_evento_sistema(
                        cursor, 'apoyo_generado',
                        f'Apoyo RUANA de {apoyo_ruana}€ generado por trabajo cerrado (contacto {contacto_id})',
                        actor_tipo='sistema', actor_codigo=prof_codigo or None,
                        metadata={'contacto_id': contacto_id, 'importe_final': float(importe_sol), 'apoyo_ruana': apoyo_ruana}
                    )
                    # Alerta de cobro: notificación al profesional (Apoyo RUANA, QR/Bizum)
                    if not prof_codigo:
                        prof_codigo = _repo.select_profesional_codigo(cursor, contacto_id) or ''
                    try:
                        if prof_codigo:
                            qr_path, bizum = _repo.select_pago_aliado(cursor, prof_codigo)
                            default_qr, default_bizum = db._get_ruana_pago_defaults()
                            qr_path = qr_path or default_qr
                            bizum = bizum or default_bizum
                            mensaje = (
                                f"Se ha generado un Apoyo a RUANA de {apoyo_ruana}€ por tu trabajo cerrado. "
                                "Escanea el QR de PayPal o usa el número de Bizum para abonar el pago."
                            )
                            meta = json.dumps({
                                'contacto_id': contacto_id, 'apoyo_ruana': apoyo_ruana,
                                'qr_paypal_path': qr_path, 'bizum_num': bizum
                            }, ensure_ascii=False)
                            _repo.insertar_notificacion_apoyo(cursor, prof_codigo, mensaje, meta)
                            print(f"[RUANA] Lógica de cobro: contacto {contacto_id} → trabajo_cerrado, apoyo_ruana={apoyo_ruana}€, notificación de cobro enviada al profesional {prof_codigo}")
                        else:
                            print(f"[RUANA] registrar_importe_contacto: contacto {contacto_id} trabajo_cerrado pero profesional_codigo vacío, no se pudo crear notificación de cobro.")
                    except Exception as notif_err:
                        print(f"[RUANA] Error creando notificación de cobro (contacto {contacto_id}): {notif_err}")
                    resultado_estado = 'trabajo_cerrado'
                else:
                    _repo.update_importe_en_disputa(cursor, contacto_id)
                    db._audit_log(cursor, 'contacto', contacto_id, 'conflicto_importe', 'sistema', '', 'discrepancia')
                    _repo.insertar_payment_conflict_si_existe(
                        cursor,
                        contacto_id,
                        contacto.get('solicitante_codigo'),
                        contacto.get('profesional_codigo'),
                        importe_sol,
                        importe_prof,
                    )
                    resultado_estado = 'importe_en_disputa'
            else:
                resultado_estado = estado_actual

            conn.commit()
            resultado = {
                'status': 'success',
                'id': contacto_id,
                'estado': resultado_estado,
                'importe_acordado': float(importe_val),
            }
            evaluar_regla7 = True
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if evaluar_regla7 and resultado and resultado.get('status') == 'success':
        try:
            hito = db.evaluar_regla7_declaracion_24h(contacto_id)
            if hito:
                db.aplicar_cambio_score(hito[0], hito[1], hito[2])
        except Exception:
            pass
    return resultado if resultado is not None else {'status': 'error', 'message': 'Error desconocido'}


def obtener_contactos_abiertos_por_codigo(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """
    Contactos RUANA abiertos para alerta activa (negociación guiada + seguimiento post-servicio).
    Excluye posponer_recordatorio activo y contactos ocultos del panel.
    """
    codigo_aliado = (codigo_aliado or "").strip()
    if not codigo_aliado:
        return []
    estados_abiertos = (
        'iniciado', 'aceptado', 'trabajo_en_progreso', 'importe_en_disputa',
        'en_conversacion', 'acuerdo_alcanzado', 'pendiente_de_pago',
    )
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            posponer_sql = (
                "(COALESCE(c.posponer_recordatorio, 0) = 0) OR "
                "(c.fecha_pospuesto_hasta IS NOT NULL AND datetime(c.fecha_pospuesto_hasta) <= datetime('now'))"
            )
            if db.backend == "postgres":
                posponer_sql = (
                    "(COALESCE(c.posponer_recordatorio, 0) = 0) OR "
                    "(c.fecha_pospuesto_hasta IS NOT NULL AND c.fecha_pospuesto_hasta <= now())"
                )
            rows = _repo.select_contactos_abiertos(
                cursor, codigo_aliado, estados_abiertos, posponer_sql
            )

            result = []
            for d in rows:
                d['ya_declaraste_importe'] = d.get('ya_declaraste_importe') is not None
                d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                neg = neg_mgr.parse_negociacion(d.get('negociacion_json'))
                d['negociacion_completa'] = bool(neg.get('completo')) or d.get('estado') == 'acuerdo_alcanzado'
                d['paso_negociacion'] = neg.get('paso_actual')
                oficial = db._importe_oficial_contacto(d)
                d['importe_acordado'] = oficial
                d['precio_acordado'] = oficial
                if oficial is None:
                    try:
                        d['precio_acordado_texto'] = (neg.get('campos') or {}).get('precio', {}).get('valor') or ''
                    except Exception:
                        d['precio_acordado_texto'] = ''
                else:
                    d['precio_acordado_texto'] = f'{oficial:g}'
                paso = neg.get('paso_actual') or 'servicio'
                campo = (neg.get('campos') or {}).get(paso, {})
                rol_viewer = neg_mgr._rol_en_contacto(
                    codigo_aliado,
                    d.get('solicitante_codigo') or '',
                    d.get('profesional_codigo') or '',
                ) or 'solicitante'
                meta = neg_mgr.meta_negociacion(neg, rol_viewer, d.get('estado') or '')
                d['negociacion_paso_label'] = neg_mgr.CAMPOS_LABELS.get(paso, paso)
                d['negociacion_paso_estado'] = campo.get('estado') or neg_mgr.ESTADO_PENDIENTE
                d['negociacion_paso_estado_label'] = neg_mgr.ESTADO_LABELS.get(
                    d['negociacion_paso_estado'], d['negociacion_paso_estado']
                )
                d['negociacion_propuesto_por'] = campo.get('propuesto_por')
                d['negociacion_requiere_mi_respuesta'] = meta.get('requiere_mi_respuesta', False)
                d['negociacion_meta'] = meta
                result.append(d)
            return result
        except Exception as e:
            print(f"Error obteniendo contactos abiertos: {e}")
            return []
        finally:
            conn.close()


def obtener_contacto_resumen(db, contacto_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene un resumen seguro de un contacto:
    - No expone importes declarados por cada parte.
    - Expone solo el importe_final (si existe) y la comisión.
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            d = _repo.select_resumen(cursor, contacto_id)
            if not d:
                return None
            if 'es_urgente' in d:
                d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
            # Reparación: si trabajo cerrado con importe_final pero apoyo_ruana/comision faltan, calcular
            if d.get('estado') == 'trabajo_cerrado' and d.get('importe_final') is not None:
                ap = d.get('apoyo_ruana') if 'apoyo_ruana' in d else None
                com = d.get('comision')
                if ap is None or com is None:
                    calculado = cents_a_importe_bd(
                        comision_ruana_cents(importe_bd_a_cents(d['importe_final']))
                    )
                    if 'apoyo_ruana' in d:
                        d['apoyo_ruana'] = calculado
                    d['comision'] = calculado
            return d
        except Exception as e:
            print(f"Error obteniendo resumen de contacto: {e}")
            return None
        finally:
            conn.close()

def marcar_no_concretado(db, contacto_id: int, motivo: str = "") -> Dict[str, Any]:
    """
    Marca el contacto como 'no_concretado' (compatibilidad legacy).
    Ver marcar_cerrado_no_concretado para el flujo con -1 y audit.
    """
    return db.marcar_cerrado_no_concretado(contacto_id, motivo=motivo)


def _get_posponer_horas(db) -> int:
    """Lee posponer_horas desde config (horas que la alerta se oculta al 'Sigue en conversación'). Por defecto 24."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return int(data.get('posponer_horas', 24))
    except Exception:
        pass
    return 24

