"""Servicio de dominio pago (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de pagos vía PagoRepo.
"""
from __future__ import annotations

from core.db_constants import RUANA_ROOT
from core.repositories.pago_repo import PagoRepo
from core import stripe_client
from core.settings import get_settings
from core.financial.estados import EstadoFinanciero
from core.financial.money import (
    cents_a_importe_bd,
    calcular_desglose_stripe_cents,
    importe_bd_a_cents,
)
from core.services import financial_transaction_service as fts

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

_repo = PagoRepo()

# --- Extraído de DBManager (pago) ---

def _get_apoyo_pct(db) -> float:
    """Lee apoyo_pct desde config/ruana_reglas_v1.json. Por defecto 12.0 (%)."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return float(data.get('apoyo_pct', 12.0))
    except Exception:
        pass
    return 12.0

def _get_ruana_pago_defaults(db) -> Tuple[Optional[str], Optional[str]]:
    """Lee qr_paypal_path y bizum_num por defecto de RUANA desde config (para notificaciones Apoyo RUANA)."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            qr = (data.get('qr_paypal_path') or '').strip() or None
            bizum = (data.get('bizum_num') or '').strip() or None
            return (qr, bizum)
    except Exception:
        pass
    return (None, None)

def obtener_metodos_pago_ruana(db) -> Dict[str, Any]:
    """Devuelve los metodos de pago configurados para cobrar Apoyo RUANA."""
    defaults = {
        'bizum_num': '642868261',
        'iban': 'ES8915830001119028625152',
        'qr_revolut_path': '',
    }
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            defaults['bizum_num'] = (data.get('bizum_num') or defaults['bizum_num']).strip()
            defaults['iban'] = (data.get('iban') or defaults['iban']).strip()
            defaults['qr_revolut_path'] = (data.get('qr_revolut_path') or data.get('qr_paypal_path') or '').strip()
    except Exception:
        pass
    return defaults

def actualizar_metodos_pago_ruana(db, valores: Dict[str, Any], admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    """Actualiza Bizum, IBAN y/o QR Revolut en config/ruana_reglas_v1.json."""
    permitidas = {'bizum_num', 'iban', 'qr_revolut_path'}
    cambios = {k: (v or '').strip() for k, v in (valores or {}).items() if k in permitidas}
    if not cambios:
        return {'status': 'error', 'message': 'No hay metodos de pago validos para actualizar'}
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if not config_path.exists():
            return {'status': 'error', 'message': 'Archivo de reglas no encontrado'}
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.update(cambios)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        db.registrar_evento_sistema(
            'actualizar_metodos_pago',
            'Metodos de pago RUANA actualizados',
            actor_tipo='admin',
            actor_codigo=admin_codigo,
            metadata={'claves': sorted(cambios.keys())},
        )
        return {'status': 'success', 'message': 'Metodos de pago actualizados', 'metodos': db.obtener_metodos_pago_ruana()}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def listar_contactos_conflicto_pago(db) -> List[Dict[str, Any]]:
    """Lista contactos donde importe_A != importe_B (estado importe_en_disputa)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(row) for row in _repo.listar_contactos_conflicto_pago(cursor)]
        except Exception:
            return []
        finally:
            conn.close()

def listar_payment_conflicts_admin(db) -> List[Dict[str, Any]]:
    """Lista conflictos de payment_conflicts con nombres, orden created_at DESC."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if not _repo.tabla_payment_conflicts_existe(cursor):
                conn.close()
                return []
            return [dict(row) for row in _repo.listar_payment_conflicts_admin(cursor)]
        except Exception as e:
            print(f"Error listar_payment_conflicts_admin: {e}")
            return []
        finally:
            conn.close()

def obtener_payment_conflict_por_trabajo(db, trabajo_id: int, codigo_aliado: str) -> Optional[Dict[str, Any]]:
    """Obtiene el conflicto abierto para un trabajo; codigo_aliado debe ser contratante o profesional."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if not _repo.tabla_payment_conflicts_existe(cursor):
                conn.close()
                return None
            aliado_id = _repo.select_aliado_id_por_codigo(cursor, codigo_aliado)
            if aliado_id is None:
                conn.close()
                return None
            row = _repo.select_conflict_por_trabajo_y_aliado(cursor, trabajo_id, aliado_id)
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            conn.close()

def obtener_payment_conflict(db, conflict_id: int) -> Optional[Dict[str, Any]]:
    """Detalle de un conflicto por id."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if not _repo.tabla_payment_conflicts_existe(cursor):
                conn.close()
                return None
            row = _repo.select_conflict_detalle(cursor, conflict_id)
            return dict(row) if row else None
        except Exception as e:
            print(f"Error obtener_payment_conflict: {e}")
            return None
        finally:
            conn.close()

def resolver_payment_conflict_admin(db, conflict_id: int, decision: str, comentario: str,
                                    admin_codigo: str = "") -> Dict[str, Any]:
    """Admin resuelve: decision in (contratante, profesional, rechazado). comentario obligatorio."""
    decision = (decision or "").strip().lower()
    if decision not in ("contratante", "profesional", "rechazado"):
        return {'status': 'error', 'message': 'decision debe ser contratante, profesional o rechazado'}
    if not (comentario or "").strip():
        return {'status': 'error', 'message': 'comentario es obligatorio'}
    resultado = {'status': 'error', 'message': 'unknown'}
    decision_penal_disputa: Optional[str] = None
    contacto_penal_disputa: Optional[int] = None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_conflict_basico(cursor, conflict_id)
            if not row:
                return {'status': 'error', 'message': 'Conflicto no encontrado'}
            pc = dict(row)
            if pc.get('estado') not in ('PENDIENTE_PRUEBA', 'EN_REVISION'):
                return {'status': 'error', 'message': 'Este conflicto ya esta resuelto o cerrado'}
            trabajo_id = pc['trabajo_id']
            nuevo_estado = 'RECHAZADO' if decision == 'rechazado' else 'RESUELTO'
            importe_valido = None
            cerro_contacto_disputa = False
            if decision == 'contratante':
                importe_valido = float(pc['importe_contratante'])
            elif decision in ('profesional', 'rechazado'):
                importe_valido = float(pc['importe_profesional'])
            _repo.update_conflict_resuelto(
                cursor, nuevo_estado, (comentario or "").strip()[:2000], conflict_id
            )
            if importe_valido is not None and trabajo_id:
                c = _repo.select_contacto_partes(cursor, trabajo_id)
                if c and dict(c).get('estado') == 'importe_en_disputa':
                    d = dict(c)
                    pct = db._get_apoyo_pct()
                    apoyo = round(importe_valido * pct / 100.0, 2)
                    comision_pct = pct / 100.0
                    estado_pago_final = 'pendiente_pago' if apoyo > 0 else 'no_generado'
                    pendiente_pago_final = 1 if apoyo > 0 else 0
                    _repo.update_contacto_cerrar_disputa(
                        cursor, importe_valido, apoyo, comision_pct,
                        estado_pago_final, pendiente_pago_final, trabajo_id,
                    )
                    cerro_contacto_disputa = True
                    if apoyo > 0:
                        _repo.insertar_ingreso_ruana(cursor, trabajo_id, importe_valido, apoyo)
                    db._audit_log(cursor, 'contacto', trabajo_id, 'conflicto_resuelto_admin',
                                    'admin', admin_codigo, f'payment_conflict_id={conflict_id} decision={decision} importe={importe_valido}')
                    db._insert_evento_sistema(
                        cursor, 'apoyo_generado',
                        f'Apoyo RUANA de {apoyo}€ generado (payment_conflict {conflict_id} resuelto)',
                        actor_tipo='admin', actor_codigo=admin_codigo or None,
                        metadata={'contacto_id': trabajo_id, 'importe_final': importe_valido, 'apoyo_ruana': apoyo}
                    )
                    sol_codigo = (d.get('solicitante_codigo') or '').strip()
                    if sol_codigo:
                        db._marcar_notificaciones_contacto_leidas(
                            cursor, sol_codigo, trabajo_id,
                            tipos=['importe_impugnado', 'prueba_conflicto_en_revision']
                        )
                    prof_codigo = (d.get('profesional_codigo') or '').strip()
                    if prof_codigo:
                        db._marcar_notificaciones_contacto_leidas(
                            cursor, prof_codigo, trabajo_id,
                            tipos=['apoyo_ruana', 'pago_rechazado']
                        )
                    if prof_codigo and apoyo > 0:
                        row_aliado = _repo.select_qr_bizum_aliado(cursor, prof_codigo)
                        qr_path = row_aliado[0] if row_aliado and row_aliado[0] else None
                        bizum = row_aliado[1] if row_aliado and row_aliado[1] else None
                        default_qr, default_bizum = db._get_ruana_pago_defaults()
                        qr_path = qr_path or default_qr
                        bizum = bizum or default_bizum
                        mensaje = (
                            f"Se ha generado un Apoyo a RUANA de {apoyo}€ por tu trabajo cerrado. "
                            "Escanea el QR de PayPal o usa el número de Bizum para abonar el pago."
                        )
                        meta = json.dumps({
                            'contacto_id': trabajo_id, 'apoyo_ruana': apoyo,
                            'qr_paypal_path': qr_path, 'bizum_num': bizum
                        }, ensure_ascii=False)
                        _repo.insertar_notif_apoyo(cursor, prof_codigo, mensaje, meta)
            conn.commit()
            resultado = {'status': 'success', 'conflict_id': conflict_id, 'estado': nuevo_estado,
                         'importe_final': importe_valido}
            # Penalización 8: -3 al perdedor si admin da la razón a una parte
            if (
                cerro_contacto_disputa
                and decision in ('contratante', 'profesional')
                and trabajo_id
            ):
                decision_penal_disputa = decision
                contacto_penal_disputa = int(trabajo_id)
        except Exception as e:
            resultado = {'status': 'error', 'message': str(e)}
        finally:
            conn.close()
    if (
        resultado.get('status') == 'success'
        and decision_penal_disputa in ('contratante', 'profesional')
        and contacto_penal_disputa
    ):
        try:
            db.aplicar_penalizacion_disputa_perdida(
                contacto_penal_disputa, decision_penal_disputa
            )
        except Exception:
            pass
    return resultado

def resolver_conflicto_pago(db, contacto_id: int, importe_valido: float,
                            admin_codigo: str = "") -> Dict[str, Any]:
    """
    Admin resuelve conflicto: define importe valido, se aplica apoyo_pct, cierra contacto, audit.
    El score por encargo completado se aplica al marcar Apoyo como pagado (Regla 2).
    """
    imp = apoyo = 0.0
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_partes(cursor, contacto_id)
            if not row:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            contacto = dict(row)
            if contacto['estado'] != 'importe_en_disputa':
                return {'status': 'error', 'message': 'El contacto no está en conflicto de pago'}

            try:
                imp = float(importe_valido)
            except (TypeError, ValueError):
                return {'status': 'error', 'message': 'Importe válido debe ser numérico'}
            if imp <= 0:
                return {'status': 'error', 'message': 'Importe debe ser mayor que cero'}

            pct = db._get_apoyo_pct()
            apoyo = round(imp * pct / 100.0, 2)
            comision_pct = pct / 100.0
            _repo.update_contacto_resolver_conflicto(cursor, imp, apoyo, comision_pct, contacto_id)
            _repo.insertar_ingreso_ruana(cursor, contacto_id, imp, apoyo)
            db._audit_log(cursor, 'contacto', contacto_id, 'conflicto_resuelto_admin',
                            'admin', admin_codigo, f'importe_valido={imp} apoyo_ruana={apoyo}')
            db._insert_evento_sistema(
                cursor, 'apoyo_generado',
                f'Apoyo RUANA de {apoyo}€ generado (resolución admin contacto {contacto_id})',
                actor_tipo='admin', actor_codigo=admin_codigo or None,
                metadata={'contacto_id': contacto_id, 'importe_final': imp, 'apoyo_ruana': apoyo}
            )
            prof_codigo = (contacto.get('profesional_codigo') or '').strip()
            if prof_codigo:
                row_aliado = _repo.select_qr_bizum_aliado(cursor, prof_codigo)
                qr_path = row_aliado[0] if row_aliado and row_aliado[0] else None
                bizum = row_aliado[1] if row_aliado and row_aliado[1] else None
                default_qr, default_bizum = db._get_ruana_pago_defaults()
                qr_path = qr_path or default_qr
                bizum = bizum or default_bizum
                mensaje = (
                    f"Se ha generado un Apoyo a RUANA de {apoyo}€ por tu trabajo cerrado. "
                    "Escanea el QR de PayPal o usa el número de Bizum para abonar el pago."
                )
                meta = json.dumps({
                    'contacto_id': contacto_id, 'apoyo_ruana': apoyo,
                    'qr_paypal_path': qr_path, 'bizum_num': bizum
                }, ensure_ascii=False)
                _repo.insertar_notif_apoyo(cursor, prof_codigo, mensaje, meta)
            conn.commit()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return {'status': 'success', 'contacto_id': contacto_id, 'importe_final': imp, 'apoyo_ruana': apoyo}

def listar_contactos_pagos_apoyo(db) -> List[Dict[str, Any]]:
    """Lista contactos con trabajo_cerrado e importe_final (Apoyo RUANA generado) para gestión de estado de pago."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            lista = [dict(row) for row in _repo.listar_contactos_pagos_apoyo(cursor)]
            for d in lista:
                d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                if d.get('importe_final') is not None and d.get('apoyo_ruana') is None:
                    try:
                        d['apoyo_ruana'] = round(float(d['importe_final']) * db._get_apoyo_pct() / 100.0, 2)
                    except (TypeError, ValueError):
                        pass
            return lista
        except Exception as e:
            print(f"Error listar_contactos_pagos_apoyo: {e}")
            return []
        finally:
            conn.close()

def listar_contactos_pagos_en_revision(db) -> List[Dict[str, Any]]:
    """Lista contactos con estado_pago = 'en_revision' (comprobante subido, pendiente de aprobar/rechazar)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            lista = [dict(row) for row in _repo.listar_contactos_pagos_en_revision(cursor)]
            for d in lista:
                if d.get('importe_final') is not None and d.get('apoyo_ruana') is None:
                    try:
                        d['apoyo_ruana'] = round(float(d['importe_final']) * db._get_apoyo_pct() / 100.0, 2)
                    except (TypeError, ValueError):
                        pass
            return lista
        except Exception as e:
            print(f"Error listar_contactos_pagos_en_revision: {e}")
            return []
        finally:
            conn.close()

def actualizar_estado_pago_contacto(db, contacto_id: int, nuevo_estado: str,
                                    admin_codigo: str = "",
                                    motivo_rechazo: Optional[str] = None) -> Dict[str, Any]:
    """
    Admin actualiza estado_pago de un contacto (trabajo_cerrado con Apoyo RUANA).
    Estados permitidos: en_revision, pagado, rechazado.
    - pagado: pendiente_pago = 0, fecha_validacion_pago y admin_validacion_codigo;
      Regla 2: +2 score al solicitante y al profesional (encargo completado);
      Regla 3: +1 a ancestros 1ª/2ª generación de cada participante (linaje referidos);
      Regla 4: +3 si el aliado completa 4 encargos pagados limpios en el mismo mes;
      Regla 6: +3 al profesional si el contacto era urgente y se paga el mismo día.
    - rechazado: estado_pago → pendiente_pago, pendiente_pago = 1, motivo_rechazo_pago, comprobante_ruta=NULL;
      motivo_rechazo obligatorio; notifica al profesional.
    """
    nuevo_estado = (nuevo_estado or "").strip().lower()
    if nuevo_estado not in db.ESTADOS_PAGO_PERMITIDOS_ADMIN:
        return {'status': 'error', 'message': f'estado_pago debe ser uno de: {", ".join(db.ESTADOS_PAGO_PERMITIDOS_ADMIN)}'}
    if nuevo_estado == 'rechazado' and not (motivo_rechazo or "").strip():
        return {'status': 'error', 'message': 'El motivo de rechazo es obligatorio'}
    # (codigo, delta, motivo)
    scores_aplicar: List[Tuple[str, int, str]] = []
    participantes_regla2: List[str] = []
    resultado = {'status': 'error', 'message': 'unknown'}
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_estado_pago(cursor, contacto_id)
            if not row:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            r = dict(row)
            if r['estado'] != 'trabajo_cerrado' or r['importe_final'] is None:
                return {'status': 'error', 'message': 'El contacto no tiene Apoyo RUANA generado'}
            estado_anterior = (r.get('estado_pago') or '').strip().lower()
            if nuevo_estado == 'pagado':
                _repo.update_estado_pago_pagado(cursor, admin_codigo, contacto_id)
                db._audit_log(cursor, 'contacto', contacto_id, 'pago_apoyo_confirmado',
                                'admin', admin_codigo or '', f'admin={admin_codigo or ""}')
                prof_codigo = str(r.get('profesional_codigo') or '').strip()
                if prof_codigo:
                    db._marcar_notificaciones_contacto_leidas(
                        cursor, prof_codigo, contacto_id,
                        tipos=['apoyo_ruana', 'pago_rechazado', 'pago_aceptado']
                    )
                    mensaje = f"RUANA ha aceptado tu comprobante de pago. El Apoyo RUANA del contacto #{contacto_id} ha sido confirmado."
                    meta = json.dumps({'contacto_id': contacto_id, 'estado_pago': 'pagado'}, ensure_ascii=False)
                    _repo.insertar_notif_pago_aceptado(cursor, prof_codigo, mensaje, meta)
                # Regla 2: encargo completado al confirmar Apoyo pagado (+2 a ambos)
                if estado_anterior != 'pagado':
                    sol_codigo = str(r.get('solicitante_codigo') or '').strip()
                    if sol_codigo:
                        participantes_regla2.append(sol_codigo)
                    if prof_codigo:
                        participantes_regla2.append(prof_codigo)
            elif nuevo_estado == 'rechazado':
                motivo = (motivo_rechazo or "").strip()[:2000]
                _repo.update_estado_pago_rechazado(cursor, motivo, contacto_id)
                db._audit_log(cursor, 'contacto', contacto_id, 'pago_apoyo_rechazado',
                                'admin', admin_codigo or '', f'motivo={motivo[:500]}')
                prof_codigo = str(r.get('profesional_codigo') or '').strip()
                if prof_codigo:
                    db._marcar_notificaciones_contacto_leidas(
                        cursor, prof_codigo, contacto_id,
                        tipos=['apoyo_ruana', 'pago_rechazado', 'pago_aceptado']
                    )
                    mensaje = f"RUANA ha rechazado el comprobante de pago del Apoyo RUANA (contacto #{contacto_id}). Motivo: {motivo}"
                    meta = json.dumps({'contacto_id': contacto_id, 'motivo': motivo}, ensure_ascii=False)
                    _repo.insertar_notif_pago_rechazado(cursor, prof_codigo, mensaje, meta)
            else:
                _repo.update_estado_pago_generico(
                    cursor, nuevo_estado, 1 if nuevo_estado != 'pagado' else 0, contacto_id
                )
            db._audit_log(cursor, 'contacto', contacto_id, 'estado_pago_actualizado',
                            'admin', admin_codigo, f'estado_pago={nuevo_estado}')
            conn.commit()
            resultado = {'status': 'success', 'contacto_id': contacto_id, 'estado_pago': nuevo_estado}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()
    excluir_participantes = set(participantes_regla2)
    anio_mes_actual = datetime.now().strftime('%Y-%m')
    for codigo in participantes_regla2:
        scores_aplicar.append((codigo, 2, 'encargo_completado_apoyo_pagado'))
        # Regla 3: +1 a padre (gen1) y abuelo (gen2) del participante
        for ancestro, generacion in db.ancestros_referidos_para_score(
            codigo, max_generaciones=2, excluir=excluir_participantes
        ):
            scores_aplicar.append((
                ancestro,
                1,
                f'referido_encargo_completado_gen{generacion}',
            ))
        # Regla 4: 4 encargos pagados limpios en el mes → +3
        hito_regla4 = db.evaluar_regla4_encargos_mes_limpio(codigo, anio_mes_actual)
        if hito_regla4:
            scores_aplicar.append(hito_regla4)
    # Regla 6: urgente pagado el mismo día → +3 al profesional
    if participantes_regla2:
        hito_regla6 = db.evaluar_regla6_urgente_mismo_dia(contacto_id)
        if hito_regla6:
            scores_aplicar.append(hito_regla6)
    for codigo, delta, motivo in scores_aplicar:
        try:
            db.aplicar_cambio_score(codigo, delta, motivo)
        except Exception:
            pass
    return resultado

def tiene_pagos_ruana_pendientes(db, codigo_profesional: str) -> bool:
    """True si el profesional tiene al menos un contacto con Apoyo RUANA pendiente de pago (estado_pago = pendiente_pago)."""
    if not (codigo_profesional or "").strip():
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.tiene_pagos_pendientes(cursor, codigo_profesional.strip())
        except Exception:
            return False
        finally:
            conn.close()

def impugnar_apoyo_ruana(db, contacto_id: int, profesional_codigo: str,
                         motivo: str = "") -> Dict[str, Any]:
    """El profesional impugna el importe declarado por el contratante y solicita prueba."""
    prof_norm = str(profesional_codigo or "").strip()
    if not prof_norm:
        return {'status': 'error', 'message': 'Código de profesional requerido'}
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_impugnar(cursor, contacto_id)
            if not row:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            contacto = dict(row)
            if str(contacto.get('profesional_codigo') or '').strip() != prof_norm:
                return {'status': 'error', 'message': 'Solo el profesional del contacto puede impugnar este Apoyo RUANA'}
            if contacto.get('estado') != 'trabajo_cerrado' or contacto.get('importe_final') is None:
                return {'status': 'error', 'message': 'Este contacto no tiene un Apoyo RUANA pendiente impugnable'}
            if (contacto.get('estado_pago') or '') != 'pendiente_pago':
                return {'status': 'error', 'message': 'Este Apoyo RUANA no está pendiente de pago'}

            importe_final = float(contacto['importe_final'])
            solicitante_codigo = str(contacto.get('solicitante_codigo') or '').strip()
            id_sol = _repo.select_aliado_id_por_codigo(cursor, solicitante_codigo)
            id_prof = _repo.select_aliado_id_por_codigo(cursor, prof_norm)
            if id_sol is None or id_prof is None:
                return {'status': 'error', 'message': 'No se pudo identificar a las partes del contacto'}
            r_sol = (id_sol,)
            r_prof = (id_prof,)

            _repo.update_contacto_impugnar(cursor, contacto_id)
            db._marcar_notificaciones_contacto_leidas(
                cursor, prof_norm, contacto_id, tipos=['apoyo_ruana', 'pago_rechazado']
            )
            if _repo.tabla_payment_conflicts_existe(cursor):
                existing_id = _repo.select_conflict_id_por_trabajo(cursor, contacto_id)
                comentario_pc = (motivo or "").strip()[:2000] or None
                if existing_id is not None:
                    _repo.update_conflict_impugnacion(
                        cursor, r_sol[0], r_prof[0], importe_final, comentario_pc, existing_id
                    )
                else:
                    _repo.insertar_conflict_impugnacion(
                        cursor, contacto_id, r_sol[0], r_prof[0], importe_final, comentario_pc
                    )
                from core.repositories.financial_conflict_repo import FinancialConflictRepo
                from core.financial.conflict_estados import TipoConflicto
                FinancialConflictRepo()._formalizar_existente(
                    cursor, contacto_id, TipoConflicto.IMPORTE_DISPUTADO,
                    (motivo or "importe impugnado")[:2000], prof_norm,
                    int(importe_bd_a_cents(importe_final)), "eur",
                )

            db._audit_log(cursor, 'contacto', contacto_id, 'apoyo_impugnado',
                            'aliado', prof_norm, (motivo or 'importe impugnado')[:500])
            mensaje = (
                f"El profesional ha impugnado el importe declarado para el contacto #{contacto_id}. "
                "Adjunta documentación o comprobantes para que RUANA pueda validarlo."
            )
            meta = json.dumps({'contacto_id': contacto_id, 'importe_declarado': importe_final}, ensure_ascii=False)
            _repo.insertar_notif_importe_impugnado(cursor, solicitante_codigo, mensaje, meta)
            conn.commit()
            return {'status': 'success', 'contacto_id': contacto_id, 'estado': 'importe_en_disputa'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def listar_contactos_pago_pendiente_profesional(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """Contactos donde el aliado es profesional y tiene Apoyo RUANA pendiente de pago (estado_pago = pendiente_pago)."""
    codigo_norm = str(codigo_aliado or '').strip()
    if not codigo_norm:
        return []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            lista = [dict(row) for row in _repo.listar_pago_pendiente_profesional(cursor, codigo_norm)]
            for d in lista:
                if d.get('importe_final') is not None and d.get('apoyo_ruana') is None:
                    try:
                        d['apoyo_ruana'] = round(float(d['importe_final']) * db._get_apoyo_pct() / 100.0, 2)
                    except (TypeError, ValueError):
                        pass
            return lista
        except Exception as e:
            print(f"Error listar_contactos_pago_pendiente_profesional: {e}")
            return []
        finally:
            conn.close()

def subir_comprobante_apoyo_ruana(db, contacto_id: int, profesional_codigo: str,
                                   comprobante_ruta: str, comentario: Optional[str] = None) -> Dict[str, Any]:
    """
    El profesional sube comprobante de pago del Apoyo RUANA.
    Requiere: contacto con estado_pago = pendiente_pago y profesional_codigo = profesional_codigo.
    Actualiza: comprobante_ruta, estado_pago = 'en_revision', pendiente_pago = 1 (sin cambio).
    Notifica al administrador vía eventos_sistema.
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_comprobante(cursor, contacto_id)
            if not row:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            r = dict(row)
            if (r['profesional_codigo'] or '').strip() != (profesional_codigo or '').strip():
                return {'status': 'error', 'message': 'Solo el profesional del contacto puede subir el comprobante'}
            if (r['estado_pago'] or '') != 'pendiente_pago':
                return {'status': 'error', 'message': 'Este contacto no tiene el pago en estado pendiente'}
            _repo.update_comprobante_en_revision(cursor, comprobante_ruta, contacto_id)
            db._marcar_notificaciones_contacto_leidas(
                cursor, profesional_codigo, contacto_id,
                tipos=['apoyo_ruana', 'pago_rechazado']
            )
            db._audit_log(cursor, 'contacto', contacto_id, 'comprobante_apoyo_subido',
                            'aliado', profesional_codigo, f'ruta={comprobante_ruta}')
            db._insert_evento_sistema(
                cursor, 'comprobante_apoyo_subido',
                f'Comprobante de pago Apoyo RUANA subido por profesional (contacto {contacto_id}, {r.get("apoyo_ruana")} €)',
                actor_tipo='aliado', actor_codigo=profesional_codigo,
                metadata={'contacto_id': contacto_id, 'comprobante_ruta': comprobante_ruta, 'comentario': (comentario or '')[:500]}
            )
            conn.commit()
            return {'status': 'success', 'contacto_id': contacto_id, 'estado_pago': 'en_revision'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()
# --- Extraído de DBManager (pago) ---

def subir_prueba_conflicto(db, conflict_id: int, contratante_codigo: str, prueba_url: str) -> Dict[str, Any]:
    """Solo contratante: guarda prueba_url y pasa estado a EN_REVISION."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_conflict_para_prueba(cursor, conflict_id)
            if not row:
                return {'status': 'error', 'message': 'Conflicto no encontrado'}
            conflicto = dict(row)
            aliado_id = _repo.select_aliado_id_por_codigo(cursor, contratante_codigo)
            if aliado_id is None or aliado_id != conflicto['contratante_id']:
                return {'status': 'error', 'message': 'Solo el contratante puede subir la prueba'}
            _repo.update_conflict_prueba(cursor, prueba_url, conflict_id)
            trabajo_id = int(conflicto['trabajo_id'])
            contratante_norm = str(conflicto.get('contratante_codigo') or contratante_codigo or '').strip()
            db._marcar_notificaciones_contacto_leidas(
                cursor, contratante_norm, trabajo_id,
                tipos=['importe_impugnado', 'prueba_conflicto_en_revision']
            )
            mensaje = (
                f"Documentacion enviada para el contacto #{trabajo_id}; "
                "queda pendiente de revision por RUANA."
            )
            meta = json.dumps({
                'contacto_id': trabajo_id,
                'conflict_id': conflict_id,
                'prueba_url': prueba_url
            }, ensure_ascii=False)
            _repo.insertar_notif_prueba_revision(cursor, contratante_norm, mensaje, meta)
            conn.commit()
            return {'status': 'success', 'id': conflict_id, 'estado': 'EN_REVISION'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

# --- Stripe Connect (separate charges and transfers) ---

def _calcular_importes_stripe(importe_bruto_cents: int, db) -> Tuple[int, int, int, float]:
    """Desglose en céntimos; comision_pct es fracción legacy para columnas BD (0.12)."""
    _ = db  # apoyo_pct fijado en money.COMISION_RUANA_PCT (12 %)
    return calcular_desglose_stripe_cents(importe_bruto_cents)


def _calcular_importes_stripe_bd(importe_bd, db) -> Tuple[float, float, float, float]:
    """Wrapper legacy: euros BD → céntimos → euros BD para persistencia."""
    bruto_c, apoyo_c, neto_c, comision_pct = _calcular_importes_stripe(importe_bd_a_cents(importe_bd), db)
    return (
        cents_a_importe_bd(bruto_c),
        cents_a_importe_bd(apoyo_c),
        cents_a_importe_bd(neto_c),
        comision_pct,
    )


def stripe_habilitado_global() -> bool:
    return stripe_client.stripe_payments_enabled() and stripe_client.stripe_configured()


MSG_PROFESIONAL_STRIPE_NO_LISTO = (
    "Este profesional está completando la activación de su cuenta de pago. "
    "Podrás cerrar el encargo en cuanto esté lista."
)
AVISO_PAGO_NO_DISPONIBLE = "Pago no disponible todavía con este profesional"
MSG_PROFESIONAL_DEBE_CONECTAR_STRIPE = (
    "Debes conectar tu cuenta de pago antes de poder cerrar encargos con precio."
)
MSG_CONTRATANTE_ESPERA_STRIPE_PROFESIONAL = (
    "Este profesional debe activar su cuenta de pago antes de que puedas confirmar el precio final."
)


def profesional_stripe_listo(db, codigo_profesional: str) -> bool:
    codigo = (codigo_profesional or "").strip()
    if not codigo:
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            row = _repo.select_aliado_stripe(cursor, codigo)
            if not row:
                return False
            data = dict(row) if hasattr(row, "keys") else {
                "stripe_account_id": row[3],
                "stripe_charges_enabled": row[4],
            }
            return bool(
                (data.get("stripe_account_id") or "").strip()
                and int(data.get("stripe_charges_enabled") or 0) == 1
            )
        except Exception:
            return False
        finally:
            conn.close()


def sincronizar_estado_stripe_profesional(db, codigo_profesional: str) -> Dict[str, Any]:
    """Consulta Stripe y actualiza flags locales (p. ej. si el webhook account.updated tarda)."""
    codigo = (codigo_profesional or "").strip()
    if not codigo or not stripe_habilitado_global():
        return {"status": "skipped", "stripe_pago_listo": False}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_aliado_stripe(cursor, codigo)
            if not row:
                return {"status": "error", "message": "Aliado no encontrado"}
            aliado = dict(row)
            account_id = (aliado.get("stripe_account_id") or "").strip()
            if not account_id:
                return {
                    "status": "success",
                    "stripe_pago_listo": False,
                    "stripe_account_id": "",
                }
            account = stripe_client.retrieve_account(account_id)
            charges = bool(account.get("charges_enabled"))
            payouts = bool(account.get("payouts_enabled"))
            details = bool(account.get("details_submitted"))
            _repo.update_aliado_stripe_account(
                cursor, codigo, account_id,
                1 if charges else 0,
                1 if payouts else 0,
                1 if details else 0,
            )
            conn.commit()
            return {
                "status": "success",
                "stripe_pago_listo": charges,
                "stripe_account_id": account_id,
                "stripe_charges_enabled": 1 if charges else 0,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def puede_usar_stripe_para_contacto(db, contacto: Dict[str, Any]) -> bool:
    if not stripe_habilitado_global():
        return False
    prof = str(contacto.get("profesional_codigo") or "").strip()
    return profesional_stripe_listo(db, prof)


def activar_pago_stripe_tras_acuerdo(
    db,
    contacto_id: int,
    solicitante_codigo: str,
    importe: float,
) -> Dict[str, Any]:
    """Tras acuerdo bilateral: congela importe y deja el encargo pendiente de pago Stripe."""
    importe_val, apoyo, neto, comision_pct = _calcular_importes_stripe_bd(importe, db)
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            updated = _repo.update_contacto_pendiente_pago_stripe(
                cursor, contacto_id, importe_val, apoyo, comision_pct, neto
            )
            if updated != 1:
                conn.close()
                return {
                    "status": "error",
                    "message": "No se pudo activar el pago Stripe para este contacto",
                }
            mensaje = (
                f"El encargo #{contacto_id} está listo para pagar ({importe_val:g} €). "
                "Pulsa «Pagar ahora» para completar el pago de forma segura."
            )
            meta = json.dumps(
                {
                    "contacto_id": contacto_id,
                    "importe_acordado": importe_val,
                    "modo_pago": "stripe",
                },
                ensure_ascii=False,
            )
            _repo.insertar_notif_pago_stripe(
                cursor,
                (solicitante_codigo or "").strip(),
                "Pago pendiente del encargo",
                mensaje,
                meta,
            )
            db._audit_log(
                cursor, "contacto", contacto_id, "stripe_pendiente_pago",
                "sistema", solicitante_codigo or "",
                f"importe={importe_val} apoyo={apoyo} neto={neto}",
            )
            conn.commit()
            fts.sincronizar_tras_activacion_stripe(db, contacto_id, solicitante_codigo or "")
            return {
                "status": "success",
                "contacto_id": contacto_id,
                "estado": "pendiente_de_pago",
                "estado_pago": "esperando_cobro_cliente",
                "modo_pago": "stripe",
                "importe_acordado": importe_val,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def crear_checkout_stripe(
    db, contacto_id: int, solicitante_codigo: str
) -> Dict[str, Any]:
    """Crea sesión Checkout; importe leído exclusivamente de BD."""
    codigo = (solicitante_codigo or "").strip()
    if not stripe_habilitado_global():
        return {"status": "error", "message": "Pagos Stripe no habilitados"}
    settings = get_settings()
    base_url = (settings.public_app_url or "http://localhost:5000").rstrip("/")
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.reclamar_checkout_stripe(
                cursor, contacto_id, ("esperando_cobro_cliente", "checkout_activo")
            )
            if not row:
                return {"status": "error", "message": "Contacto no disponible para pago Stripe"}
            contacto = dict(row)
            if str(contacto.get("solicitante_codigo") or "").strip() != codigo:
                return {"status": "error", "message": "Solo el contratante puede iniciar el pago"}
            importe = contacto.get("importe_acordado")
            if importe is None:
                importe = contacto.get("importe_final")
            amount_cents = importe_bd_a_cents(importe)
            if amount_cents <= 0:
                return {"status": "error", "message": "Importe acordado no válido en base de datos"}
            importe_val = cents_a_importe_bd(amount_cents)
            session = stripe_client.create_checkout_session(
                amount_cents=amount_cents,
                currency="eur",
                contacto_id=contacto_id,
                success_url=f"{base_url}/aliado.html?stripe_pago=ok&contacto_id={contacto_id}",
                cancel_url=f"{base_url}/aliado.html?stripe_pago=cancel&contacto_id={contacto_id}",
                idempotency_key=f"checkout-contacto-{contacto_id}-v1",
            )
            session_id = session.get("id")
            if not session_id:
                return {"status": "error", "message": "Stripe no devolvió sesión de checkout"}
            _repo.update_checkout_stripe_activo(cursor, session_id, contacto_id)
            db._audit_log(
                cursor, "contacto", contacto_id, "stripe_checkout_creado",
                "aliado", codigo, f"session={session_id} importe={importe_val}",
            )
            conn.commit()
            return {
                "status": "success",
                "checkout_url": session.get("url"),
                "session_id": session_id,
                "importe": importe_val,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def _aplicar_score_tras_transfer(db, contacto_id: int, solicitante_codigo: str, profesional_codigo: str) -> None:
    participantes = [c for c in (solicitante_codigo, profesional_codigo) if c]
    scores_aplicar: List[Tuple[str, int, str]] = []
    anio_mes_actual = datetime.now().strftime("%Y-%m")
    for codigo in participantes:
        scores_aplicar.append((codigo, 2, "encargo_completado_stripe_transferido"))
        for ancestro, generacion in db.ancestros_referidos_para_score(
            codigo, max_generaciones=2, excluir=set(participantes)
        ):
            scores_aplicar.append((ancestro, 1, f"referido_encargo_completado_gen{generacion}"))
        hito_regla4 = db.evaluar_regla4_encargos_mes_limpio(codigo, anio_mes_actual)
        if hito_regla4:
            scores_aplicar.append(hito_regla4)
    hito_regla6 = db.evaluar_regla6_urgente_mismo_dia(contacto_id)
    if hito_regla6:
        scores_aplicar.append(hito_regla6)
    for codigo, delta, motivo in scores_aplicar:
        try:
            db.aplicar_cambio_score(codigo, delta, motivo)
        except Exception:
            pass


def confirmar_trabajo_y_transferir(
    db, contacto_id: int, contratante_codigo: str
) -> Dict[str, Any]:
    """
    El aliado contratante confirma que el trabajo se realizó y RUANA transfiere al profesional.

    FASE 03: delega en financial_transfer_service (idempotencia + concurrencia BD).
    TRANSFERIDO solo se alcanza vía webhook transfer.paid.
    """
    from core.services import financial_transfer_service as transfer_svc

    return transfer_svc.ejecutar_liberacion_y_transferencia(db, contacto_id, contratante_codigo)


def _procesar_pago_confirmado(
    db, contacto_id: int, payment_intent_id: str
) -> Dict[str, Any]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_stripe_por_id(cursor, contacto_id)
            if not row:
                return {"status": "ignored", "message": "contacto no encontrado"}
            contacto = dict(row)
            if contacto.get("stripe_payment_intent_id"):
                return {"status": "ignored", "message": "ya procesado"}
            importe_cents = importe_bd_a_cents(
                contacto.get("importe_acordado") or contacto.get("importe_final")
            )
            if importe_cents <= 0:
                return {"status": "error", "message": "sin importe"}
            bruto_c, apoyo_c, neto_c, comision_pct = _calcular_importes_stripe(importe_cents, db)
            importe_val = cents_a_importe_bd(bruto_c)
            apoyo = cents_a_importe_bd(apoyo_c)
            neto = cents_a_importe_bd(neto_c)
            updated = _repo.marcar_cobro_stripe_confirmado(
                cursor,
                contacto_id,
                payment_intent_id,
                importe_val,
                apoyo,
                comision_pct,
                neto,
            )
            if updated != 1:
                conn.commit()
                return {"status": "ignored", "message": "estado no aplicable"}
            _repo.insertar_ingreso_ruana(cursor, contacto_id, importe_val, apoyo)
            prof_codigo = str(contacto.get("profesional_codigo") or "").strip()
            sol_codigo = str(contacto.get("solicitante_codigo") or "").strip()
            meta_sol = json.dumps(
                {"contacto_id": contacto_id, "importe": importe_val, "estado_pago": "cobro_confirmado"},
                ensure_ascii=False,
            )
            _repo.insertar_notif_pago_stripe(
                cursor,
                sol_codigo,
                "Pago confirmado",
                (
                    f"Tu pago de {importe_val:g} € del encargo #{contacto_id} está confirmado. "
                    "Cuando el trabajo esté terminado, confirma la entrega para liberar el pago al profesional."
                ),
                meta_sol,
            )
            meta_prof = json.dumps(
                {"contacto_id": contacto_id, "importe_neto": neto},
                ensure_ascii=False,
            )
            _repo.insertar_notif_pago_stripe(
                cursor,
                prof_codigo,
                "Pago del cliente recibido",
                (
                    f"El cliente pagó {importe_val:g} € por el encargo #{contacto_id}. "
                    "Realiza el trabajo; el contratante confirmará la entrega para liberar tu pago."
                ),
                meta_prof,
            )
            db._audit_log(
                cursor, "contacto", contacto_id, "stripe_cobro_confirmado",
                "sistema", "", f"pi={payment_intent_id} importe={importe_val}",
            )
            conn.commit()
            fts.sincronizar_tras_cobro_confirmado(db, contacto_id, payment_intent_id)
            from core.services.financial_ledger_hooks import on_pago_confirmado
            on_pago_confirmado(
                db,
                contacto_id=contacto_id,
                payment_intent_id=payment_intent_id,
                importe_bruto_cents=bruto_c,
            )
            return {"status": "success", "contacto_id": contacto_id}
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def procesar_webhook_stripe(db, payload: bytes, sig_header: str) -> Dict[str, Any]:
    """Verifica firma e idempotencia; procesa eventos Stripe (FASE 02 → stripe_webhook_service)."""
    from core.services import stripe_webhook_service
    return stripe_webhook_service.procesar_webhook(db, payload, sig_header)


def procesar_timeouts_sin_confirmacion_stripe(db) -> int:
    """Plazo sin confirmación del contratante → payment_conflicts para revisión admin."""
    dias = int(os.environ.get("RUANA_STRIPE_TRANSFER_TIMEOUT_DAYS", "12") or "12")
    procesados = 0
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_stripe_sin_confirmacion_vencidos(
                cursor, dias, postgres=(getattr(db, "backend", "") == "postgres")
            )
            for row in rows:
                item = dict(row)
                contacto_id = int(item["id"])
                importe = cents_a_importe_bd(
                    importe_bd_a_cents(item.get("importe_final"))
                )
                id_sol = _repo.select_aliado_id_por_codigo(cursor, item.get("solicitante_codigo") or "")
                id_prof = _repo.select_aliado_id_por_codigo(cursor, item.get("profesional_codigo") or "")
                if id_sol is None or id_prof is None:
                    continue
                _repo.insertar_conflict_sin_confirmacion(
                    cursor,
                    contacto_id,
                    id_sol,
                    id_prof,
                    importe,
                    item.get("stripe_payment_intent_id"),
                )
                _repo.marcar_stripe_revision_admin(cursor, contacto_id)
                procesados += 1
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"[RUANA] Error procesar_timeouts_sin_confirmacion_stripe: {e}")
        finally:
            if conn:
                conn.close()
    return procesados


def iniciar_onboarding_stripe_profesional(db, codigo_profesional: str) -> Dict[str, Any]:
    """Crea cuenta Connect Express y devuelve URL de onboarding."""
    codigo = (codigo_profesional or "").strip()
    if not stripe_habilitado_global():
        return {"status": "error", "message": "Pagos Stripe no habilitados"}
    settings = get_settings()
    base_url = (settings.public_app_url or "http://localhost:5000").rstrip("/")
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_aliado_stripe(cursor, codigo)
            if not row:
                return {"status": "error", "message": "Aliado no encontrado"}
            aliado = dict(row)
            account_id = (aliado.get("stripe_account_id") or "").strip()
            if not account_id:
                account = stripe_client.create_connect_account(email=aliado.get("email"))
                account_id = account.get("id")
                if not account_id:
                    return {"status": "error", "message": "No se pudo crear cuenta Connect"}
                _repo.update_aliado_stripe_account(cursor, codigo, account_id, 0, 0, 0)
            link = stripe_client.create_account_link(
                account_id=account_id,
                refresh_url=f"{base_url}/aliado.html?stripe_onboarding=refresh",
                return_url=f"{base_url}/aliado.html?stripe_onboarding=done",
            )
            conn.commit()
            return {
                "status": "success",
                "onboarding_url": link.get("url"),
                "stripe_account_id": account_id,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def estado_pago_stripe_contacto(db, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
    """Estado de pago Stripe visible para participantes del contacto."""
    codigo = (codigo_aliado or "").strip()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_stripe_por_id(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            sol = str(contacto.get("solicitante_codigo") or "").strip()
            pro = str(contacto.get("profesional_codigo") or "").strip()
            if codigo not in (sol, pro):
                return {"status": "error", "message": "No autorizado"}
            es_contratante = codigo == sol
            return {
                "status": "success",
                "modo_pago": contacto.get("modo_pago") or "manual",
                "estado": contacto.get("estado"),
                "estado_pago": contacto.get("estado_pago"),
                "importe_acordado": contacto.get("importe_acordado"),
                "importe_neto_profesional": contacto.get("importe_neto_profesional"),
                "puede_pagar": es_contratante and contacto.get("estado_pago") in (
                    "esperando_cobro_cliente", "checkout_activo"
                ),
                "puede_confirmar_trabajo": es_contratante and contacto.get("estado_pago") == "cobro_confirmado",
                "es_contratante": es_contratante,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def _stripe_onboarding_estado(aliado: Dict[str, Any]) -> str:
    account = (aliado.get("stripe_account_id") or "").strip()
    if not account:
        return "sin_cuenta"
    if int(aliado.get("stripe_charges_enabled") or 0) == 1:
        return "listo"
    if int(aliado.get("stripe_onboarding_completo") or 0) == 1:
        return "onboarding_pendiente"
    return "onboarding_pendiente"


def resumen_stripe_admin(db) -> Dict[str, Any]:
    """Resumen admin: onboarding Stripe por aliado y pipeline de transferencias."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            aliados_raw = _repo.listar_aliados_stripe_onboarding(cursor)
            contactos_raw = _repo.listar_contactos_stripe_pipeline(cursor)
            aliados = []
            for row in aliados_raw:
                item = dict(row)
                item["onboarding_estado"] = _stripe_onboarding_estado(item)
                aliados.append(item)
            transferencias = []
            en_transito = 0.0
            pendientes = 0
            completadas = 0
            for row in contactos_raw:
                item = dict(row)
                estado_pago = (item.get("estado_pago") or "").strip()
                transfer_id = (item.get("stripe_transfer_id") or "").strip()
                neto = float(item.get("importe_neto_profesional") or 0)
                if estado_pago == "transferido" or transfer_id:
                    item["transferencia_estado"] = "completada"
                    completadas += 1
                elif estado_pago == "cobro_confirmado":
                    item["transferencia_estado"] = "pendiente"
                    pendientes += 1
                    en_transito += neto
                elif estado_pago in ("esperando_cobro_cliente", "checkout_activo"):
                    item["transferencia_estado"] = "esperando_cobro"
                elif estado_pago == "revision_admin":
                    item["transferencia_estado"] = "revision"
                else:
                    item["transferencia_estado"] = estado_pago or "otro"
                transferencias.append(item)
            return {
                "status": "success",
                "stripe_habilitado": stripe_habilitado_global(),
                "aliados": aliados,
                "transferencias": transferencias,
                "totales": {
                    "importe_en_transito": round(en_transito, 2),
                    "transferencias_pendientes": pendientes,
                    "transferencias_completadas": completadas,
                },
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def _stripe_onboarding_estado(aliado: Dict[str, Any]) -> str:
    account = (aliado.get("stripe_account_id") or "").strip()
    if not account:
        return "sin_cuenta"
    if int(aliado.get("stripe_charges_enabled") or 0) == 1:
        return "listo"
    if int(aliado.get("stripe_onboarding_completo") or 0) == 1:
        return "onboarding_pendiente"
    return "onboarding_pendiente"


def resumen_stripe_admin(db) -> Dict[str, Any]:
    """Resumen admin: onboarding Stripe por aliado y pipeline de transferencias."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            aliados_raw = _repo.listar_aliados_stripe_onboarding(cursor)
            contactos_raw = _repo.listar_contactos_stripe_pipeline(cursor)
            aliados = []
            for row in aliados_raw:
                item = dict(row)
                item["onboarding_estado"] = _stripe_onboarding_estado(item)
                aliados.append(item)
            transferencias = []
            en_transito = 0.0
            pendientes = 0
            completadas = 0
            for row in contactos_raw:
                item = dict(row)
                estado_pago = (item.get("estado_pago") or "").strip()
                transfer_id = (item.get("stripe_transfer_id") or "").strip()
                neto = float(item.get("importe_neto_profesional") or 0)
                if estado_pago == "transferido" or transfer_id:
                    item["transferencia_estado"] = "completada"
                    completadas += 1
                elif estado_pago == "cobro_confirmado":
                    item["transferencia_estado"] = "pendiente"
                    pendientes += 1
                    en_transito += neto
                elif estado_pago in ("esperando_cobro_cliente", "checkout_activo"):
                    item["transferencia_estado"] = "esperando_cobro"
                elif estado_pago == "revision_admin":
                    item["transferencia_estado"] = "revision"
                else:
                    item["transferencia_estado"] = estado_pago or "otro"
                transferencias.append(item)
            return {
                "status": "success",
                "stripe_habilitado": stripe_habilitado_global(),
                "aliados": aliados,
                "transferencias": transferencias,
                "totales": {
                    "importe_en_transito": round(en_transito, 2),
                    "transferencias_pendientes": pendientes,
                    "transferencias_completadas": completadas,
                },
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()

