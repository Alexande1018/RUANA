"""Servicio de dominio pago (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
"""
from __future__ import annotations

from core.db_constants import RUANA_ROOT

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
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
            cursor.execute("""
                SELECT id, solicitante_codigo, profesional_codigo, servicio,
                       importe_solicitante, importe_profesional, comprobante_ruta,
                       estado, fecha_disputa, creado_en
                FROM contactos_ruana
                WHERE estado = 'importe_en_disputa'
                  AND importe_solicitante IS NOT NULL AND importe_profesional IS NOT NULL
                  AND importe_solicitante != importe_profesional
                ORDER BY fecha_disputa DESC, id DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
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
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
            if not cursor.fetchone():
                conn.close()
                return []
            cursor.execute("""
                SELECT pc.id, pc.trabajo_id, pc.contratante_id, pc.profesional_id,
                       pc.importe_contratante, pc.importe_profesional, pc.estado,
                       pc.prueba_url, pc.comentario_admin, pc.created_at, pc.updated_at,
                       a_cont.nombre AS contratante_nombre, a_cont.codigo AS contratante_codigo,
                       a_prof.nombre AS profesional_nombre, a_prof.codigo AS profesional_codigo
                FROM payment_conflicts pc
                JOIN aliados a_cont ON a_cont.id = pc.contratante_id
                JOIN aliados a_prof ON a_prof.id = pc.profesional_id
                WHERE pc.estado IN ('PENDIENTE_PRUEBA', 'EN_REVISION')
                ORDER BY pc.created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
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
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
            if not cursor.fetchone():
                conn.close()
                return None
            cursor.execute(
                "SELECT id FROM aliados WHERE codigo = ?", (codigo_aliado,)
            )
            r = cursor.fetchone()
            if not r:
                conn.close()
                return None
            aliado_id = r[0]
            cursor.execute("""
                SELECT id, trabajo_id, contratante_id, profesional_id, importe_contratante, importe_profesional,
                       estado, prueba_url, comentario_admin, created_at, updated_at
                FROM payment_conflicts
                WHERE trabajo_id = ? AND (contratante_id = ? OR profesional_id = ?)
            """, (trabajo_id, aliado_id, aliado_id))
            row = cursor.fetchone()
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
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
            if not cursor.fetchone():
                conn.close()
                return None
            cursor.execute("""
                SELECT pc.id, pc.trabajo_id, pc.contratante_id, pc.profesional_id,
                       pc.importe_contratante, pc.importe_profesional, pc.estado,
                       pc.prueba_url, pc.comentario_admin, pc.created_at, pc.updated_at,
                       a_cont.nombre AS contratante_nombre, a_cont.codigo AS contratante_codigo,
                       a_prof.nombre AS profesional_nombre, a_prof.codigo AS profesional_codigo
                FROM payment_conflicts pc
                JOIN aliados a_cont ON a_cont.id = pc.contratante_id
                JOIN aliados a_prof ON a_prof.id = pc.profesional_id
                WHERE pc.id = ?
            """, (conflict_id,))
            row = cursor.fetchone()
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
            cursor.execute("""
                SELECT id, trabajo_id, importe_contratante, importe_profesional, estado
                FROM payment_conflicts WHERE id = ?
            """, (conflict_id,))
            row = cursor.fetchone()
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
            cursor.execute("""
                UPDATE payment_conflicts SET estado = ?, comentario_admin = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (nuevo_estado, (comentario or "").strip()[:2000], conflict_id))
            if importe_valido is not None and trabajo_id:
                cursor.execute(
                    "SELECT id, solicitante_codigo, profesional_codigo, estado FROM contactos_ruana WHERE id = ?",
                    (trabajo_id,)
                )
                c = cursor.fetchone()
                if c and dict(c).get('estado') == 'importe_en_disputa':
                    d = dict(c)
                    pct = db._get_apoyo_pct()
                    apoyo = round(importe_valido * pct / 100.0, 2)
                    comision_pct = pct / 100.0
                    estado_pago_final = 'pendiente_pago' if apoyo > 0 else 'no_generado'
                    pendiente_pago_final = 1 if apoyo > 0 else 0
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET estado = 'trabajo_cerrado', pendiente_resolucion = 0,
                            importe_final = ?, comision = ?, comision_porcentaje = ?,
                            apoyo_ruana = ?, estado_pago = ?, pendiente_pago = ?,
                            fecha_cierre = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (importe_valido, apoyo, comision_pct, apoyo, estado_pago_final, pendiente_pago_final, trabajo_id))
                    cerro_contacto_disputa = True
                    if apoyo > 0:
                        cursor.execute(
                            "INSERT INTO ingresos_ruana (contacto_id, importe_final, apoyo_ruana_2pct) VALUES (?, ?, ?)",
                            (trabajo_id, importe_valido, apoyo)
                        )
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
                        cursor.execute(
                            "SELECT qr_paypal_path, bizum_num FROM aliados WHERE codigo = ?",
                            (prof_codigo,)
                        )
                        row_aliado = cursor.fetchone()
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
                        cursor.execute("""
                            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                            VALUES (?, 'apoyo_ruana', 'Apoyo a RUANA', ?, ?, 0)
                        """, (prof_codigo, mensaje, meta))
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
            cursor.execute(
                "SELECT id, solicitante_codigo, profesional_codigo, estado FROM contactos_ruana WHERE id = ?",
                (contacto_id,)
            )
            row = cursor.fetchone()
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
            cursor.execute("""
                UPDATE contactos_ruana
                SET estado = 'trabajo_cerrado', pendiente_resolucion = 0,
                    importe_final = ?, comision = ?, comision_porcentaje = ?,
                    apoyo_ruana = ?, estado_pago = 'pendiente_pago', pendiente_pago = 1,
                    fecha_cierre = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (imp, apoyo, comision_pct, apoyo, contacto_id))
            cursor.execute(
                "INSERT INTO ingresos_ruana (contacto_id, importe_final, apoyo_ruana_2pct) VALUES (?, ?, ?)",
                (contacto_id, imp, apoyo)
            )
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
                cursor.execute(
                    "SELECT qr_paypal_path, bizum_num FROM aliados WHERE codigo = ?",
                    (prof_codigo,)
                )
                row_aliado = cursor.fetchone()
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
                cursor.execute("""
                    INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                    VALUES (?, 'apoyo_ruana', 'Apoyo a RUANA', ?, ?, 0)
                """, (prof_codigo, mensaje, meta))
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
            cursor.execute("""
                SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio,
                       c.importe_final, c.apoyo_ruana, c.estado_pago, c.pendiente_pago, c.fecha_cierre,
                       c.comprobante_ruta,
                       COALESCE(c.es_urgente, 0) AS es_urgente, c.urgente_marcado_en, c.creado_en,
                       a_sol.nombre AS solicitante_nombre, a_prof.nombre AS profesional_nombre
                FROM contactos_ruana c
                LEFT JOIN aliados a_sol ON a_sol.codigo = c.solicitante_codigo
                LEFT JOIN aliados a_prof ON a_prof.codigo = c.profesional_codigo
                WHERE c.estado = 'trabajo_cerrado' AND c.importe_final IS NOT NULL
                  AND COALESCE(c.apoyo_ruana, 0) > 0
                ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
            """)
            lista = [dict(row) for row in cursor.fetchall()]
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
            cursor.execute("""
                SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio,
                       c.importe_final, c.apoyo_ruana, c.estado_pago, c.comprobante_ruta, c.fecha_cierre,
                       a_prof.nombre AS profesional_nombre
                FROM contactos_ruana c
                LEFT JOIN aliados a_prof ON a_prof.codigo = c.profesional_codigo
                WHERE c.estado = 'trabajo_cerrado' AND c.importe_final IS NOT NULL
                  AND c.estado_pago = 'en_revision'
                  AND COALESCE(c.apoyo_ruana, 0) > 0
                ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
            """)
            lista = [dict(row) for row in cursor.fetchall()]
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
            cursor.execute("""
                SELECT id, estado, importe_final, estado_pago, pendiente_pago,
                       solicitante_codigo, profesional_codigo
                FROM contactos_ruana WHERE id = ?
            """, (contacto_id,))
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            r = dict(row)
            if r['estado'] != 'trabajo_cerrado' or r['importe_final'] is None:
                return {'status': 'error', 'message': 'El contacto no tiene Apoyo RUANA generado'}
            estado_anterior = (r.get('estado_pago') or '').strip().lower()
            if nuevo_estado == 'pagado':
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado_pago = 'pagado', pendiente_pago = 0,
                        fecha_validacion_pago = CURRENT_TIMESTAMP,
                        admin_validacion_codigo = ?,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (admin_codigo or None, contacto_id))
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
                    cursor.execute("""
                        INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                        VALUES (?, 'pago_aceptado', 'Pago aceptado', ?, ?, 1)
                    """, (prof_codigo, mensaje, meta))
                # Regla 2: encargo completado al confirmar Apoyo pagado (+2 a ambos)
                if estado_anterior != 'pagado':
                    sol_codigo = str(r.get('solicitante_codigo') or '').strip()
                    if sol_codigo:
                        participantes_regla2.append(sol_codigo)
                    if prof_codigo:
                        participantes_regla2.append(prof_codigo)
            elif nuevo_estado == 'rechazado':
                motivo = (motivo_rechazo or "").strip()[:2000]
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado_pago = 'pendiente_pago', pendiente_pago = 1,
                        motivo_rechazo_pago = ?, comprobante_ruta = NULL,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (motivo, contacto_id))
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
                    cursor.execute("""
                        INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                        VALUES (?, 'pago_rechazado', 'Comprobante de pago rechazado', ?, ?, 0)
                    """, (prof_codigo, mensaje, meta))
            else:
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado_pago = ?, pendiente_pago = ?,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (nuevo_estado, 1 if nuevo_estado != 'pagado' else 0, contacto_id))
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
            cursor.execute("""
                SELECT 1 FROM contactos_ruana
                WHERE profesional_codigo = ? AND estado = 'trabajo_cerrado'
                  AND importe_final IS NOT NULL AND estado_pago = 'pendiente_pago'
                  AND COALESCE(apoyo_ruana, 0) > 0
                LIMIT 1
            """, (codigo_profesional.strip(),))
            return cursor.fetchone() is not None
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
            cursor.execute("""
                SELECT id, solicitante_codigo, profesional_codigo, estado, importe_final,
                       estado_pago, pendiente_pago
                FROM contactos_ruana
                WHERE id = ?
            """, (contacto_id,))
            row = cursor.fetchone()
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
            cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (solicitante_codigo,))
            r_sol = cursor.fetchone()
            cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (prof_norm,))
            r_prof = cursor.fetchone()
            if not r_sol or not r_prof:
                return {'status': 'error', 'message': 'No se pudo identificar a las partes del contacto'}

            cursor.execute("""
                UPDATE contactos_ruana
                SET estado = 'importe_en_disputa', pendiente_resolucion = 1,
                    estado_pago = 'no_generado', pendiente_pago = 0,
                    fecha_disputa = COALESCE(fecha_disputa, CURRENT_TIMESTAMP),
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (contacto_id,))
            db._marcar_notificaciones_contacto_leidas(
                cursor, prof_norm, contacto_id, tipos=['apoyo_ruana', 'pago_rechazado']
            )
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
            if cursor.fetchone():
                cursor.execute("SELECT id FROM payment_conflicts WHERE trabajo_id = ?", (contacto_id,))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute("""
                        UPDATE payment_conflicts
                        SET contratante_id = ?, profesional_id = ?, importe_contratante = ?,
                            importe_profesional = 0, estado = 'PENDIENTE_PRUEBA',
                            prueba_url = NULL, comentario_admin = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (r_sol[0], r_prof[0], importe_final, (motivo or "").strip()[:2000] or None, existing[0]))
                else:
                    cursor.execute("""
                        INSERT INTO payment_conflicts (trabajo_id, contratante_id, profesional_id,
                            importe_contratante, importe_profesional, estado, comentario_admin,
                            created_at, updated_at)
                        VALUES (?, ?, ?, ?, 0, 'PENDIENTE_PRUEBA', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (contacto_id, r_sol[0], r_prof[0], importe_final, (motivo or "").strip()[:2000] or None))

            db._audit_log(cursor, 'contacto', contacto_id, 'apoyo_impugnado',
                            'aliado', prof_norm, (motivo or 'importe impugnado')[:500])
            mensaje = (
                f"El profesional ha impugnado el importe declarado para el contacto #{contacto_id}. "
                "Adjunta documentación o comprobantes para que RUANA pueda validarlo."
            )
            meta = json.dumps({'contacto_id': contacto_id, 'importe_declarado': importe_final}, ensure_ascii=False)
            cursor.execute("""
                INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                VALUES (?, 'importe_impugnado', 'Importe impugnado', ?, ?, 0)
            """, (solicitante_codigo, mensaje, meta))
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
            cursor.execute("""
                SELECT c.id, c.servicio, c.importe_final, c.apoyo_ruana, c.estado_pago, c.pendiente_pago,
                       c.fecha_cierre, c.solicitante_codigo,
                       a_sol.nombre AS solicitante_nombre
                FROM contactos_ruana c
                LEFT JOIN aliados a_sol ON a_sol.codigo = c.solicitante_codigo
                WHERE TRIM(CAST(c.profesional_codigo AS TEXT)) = ? AND c.estado = 'trabajo_cerrado'
                  AND c.importe_final IS NOT NULL AND c.estado_pago = 'pendiente_pago'
                  AND COALESCE(c.apoyo_ruana, 0) > 0
                ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
            """, (codigo_norm,))
            lista = [dict(row) for row in cursor.fetchall()]
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
            cursor.execute("""
                SELECT id, profesional_codigo, estado_pago, apoyo_ruana
                FROM contactos_ruana
                WHERE id = ? AND estado = 'trabajo_cerrado' AND importe_final IS NOT NULL
            """, (contacto_id,))
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Contacto no encontrado'}
            r = dict(row)
            if (r['profesional_codigo'] or '').strip() != (profesional_codigo or '').strip():
                return {'status': 'error', 'message': 'Solo el profesional del contacto puede subir el comprobante'}
            if (r['estado_pago'] or '') != 'pendiente_pago':
                return {'status': 'error', 'message': 'Este contacto no tiene el pago en estado pendiente'}
            cursor.execute("""
                UPDATE contactos_ruana
                SET comprobante_ruta = ?, estado_pago = 'en_revision', actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (comprobante_ruta, contacto_id))
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
            cursor.execute("""
                SELECT pc.id, pc.trabajo_id, pc.contratante_id, a.codigo AS contratante_codigo
                FROM payment_conflicts pc
                JOIN aliados a ON a.id = pc.contratante_id
                WHERE pc.id = ?
            """, (conflict_id,))
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Conflicto no encontrado'}
            conflicto = dict(row)
            cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (contratante_codigo,))
            r_aliado = cursor.fetchone()
            if not r_aliado or r_aliado[0] != conflicto['contratante_id']:
                return {'status': 'error', 'message': 'Solo el contratante puede subir la prueba'}
            cursor.execute("""
                UPDATE payment_conflicts SET estado = 'EN_REVISION', prueba_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (prueba_url, conflict_id))
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
            cursor.execute("""
                INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                VALUES (?, 'prueba_conflicto_en_revision', 'Documentacion en revision', ?, ?, 0)
            """, (contratante_norm, mensaje, meta))
            conn.commit()
            return {'status': 'success', 'id': conflict_id, 'estado': 'EN_REVISION'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

