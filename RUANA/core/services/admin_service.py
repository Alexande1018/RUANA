"""Servicio de dominio admin (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de admin vía AdminRepo.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.db_constants import RUANA_ROOT

import json
import sqlite3
from typing import Any, Dict, List, Optional

from core.repositories.admin_repo import AdminRepo

_repo = AdminRepo()

# --- Extraído de DBManager (admin) ---

def obtener_o_crear_invitador_admin(db, admin_codigo: str, nombre: str = "") -> Optional[str]:
    """
    Garantiza un aliado 'sistema' para representar al admin como invitador en referidos.
    Necesario porque referidos.codigo_invitador tiene FK a aliados(codigo).
    """
    admin_codigo = (admin_codigo or "").strip() or "RUANA-ADMIN"
    existente = db.obtener_aliado_por_codigo(admin_codigo)
    if existente:
        return admin_codigo
    nombre_final = (nombre or "").strip() or f"Administrador ({admin_codigo})"
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            _repo.insertar_invitador_admin(cursor, admin_codigo, nombre_final)
            conn.commit()
            return admin_codigo
        except Exception:
            return None
        finally:
            if conn:
                conn.close()

def listar_conversaciones_soporte_admin(db, aliado_codigo: str = '', estado: str = '',
                                        solo_no_leidas: bool = False, limite: int = 100,
                                        offset: int = 0) -> List[Dict[str, Any]]:
    aliado_f = str(aliado_codigo or '').strip()
    estado_f = str(estado or '').strip().lower()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            where = ["COALESCE(c.eliminada_por_admin, 0) = 0"]
            params: List[Any] = []
            if aliado_f:
                where.append("LOWER(TRIM(CAST(c.aliado_codigo AS TEXT))) LIKE ?")
                params.append(f"%{aliado_f.lower()}%")
            if estado_f:
                where.append("LOWER(TRIM(COALESCE(c.estado, ''))) = ?")
                params.append(estado_f)
            if solo_no_leidas:
                where.append("COALESCE(c.tiene_no_leido_admin, 0) = 1")
            params.extend([max(1, min(int(limite or 100), 300)), max(0, int(offset or 0))])
            return [dict(r) for r in _repo.listar_conversaciones_soporte(cursor, ' AND '.join(where), params)]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

def responder_soporte_admin(db, conversacion_id: int, admin_codigo: str, mensaje: str,
                              nuevo_estado: Optional[str] = None) -> Dict[str, Any]:
    msg = str(mensaje or '').strip()
    if not msg:
        return {'status': 'error', 'message': 'Mensaje requerido'}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT aliado_codigo, asunto FROM ruana_soporte_conversaciones WHERE id = ? AND COALESCE(eliminada_por_admin, 0) = 0",
                (int(conversacion_id),),
            )
            conv = cursor.fetchone()
            if not conv:
                return {'status': 'error', 'message': 'Conversación no encontrada'}
            estado = (nuevo_estado or '').strip().lower()
            if estado not in ('pendiente', 'en_revision', 'respondido', 'cerrado', 'reabierto'):
                estado = 'respondido'
            admin_code = (admin_codigo or '').strip() or 'admin'
            cursor.execute("""
                INSERT INTO ruana_soporte_mensajes
                    (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
                VALUES (?, 'admin', ?, ?, 0, 1)
            """, (int(conversacion_id), admin_code, msg))
            cursor.execute("""
                UPDATE ruana_soporte_conversaciones
                SET estado = ?, ultimo_mensaje_preview = ?, ultimo_mensaje_en = CURRENT_TIMESTAMP,
                    actualizado_en = CURRENT_TIMESTAMP, tiene_no_leido_aliado = 1, tiene_no_leido_admin = 0
                WHERE id = ?
            """, (estado, msg[:220], int(conversacion_id)))
            cursor.execute("""
                INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                VALUES (?, 'ruana_soporte', '📩 Respuesta del equipo RUANA', ?, ?, 0)
            """, (
                (conv['aliado_codigo'] or '').strip(),
                f"Tu conversación #{int(conversacion_id)} tiene una respuesta nueva.",
                json.dumps({'conversacion_id': int(conversacion_id), 'estado': estado, 'origen': 'centro_soporte'}),
            ))
            conn.commit()
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()


def actualizar_estado_soporte_admin(db, conversacion_id: int, nuevo_estado: str, admin_codigo: str = '') -> Dict[str, Any]:
    estado = (nuevo_estado or '').strip().lower()
    if estado not in ('pendiente', 'en_revision', 'respondido', 'cerrado', 'reabierto'):
        return {'status': 'error', 'message': 'Estado inválido'}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            conv = _repo.select_soporte_aliado_codigo(cursor, conversacion_id)
            if not conv:
                return {'status': 'error', 'message': 'Conversación no encontrada'}
            _repo.update_estado_soporte(cursor, estado, conversacion_id)
            _repo.insertar_notif_estado_soporte(
                cursor,
                (conv['aliado_codigo'] or '').strip(),
                f"La conversación #{int(conversacion_id)} ahora está en estado: {estado.replace('_', ' ')}.",
                json.dumps({'conversacion_id': int(conversacion_id), 'estado': estado, 'origen': 'centro_soporte'}),
            )
            conn.commit()
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def eliminar_conversacion_soporte_admin(db, conversacion_id: int, admin_codigo: str = '') -> Dict[str, Any]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            _repo.soft_delete_soporte(cursor, conversacion_id)
            conn.commit()
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def listar_conversaciones_admin(db, limite: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Lista contactos con sus mensajes para GET /api/admin/chats (paginado).
    Orden: más recientes primero. LIMIT y OFFSET para carga progresiva.
    """
    offset = max(0, offset)
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            contactos = [dict(row) for row in _repo.listar_contactos_chats(cursor, limite, offset)]
            for c in contactos:
                c['es_urgente'] = bool(int(c.get('es_urgente') or 0))
            if not contactos:
                return []
            ids = [c["contacto_id"] for c in contactos]
            # Solo mensajes con contacto_id válido (siempre en chat_mensajes)
            filas_msg = _repo.listar_mensajes_contactos(cursor, ids)
            mensajes_por_contacto = {}
            for c in contactos:
                mensajes_por_contacto[c["contacto_id"]] = []
            for row in filas_msg:
                r = dict(row)
                cid = r["contacto_id"]
                if cid not in mensajes_por_contacto:
                    continue
                contacto = next((x for x in contactos if x["contacto_id"] == cid), None)
                sol = (contacto.get("solicitante_codigo") or "").strip()
                pro = (contacto.get("profesional_codigo") or "").strip()
                emisor = (r.get("emisor_codigo") or "").strip()
                remitente = "solicitante" if emisor == sol else ("profesional" if emisor == pro else "aliado")
                mensajes_por_contacto[cid].append({
                    "id": r.get("id"),
                    "texto": r.get("texto"),
                    "fecha": r.get("creado_en"),
                    "remitente": remitente,
                    "emisor_codigo": emisor,
                })
            out = []
            for c in contactos:
                cid = c["contacto_id"]
                num_m = c.get("num_mensajes") or 0
                ultimo = (c.get("ultimo_mensaje") or "").strip()
                fecha_ultimo = c.get("fecha_ultimo")
                if not ultimo and num_m == 0:
                    ultimo = "Sin mensajes aún"
                if not fecha_ultimo:
                    fecha_ultimo = c.get("contacto_creado_en")
                out.append({
                    "contacto_id": cid,
                    "solicitante": c.get("solicitante") or c.get("solicitante_codigo") or "",
                    "profesional": c.get("profesional") or c.get("profesional_codigo") or "",
                    "ultimo_mensaje": ultimo,
                    "fecha_ultimo": fecha_ultimo,
                    "num_mensajes": num_m,
                    "es_urgente": bool(c.get("es_urgente")),
                    "urgente_marcado_en": c.get("urgente_marcado_en"),
                    "motivo_contacto": c.get("motivo_contacto"),
                    "mensajes": mensajes_por_contacto.get(cid, []),
                })
            return out
        except Exception as e:
            print(f"Error listar_conversaciones_admin: {e}")
            return []
        finally:
            conn.close()

def obtener_metricas_contactos(db) -> Dict[str, Any]:
    """
    Calcula métricas agregadas de contactos RUANA para usar en dashboards y motor de riesgo.
    - contactos_abiertos: en estados iniciado/aceptado/trabajo_en_progreso
    - contactos_no_resueltos: pendientes de resolución (flag)
    - contactos_en_disputa: estado importe_en_disputa
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            _repo.execute(cursor, """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso')
            """)
            abiertos = cursor.fetchone()[0] or 0

            _repo.execute(cursor, """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE pendiente_resolucion = 1
            """)
            no_resueltos = cursor.fetchone()[0] or 0

            _repo.execute(cursor, """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE estado = 'importe_en_disputa'
            """)
            en_disputa = cursor.fetchone()[0] or 0

            # Contactos en disputa "prolongada": más de 7 días desde fecha_disputa
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE estado = 'importe_en_disputa'
                  AND fecha_disputa IS NOT NULL
                  AND julianday('now') - julianday(fecha_disputa) >= 7
            """)
            disputa_prolongada = cursor.fetchone()[0] or 0

            return {
                'status': 'success',
                'contactos_abiertos': abiertos,
                'contactos_no_resueltos': no_resueltos,
                'contactos_en_disputa': en_disputa,
                'contactos_en_disputa_prolongada': disputa_prolongada
            }
        except Exception as e:
            print(f"Error obteniendo métricas de contactos: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
        finally:
            conn.close()

def obtener_metricas_motor_por_aliado(db, codigo_aliado: str) -> Dict[str, Any]:
    """
    Métricas desde contactos_ruana para el motor de evaluación (tasa_respuesta, tasa_confirmacion, meses_sin_trabajo).
    - tasa_respuesta: como profesional, proporción de contactos que salieron de 'iniciado' (aceptó o más).
    - tasa_confirmacion: como profesional, proporción de contactos aceptados que llegaron a trabajo_cerrado o no_concretado.
    - meses_sin_trabajo: meses desde el último trabajo_cerrado (como profesional o solicitante); si no hay ninguno, 24.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            codigo = (codigo_aliado or '').strip()
            if not codigo:
                return {"tasa_respuesta": 0.0, "tasa_confirmacion": 0.0, "meses_sin_trabajo": 24}

            # Contactos donde es profesional
            rows_pro = _repo.select_estados_profesional(cursor, codigo)
            total_pro = len(rows_pro)
            estados_pro = [r[0] for r in rows_pro if r[0]]

            responded = sum(1 for e in estados_pro if e and e != 'iniciado')
            tasa_respuesta = (responded / total_pro) if total_pro > 0 else 1.0

            total_aceptados = sum(1 for e in estados_pro if e in (
                'aceptado', 'trabajo_en_progreso', 'trabajo_cerrado', 'no_concretado', 'importe_en_disputa'))
            cerrados = sum(1 for e in estados_pro if e in ('trabajo_cerrado', 'no_concretado'))
            tasa_confirmacion = (cerrados / total_aceptados) if total_aceptados > 0 else 1.0

            # Meses desde último trabajo_cerrado (como profesional o solicitante); SQLite julianday
            row = _repo.select_meses_sin_trabajo(cursor, codigo)
            meses_sin_trabajo = 24
            if row and row[0] is not None:
                try:
                    m = float(row[0])
                    meses_sin_trabajo = max(0, int(round(m)))
                except (TypeError, ValueError):
                    meses_sin_trabajo = 24

            return {
                "tasa_respuesta": round(tasa_respuesta, 4),
                "tasa_confirmacion": round(tasa_confirmacion, 4),
                "meses_sin_trabajo": meses_sin_trabajo,
            }
        except Exception:
            return {"tasa_respuesta": 0.0, "tasa_confirmacion": 0.0, "meses_sin_trabajo": 24}
        finally:
            try:
                conn.close()
            except Exception:
                pass

def obtener_stats_24h_admin(db) -> Dict[str, Any]:
    """
    Stats 24h para GET /api/admin/stats-24h.
    Sin datos simulados. Calcula:
    - solicitudes_nuevas: creadas en últimas 24h
    - solicitudes_atendidas: contestadas creadas en 24h
    - solicitudes_sin_respuesta: pendientes creadas en 24h (sin atender aún)
    - invitaciones_generadas: creadas en 24h (invitaciones + invitaciones_oficio)
    - invitaciones_usadas: usadas en 24h (referidos + invitaciones_oficio usadas)
    - invitaciones_expiradas: no usadas y creadas hace >30 días (umbral por defecto)
    """
    conn = None
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            col_ts_sol = "created_at"
            try:
                if 'created_at' not in _repo.columnas_tabla(cursor, 'solicitudes'):
                    col_ts_sol = "creado_en"
            except Exception:
                pass
            filtro_24h_sol = f"datetime({col_ts_sol}) >= datetime('now', '-1 day')"
            estado_atendida = "atendida"
            try:
                if 'atendido_por_codigo' not in _repo.columnas_tabla(cursor, 'solicitudes'):
                    estado_atendida = "contestada"
            except Exception:
                pass

            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE {filtro_24h_sol}")
            solicitudes_nuevas = cursor.fetchone()[0] or 0
            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE estado = ? AND {filtro_24h_sol}", (estado_atendida,))
            solicitudes_atendidas = cursor.fetchone()[0] or 0
            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente' AND {filtro_24h_sol}")
            solicitudes_sin_respuesta = cursor.fetchone()[0] or 0

            # Invitaciones generadas 24h: invitaciones (aliado) + invitaciones_oficio
            filtro_24h = "datetime(creado_en) >= datetime('now', '-1 day')"
            _repo.execute(cursor, f"""
                SELECT COUNT(*) FROM invitaciones
                WHERE {filtro_24h}
            """)
            inv_aliado_gen = cursor.fetchone()[0] or 0
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM invitaciones_oficio
                WHERE datetime(fecha_creacion) >= datetime('now', '-1 day')
            """)
            inv_oficio_gen = cursor.fetchone()[0] or 0
            invitaciones_generadas = inv_aliado_gen + inv_oficio_gen

            # Invitaciones usadas 24h: referidos.creado_en + invitaciones_oficio marcadas usado en 24h
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM referidos
                WHERE datetime(creado_en) >= datetime('now', '-1 day')
            """)
            invitaciones_usadas = cursor.fetchone()[0] or 0
            # invitaciones_oficio no tiene timestamp de uso; contar por alias: no hay tabla de uso
            # Solo referidos refleja invitación aliado usada. invitaciones_oficio: al consumir se cambia estado
            # sin timestamp. Por simplicidad, invitaciones_usadas = referidos en 24h.
            # invitaciones_oficio usadas: no hay created_at del uso. Omitir por ahora.

            # Invitaciones expiradas: no usadas, creadas hace >30 días (regla de negocio)
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM invitaciones
                WHERE usado = 0 AND datetime(creado_en) < datetime('now', '-30 day')
            """)
            exp_aliado = cursor.fetchone()[0] or 0
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM invitaciones_oficio
                WHERE estado = 'pendiente' AND datetime(fecha_creacion) < datetime('now', '-30 day')
            """)
            exp_oficio = cursor.fetchone()[0] or 0
            invitaciones_expiradas = exp_aliado + exp_oficio

            return {
                'solicitudes_nuevas': solicitudes_nuevas,
                'solicitudes_atendidas': solicitudes_atendidas,
                'solicitudes_sin_respuesta': solicitudes_sin_respuesta,
                'invitaciones_generadas': invitaciones_generadas,
                'invitaciones_usadas': invitaciones_usadas,
                'invitaciones_expiradas': invitaciones_expiradas,
            }
        except Exception as e:
            print(f"Error obtener_stats_24h_admin: {e}")
            return {
                'solicitudes_nuevas': 0,
                'solicitudes_atendidas': 0,
                'solicitudes_sin_respuesta': 0,
                'invitaciones_generadas': 0,
                'invitaciones_usadas': 0,
                'invitaciones_expiradas': 0,
            }
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

def obtener_stats_24h_panel(db) -> Dict[str, Any]:
    """
    Métricas 24h en formato para el panel admin (endpoint único GET /api/admin/stats-24h).
    limite = now - 24 hours. Devuelve: solicitudes, invitaciones, top_invitadores.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            limite = "datetime('now', '-1 day')"

            # Solicitudes: nuevas, atendidas, sin_respuesta (compatible con tabla unificada)
            try:
                cols_sol = _repo.columnas_tabla(cursor, 'solicitudes')
                col_ts_s = "created_at" if 'created_at' in cols_sol else "creado_en"
                estado_at = "atendida" if 'atendido_por_codigo' in cols_sol else "contestada"
            except Exception:
                col_ts_s, estado_at = "creado_en", "contestada"
            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE datetime({col_ts_s}) >= {limite}")
            nuevas = cursor.fetchone()[0] or 0
            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE estado = ? AND datetime({col_ts_s}) >= {limite}", (estado_at,))
            atendidas = cursor.fetchone()[0] or 0
            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente' AND datetime({col_ts_s}) >= {limite}")
            sin_respuesta = cursor.fetchone()[0] or 0

            # Invitaciones: generadas (invitaciones + invitaciones_oficio), usadas (referidos 24h), expiradas
            _repo.execute(cursor, f"""
                SELECT COUNT(*) FROM invitaciones
                WHERE datetime(creado_en) >= {limite}
            """)
            inv_gen = cursor.fetchone()[0] or 0
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM invitaciones_oficio
                WHERE datetime(fecha_creacion) >= datetime('now', '-1 day')
            """)
            inv_oficio = cursor.fetchone()[0] or 0
            generadas = inv_gen + inv_oficio

            _repo.execute(cursor, f"""
                SELECT COUNT(*) FROM referidos
                WHERE datetime(creado_en) >= {limite}
            """)
            usadas = cursor.fetchone()[0] or 0

            _repo.execute(cursor, """
                SELECT COUNT(*) FROM invitaciones
                WHERE usado = 0 AND datetime(creado_en) < datetime('now', '-30 day')
            """)
            exp_a = cursor.fetchone()[0] or 0
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM invitaciones_oficio
                WHERE estado = 'pendiente' AND datetime(fecha_creacion) < datetime('now', '-30 day')
            """)
            exp_o = cursor.fetchone()[0] or 0
            expiradas = exp_a + exp_o

            # Top invitadores 24h: por referidos en 24h, agrupar por codigo_invitador
            _repo.execute(cursor, f"""
                SELECT r.codigo_invitador, COUNT(*) AS total
                FROM referidos r
                WHERE datetime(r.creado_en) >= {limite}
                GROUP BY r.codigo_invitador
                ORDER BY total DESC
                LIMIT 3
            """)
            rows = cursor.fetchall()
            top_invitadores = []
            for (codigo_inv, total) in rows:
                rn = _repo.select_nombre_aliado(cursor, codigo_inv or '')
                nombre = (rn[0] or codigo_inv or '—') if rn else (codigo_inv or '—')
                top_invitadores.append({'nombre': nombre, 'total': total})

            return {
                'solicitudes': {'nuevas': nuevas, 'atendidas': atendidas, 'sin_respuesta': sin_respuesta},
                'invitaciones': {'generadas': generadas, 'usadas': usadas, 'expiradas': expiradas},
                'top_invitadores': top_invitadores,
            }
        except Exception as e:
            print(f"Error obtener_stats_24h_panel: {e}")
            return {
                'solicitudes': {'nuevas': 0, 'atendidas': 0, 'sin_respuesta': 0},
                'invitaciones': {'generadas': 0, 'usadas': 0, 'expiradas': 0},
                'top_invitadores': [],
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

def obtener_metricas_salud(db) -> Dict[str, Any]:
    """
    Cruce aliados, contactos, evaluaciones, invitaciones para métricas de salud del panel admin.
    Devuelve, usando datos reales de la BD:
    - Ratio Solicitud → Invitación  = solicitudes que generaron invitación / total solicitudes
    - Ratio Invitación → Registro   = invitaciones usadas (usado=1) / total invitaciones
    - Oficios Saturados            = nº oficios cuyo nº de aliados activos supera umbral (p.ej. ≥3)
    - Oficios Disponibles          = total oficios catálogo − oficios saturados
    - Zona Mayor Demanda           = código postal con más solicitudes pendientes
    - Tasa Retención Aliados       = aliados con ≥1 trabajo completado / total aliados (en %)
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            # Totales básicos
            total_aliados = _repo.contar(cursor, "SELECT COUNT(*) FROM aliados")
            total_solicitudes = _repo.contar(cursor, "SELECT COUNT(*) FROM solicitudes")
            total_invitaciones = _repo.contar(cursor, "SELECT COUNT(*) FROM invitaciones")
            _repo.execute(cursor, "SELECT COUNT(*) FROM invitaciones WHERE usado = 1")
            invitaciones_usadas = cursor.fetchone()[0] or 0

            # Solicitudes que "generaron" invitación:
            # aproximación: solicitudes cuyo solicitante es un aliado que ha generado al menos una invitación.
            _repo.execute(cursor, """
                SELECT COUNT(DISTINCT s.id)
                FROM solicitudes s
                JOIN aliados a ON s.solicitante_codigo = a.codigo
                JOIN invitaciones i ON i.invitador_aliado_id = a.id
            """)
            solicitudes_con_invitacion = cursor.fetchone()[0] or 0

            ratio_solicitud_invitacion = round(solicitudes_con_invitacion / max(total_solicitudes, 1), 2)
            ratio_invitacion_registro = round(invitaciones_usadas / max(total_invitaciones, 1), 2)

            # Oficios saturados / disponibles
            catalogo = db.get_catalogo_oficios_ruana()
            total_oficios_catalogo = len(catalogo) if catalogo else 0

            # Oficio saturado: >= 3 aliados activos con ese oficio (a nivel global)
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM (
                    SELECT oficio
                    FROM aliados
                    WHERE estado = 'activo' AND oficio IS NOT NULL AND TRIM(oficio) != ''
                    GROUP BY oficio
                    HAVING COUNT(*) >= 3
                )
            """)
            num_oficios_saturados = cursor.fetchone()[0] or 0

            oficios_disponibles = 0
            if total_oficios_catalogo > 0:
                oficios_disponibles = max(total_oficios_catalogo - num_oficios_saturados, 0)

            # Zona mayor demanda: CP con más solicitudes pendientes
            _repo.execute(cursor, """
                SELECT g.codigo_postal, COUNT(*) as c
                FROM solicitudes s
                JOIN grupos g ON s.grupo_id = g.id
                WHERE s.estado = 'pendiente' AND g.codigo_postal IS NOT NULL AND g.codigo_postal != ''
                GROUP BY codigo_postal
                ORDER BY c DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            zona_mayor_demanda = (row[0] or '—') if row else '—'

            # Retención: aliados que han completado al menos 1 trabajo (contacto con cierre/no_concretado)
            _repo.execute(cursor, """
                SELECT COUNT(DISTINCT codigo) FROM aliados
                WHERE codigo IN (
                    SELECT solicitante_codigo
                    FROM contactos_ruana
                    WHERE (fecha_cierre IS NOT NULL OR fecha_no_concretado IS NOT NULL)
                    UNION
                    SELECT profesional_codigo
                    FROM contactos_ruana
                    WHERE (fecha_cierre IS NOT NULL OR fecha_no_concretado IS NOT NULL)
                )
            """)
            aliados_con_trabajo = cursor.fetchone()[0] or 0

            tasa_retencion = round(100.0 * aliados_con_trabajo / max(total_aliados, 1), 1)

            return {
                'ratio_solicitud_invitacion': ratio_solicitud_invitacion,
                'ratio_invitacion_registro': ratio_invitacion_registro,
                'oficios_saturados': num_oficios_saturados,
                'oficios_disponibles': oficios_disponibles,
                'zona_mayor_demanda': zona_mayor_demanda,
                'tasa_retencion': tasa_retencion,
            }
        except Exception as e:
            print(f"Error obtener_metricas_salud: {e}")
            return {
                'ratio_solicitud_invitacion': 0,
                'ratio_invitacion_registro': 0,
                'oficios_saturados': 0,
                'oficios_disponibles': 0,
                'zona_mayor_demanda': '—',
                'tasa_retencion': 0,
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

def obtener_health_metrics_admin(db, umbral_suplentes: int = 1) -> Dict[str, Any]:
    """
    Métricas de salud para GET /api/admin/health-metrics.
    - ratio_solicitud_invitacion: solicitudes que generaron invitación / total solicitudes
    - ratio_invitacion_registro: invitaciones usadas / total invitaciones
    - oficios_saturados: oficios con más de X suplentes en competencia activa (X=umbral_suplentes)
    - oficios_disponibles: plazas sin titular (grupo+oficio sin aliado, no cerrada)
    - zona_mayor_demanda: código postal con más solicitudes pendientes
    - tasa_retencion: usuarios activos / total usuarios (en %)
    """
    conn = None
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            # Totales
            total_aliados = _repo.contar(cursor, "SELECT COUNT(*) FROM aliados")
            _repo.execute(cursor, "SELECT COUNT(*) FROM aliados WHERE estado = 'activo'")
            aliados_activos = cursor.fetchone()[0] or 0
            total_solicitudes = _repo.contar(cursor, "SELECT COUNT(*) FROM solicitudes")
            total_invitaciones = _repo.contar(cursor, "SELECT COUNT(*) FROM invitaciones")
            _repo.execute(cursor, "SELECT COUNT(*) FROM invitaciones WHERE usado = 1")
            invitaciones_usadas = cursor.fetchone()[0] or 0

            # Ratio solicitud → invitación
            _repo.execute(cursor, """
                SELECT COUNT(DISTINCT s.id) FROM solicitudes s
                JOIN aliados a ON s.solicitante_codigo = a.codigo
                JOIN invitaciones i ON i.invitador_aliado_id = a.id
            """)
            solicitudes_con_invitacion = cursor.fetchone()[0] or 0
            ratio_solicitud_invitacion = round(solicitudes_con_invitacion / max(total_solicitudes, 1), 2)

            # Ratio invitación → registro
            ratio_invitacion_registro = round(invitaciones_usadas / max(total_invitaciones, 1), 2)

            # Oficios saturados: oficios con más de X retadores en competencia activa
            col_retador = db._columna_retador_competencia(cursor)
            _repo.execute(cursor, """
                SELECT oficio, COUNT(DISTINCT """ + col_retador + """) as n
                FROM competencia WHERE estado = 'activa'
                GROUP BY oficio
                HAVING COUNT(DISTINCT """ + col_retador + """) > ?
            """, (umbral_suplentes,))
            oficios_saturados = len(cursor.fetchall())

            # Oficios disponibles (sin titular): plazas vacías en grupos activos, no cerradas
            catalogo = db.get_catalogo_oficios_ruana()
            if not catalogo:
                oficios_disponibles = 0
            else:
                _repo.execute(cursor, """
                    SELECT g.id, g.codigo_postal FROM grupos g
                    WHERE g.estado = 'activo'
                """)
                grupos_activos = cursor.fetchall()
                plazas_sin_titular = 0
                for (gid, _) in grupos_activos:
                    _repo.execute(cursor, 
                        "SELECT oficio FROM aliados WHERE grupo_id = ? AND estado = 'activo' AND oficio IS NOT NULL",
                        (gid,)
                    )
                    oficios_en_grupo = {r[0].strip() for r in cursor.fetchall() if r[0]}
                    _repo.execute(cursor, 
                        "SELECT oficio FROM grupo_oficio_cerrado WHERE grupo_id = ?",
                        (gid,)
                    )
                    cerrados = {r[0].strip() for r in cursor.fetchall() if r[0]}
                    for oficio in catalogo:
                        if oficio and oficio not in oficios_en_grupo and oficio not in cerrados:
                            plazas_sin_titular += 1
                oficios_disponibles = plazas_sin_titular

            # Zona mayor demanda: CP con más solicitudes pendientes
            _repo.execute(cursor, """
                SELECT g.codigo_postal, COUNT(*) as c
                FROM solicitudes s
                JOIN grupos g ON s.grupo_id = g.id
                WHERE s.estado = 'pendiente' AND g.codigo_postal IS NOT NULL AND g.codigo_postal != ''
                GROUP BY g.codigo_postal
                ORDER BY c DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            zona_mayor_demanda = (row[0] or '—') if row else '—'

            # Tasa retención: activos / total
            tasa_retencion = round(100.0 * aliados_activos / max(total_aliados, 1), 1)

            return {
                'ratio_solicitud_invitacion': ratio_solicitud_invitacion,
                'ratio_invitacion_registro': ratio_invitacion_registro,
                'oficios_saturados': oficios_saturados,
                'oficios_disponibles': oficios_disponibles,
                'zona_mayor_demanda': zona_mayor_demanda,
                'tasa_retencion': tasa_retencion,
            }
        except Exception as e:
            print(f"Error obtener_health_metrics_admin: {e}")
            return {
                'ratio_solicitud_invitacion': 0,
                'ratio_invitacion_registro': 0,
                'oficios_saturados': 0,
                'oficios_disponibles': 0,
                'zona_mayor_demanda': '—',
                'tasa_retencion': 0,
            }
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
# --- Extraído de DBManager (admin) ---

def _insert_evento_sistema(db,
    cursor,
    tipo: str,
    descripcion: str,
    actor_tipo: Optional[str] = None,
    actor_codigo: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Inserta un evento de sistema usando un cursor ya abierto. Idempotencia: no inserta si el mismo evento (tipo, descripcion, actor_codigo) ya existe en los últimos 30 segundos."""
    import time as _time
    row = _repo.select_evento_reciente_idem(cursor, tipo, descripcion, actor_codigo)
    if row:
        try:
            from datetime import datetime
            ultimo = row[0]
            if ultimo:
                s = str(ultimo).replace("Z", "").replace("+00:00", "").strip()[:19]
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        dt = datetime.strptime(s, fmt)
                        ts = dt.timestamp()
                        if (_time.time() - ts) < 30:
                            return
                        break
                    except ValueError:
                        continue
        except Exception:
            pass
    meta_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else None
    _repo.insertar_evento_sistema(
        cursor, tipo, descripcion, actor_tipo, actor_codigo, meta_json
    )

def registrar_evento_sistema(db,
    tipo: str,
    descripcion: str,
    actor_tipo: Optional[str] = None,
    actor_codigo: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Registra un evento de sistema (acción relevante para trazabilidad/auditoría).
    Uso genérico cuando no estamos ya dentro de otra transacción.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            db._insert_evento_sistema(cursor, tipo, descripcion, actor_tipo, actor_codigo, metadata)
            conn.commit()
        except Exception as e:
            print(f"Error registrando evento de sistema: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

def obtener_eventos_recientes(db, limite: int = 10) -> List[Dict[str, Any]]:
    """Obtiene los últimos N eventos de sistema para el panel admin."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                limite_int = int(limite)
            except Exception:
                limite_int = 10
            if limite_int <= 0:
                limite_int = 10

            rows = _repo.listar_eventos_recientes(cursor, limite_int)
            eventos: List[Dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                meta_raw = item.get('metadata')
                if meta_raw:
                    try:
                        item['metadata'] = json.loads(meta_raw)
                    except Exception:
                        item['metadata'] = None
                else:
                    item['metadata'] = None
                eventos.append(item)
            return eventos
        except Exception as e:
            print(f"Error obteniendo eventos recientes: {e}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

def obtener_movimiento_24h(db) -> Dict[str, Any]:
    """
    Movimiento del sistema en las últimas 24 horas: contactos recientes, invitaciones, solicitudes.
    Para el panel admin (GET /api/movimiento-24h).
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            # Ventana 24h (solicitudes: compatible tabla unificada)
            try:
                cols_s = _repo.columnas_tabla(cursor, 'solicitudes')
                col_s = "created_at" if 'created_at' in cols_s else "creado_en"
                est_s = "atendida" if 'atendido_por_codigo' in cols_s else "contestada"
            except Exception:
                col_s, est_s = "creado_en", "contestada"
            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE datetime({col_s}) >= datetime('now', '-1 day')")
            solicitudes_nuevas = cursor.fetchone()[0] or 0
            _repo.execute(cursor, f"SELECT COUNT(*) FROM solicitudes WHERE estado = ? AND datetime({col_s}) >= datetime('now', '-1 day')", (est_s,))
            solicitudes_atendidas = cursor.fetchone()[0] or 0
            _repo.execute(cursor, "SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente'")
            solicitudes_sin_respuesta = cursor.fetchone()[0] or 0

            # Invitaciones: generadas y usadas en 24h (invitaciones.creado_en, referidos.creado_en)
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM invitaciones
                WHERE datetime(creado_en) >= datetime('now', '-1 day')
            """)
            invitaciones_generadas = cursor.fetchone()[0] or 0

            _repo.execute(cursor, """
                SELECT COUNT(*) FROM referidos
                WHERE datetime(creado_en) >= datetime('now', '-1 day')
            """)
            invitaciones_usadas = cursor.fetchone()[0] or 0

            # Contactos RUANA recientes
            _repo.execute(cursor, """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE datetime(creado_en) >= datetime('now', '-1 day')
            """)
            contactos_nuevos = cursor.fetchone()[0] or 0

            _repo.execute(cursor, """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE fecha_aceptacion IS NOT NULL AND datetime(fecha_aceptacion) >= datetime('now', '-1 day')
            """)
            contactos_aceptados = cursor.fetchone()[0] or 0

            _repo.execute(cursor, """
                SELECT COUNT(*) FROM contactos_ruana
                WHERE (fecha_cierre IS NOT NULL OR fecha_no_concretado IS NOT NULL)
                AND (datetime(fecha_cierre) >= datetime('now', '-1 day') OR datetime(fecha_no_concretado) >= datetime('now', '-1 day'))
            """)
            contactos_cerrados = cursor.fetchone()[0] or 0

            # Top invitadores (últimas 24h): por referidos.creado_en
            _repo.execute(cursor, """
                SELECT r.codigo_invitador, COUNT(*) as total
                FROM referidos r
                WHERE datetime(r.creado_en) >= datetime('now', '-1 day')
                GROUP BY r.codigo_invitador
                ORDER BY total DESC
                LIMIT 5
            """)
            rows = cursor.fetchall()
            top_invitadores = []
            for codigo_inv, total in rows:
                rn = _repo.select_nombre_aliado(cursor, codigo_inv)
                nombre = (rn[0] or codigo_inv) if rn else codigo_inv
                top_invitadores.append({'nombre': nombre, 'total': total})

            return {
                'solicitudes': {
                    'nuevas': solicitudes_nuevas,
                    'atendidas': solicitudes_atendidas,
                    'sin_respuesta': solicitudes_sin_respuesta,
                },
                'invitaciones': {
                    'generadas': invitaciones_generadas,
                    'usadas': invitaciones_usadas,
                    'expiradas': 0,
                },
                'contactos': {
                    'nuevos': contactos_nuevos,
                    'aceptados': contactos_aceptados,
                    'cerrados': contactos_cerrados,
                },
                'top_invitadores': top_invitadores,
            }
        except Exception as e:
            print(f"Error obtener_movimiento_24h: {e}")
            return {
                'solicitudes': {'nuevas': 0, 'atendidas': 0, 'sin_respuesta': 0},
                'invitaciones': {'generadas': 0, 'usadas': 0, 'expiradas': 0},
                'contactos': {'nuevos': 0, 'aceptados': 0, 'cerrados': 0},
                'top_invitadores': [],
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

def obtener_movimiento_24h_por_hora(db) -> Dict[str, Dict[str, int]]:
    """
    Movimiento del sistema en las últimas 24 horas, agrupado por hora (00-23).
    Cada clave es "00".."23" con: nuevas, atendidas, sin_respuesta, invitaciones_generadas,
    invitaciones_usadas, invitaciones_expiradas. Siempre devuelve 24 entradas (0 si no hay datos).
    """
    horas = [f"{h:02d}" for h in range(24)]
    vacio = {
        'nuevas': 0,
        'atendidas': 0,
        'sin_respuesta': 0,
        'invitaciones_generadas': 0,
        'invitaciones_usadas': 0,
        'invitaciones_expiradas': 0,
        'contactos_creados': 0,
    }
    resultado = {h: dict(vacio) for h in horas}

    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            try:
                cols_s2 = _repo.columnas_tabla(cursor, 'solicitudes')
                col_sol = "created_at" if 'created_at' in cols_s2 else "creado_en"
                est_sol = "atendida" if 'atendido_por_codigo' in cols_s2 else "contestada"
            except Exception:
                col_sol, est_sol = "creado_en", "contestada"
            filtro_24h_sol = f"datetime({col_sol}) >= datetime('now', '-1 day')"
            filtro_24h = "datetime(creado_en) >= datetime('now', '-1 day')"

            _repo.execute(cursor, f"SELECT strftime('%H', {col_sol}) AS hora, COUNT(*) AS total FROM solicitudes WHERE {filtro_24h_sol} GROUP BY strftime('%H', {col_sol})")
            for row in cursor.fetchall():
                h = row[0] if row[0] and len(row[0]) == 2 else (f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0])
                if h in resultado:
                    resultado[h]['nuevas'] = row[1]
            _repo.execute(cursor, f"SELECT strftime('%H', {col_sol}) AS hora, COUNT(*) AS total FROM solicitudes WHERE estado = ? AND {filtro_24h_sol} GROUP BY strftime('%H', {col_sol})", (est_sol,))
            for row in cursor.fetchall():
                h = row[0] if row[0] and len(row[0]) == 2 else (f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0])
                if h in resultado:
                    resultado[h]['atendidas'] = row[1]
            _repo.execute(cursor, f"SELECT strftime('%H', {col_sol}) AS hora, COUNT(*) AS total FROM solicitudes WHERE estado = 'pendiente' AND {filtro_24h_sol} GROUP BY strftime('%H', {col_sol})")
            for row in cursor.fetchall():
                h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                if h in resultado:
                    resultado[h]['sin_respuesta'] = row[1]

            # Invitaciones generadas por hora
            _repo.execute(cursor, f"""
                SELECT strftime('%H', creado_en) AS hora, COUNT(*) AS total
                FROM invitaciones
                WHERE {filtro_24h}
                GROUP BY strftime('%H', creado_en)
            """)
            for row in cursor.fetchall():
                h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                if h in resultado:
                    resultado[h]['invitaciones_generadas'] = row[1]

            # Invitaciones usadas (referidos) por hora
            _repo.execute(cursor, f"""
                SELECT strftime('%H', creado_en) AS hora, COUNT(*) AS total
                FROM referidos
                WHERE {filtro_24h}
                GROUP BY strftime('%H', creado_en)
            """)
            for row in cursor.fetchall():
                h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                if h in resultado:
                    resultado[h]['invitaciones_usadas'] = row[1]

            # Contactos creados por hora
            _repo.execute(cursor, f"""
                SELECT strftime('%H', creado_en) AS hora, COUNT(*) AS total
                FROM contactos_ruana
                WHERE {filtro_24h}
                GROUP BY strftime('%H', creado_en)
            """)
            for row in cursor.fetchall():
                h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                if h in resultado:
                    resultado[h]['contactos_creados'] = row[1]

            return resultado
        except Exception as e:
            print(f"Error obtener_movimiento_24h_por_hora: {e}")
            return resultado
        finally:
            try:
                conn.close()
            except Exception:
                pass


def generar_reporte(db) -> Dict[str, Any]:
    """Genera un resumen para el panel admin (conteos y datos agregados)."""
    conn = None
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM aliados")
            total_aliados = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM aliados WHERE estado = 'activo'")
            aliados_activos = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM solicitudes")
            total_solicitudes = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM contactos_ruana")
            total_contactos = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM grupos WHERE estado = 'activo'")
            grupos_activos = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM competencia WHERE estado = 'activa'")
            competencias_activas = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM grupo_oficio_cerrado")
            plazas_cerradas = cursor.fetchone()[0] or 0
            reporte = {
                'total_aliados': total_aliados,
                'aliados_activos': aliados_activos,
                'total_solicitudes': total_solicitudes,
                'total_contactos': total_contactos,
                'grupos_activos': grupos_activos,
                'competencias_activas': competencias_activas,
                'plazas_cerradas': plazas_cerradas,
                'generado_en': datetime.now().isoformat(),
            }
            try:
                db.registrar_evento_sistema('generar_reporte', 'Reporte administrativo generado', actor_tipo='admin', metadata=reporte)
            except Exception:
                pass
            return {'status': 'success', 'reporte': reporte}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass


def cambiar_regla(db, clave: str, valor: Any, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    """
    Actualiza una clave en config/ruana_reglas_v1.json.
    Claves permitidas: umbral_competencia, duracion_competencia_dias, purga_mensual_meses_sin_ganar, purga_score_bajo_umbral, apoyo_pct, posponer_horas.
    """
    permitidas = {'umbral_competencia', 'duracion_competencia_dias', 'purga_mensual_meses_sin_ganar', 'purga_score_bajo_umbral', 'apoyo_pct', 'posponer_horas'}
    if clave not in permitidas:
        return {'status': 'error', 'message': f'Clave no permitida. Permitidas: {", ".join(sorted(permitidas))}'}
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if not config_path.exists():
            return {'status': 'error', 'message': 'Archivo de reglas no encontrado'}
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if clave == 'umbral_competencia':
            data[clave] = int(valor)
        elif clave == 'duracion_competencia_dias':
            data[clave] = int(valor)
        elif clave == 'purga_mensual_meses_sin_ganar':
            data[clave] = int(valor)
        elif clave == 'purga_score_bajo_umbral':
            data[clave] = int(valor)
        elif clave == 'apoyo_pct':
            data[clave] = float(valor)
        elif clave == 'posponer_horas':
            data[clave] = int(valor)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=0, ensure_ascii=False)
        db.registrar_evento_sistema(
            'cambiar_reglas',
            f'Regla actualizada: {clave} = {valor}',
            actor_tipo='admin',
            actor_codigo=admin_codigo,
            metadata={'clave': clave, 'valor': valor},
        )
        return {'status': 'success', 'message': f'Regla {clave} actualizada', 'clave': clave, 'valor': data[clave]}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def exportar_a_json(db) -> Dict[str, Any]:
    """Exporta toda la BD a JSON (para respaldos o migraciones)"""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Obtener todas las tablas
            cursor.execute("SELECT * FROM aliados")
            aliados = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT * FROM grupos")
            grupos = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT * FROM solicitudes")
            solicitudes = [dict(row) for row in cursor.fetchall()]
            
            return {
                'aliados': aliados,
                'grupos': grupos,
                'solicitudes': solicitudes,
                'exportado_en': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error exportando: {e}")
            return {}
        finally:
            conn.close()


def limpiar_bd(db):
    """⚠️ PELIGRO: Limpia completamente la BD (solo para testing)"""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM evaluaciones_historico")
            cursor.execute("DELETE FROM evaluaciones")
            cursor.execute("DELETE FROM solicitudes")
            cursor.execute("DELETE FROM aliados")
            cursor.execute("DELETE FROM grupos")
            
            conn.commit()
            print("⚠️ Base de datos limpiada")
            
        except Exception as e:
            print(f"Error limpiando BD: {e}")
        finally:
            conn.close()


def contar_aliados_en_riesgo(db) -> int:
    """Cuenta aliados activos con estado RUANA 'EN RIESGO' (15 <= score < 50)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM aliados
                WHERE estado = 'activo' AND score IS NOT NULL
                AND CAST(score AS INTEGER) >= 15 AND CAST(score AS INTEGER) < 50
            """)
            return cursor.fetchone()[0] or 0
        except Exception:
            return 0
        finally:
            conn.close()


def contar_retadores_activos(db) -> int:
    """Cuenta aliados que están actuando como retador en una competencia activa."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            col_retador = db._columna_retador_competencia(cursor)
            cursor.execute(
                f"SELECT COUNT(DISTINCT {col_retador}) FROM competencia WHERE estado = 'activa'"
            )
            return cursor.fetchone()[0] or 0
        except Exception:
            return 0
        finally:
            conn.close()


def contar_aliados_en_espera(db) -> int:
    """Cuenta aliados en lista de espera (estado en_espera)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM aliados WHERE estado = 'en_espera'")
            return cursor.fetchone()[0] or 0
        except Exception:
            return 0
        finally:
            conn.close()


def contar_suplentes_activos(db) -> int:
    """Alias de contar_retadores_activos para compatibilidad."""
    return db.contar_retadores_activos()


def listar_codigos_aliados_activos(db) -> List[str]:
    """Lista los códigos de todos los aliados con estado activo (para motor de evaluación)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT codigo FROM aliados WHERE estado = 'activo' AND codigo IS NOT NULL AND TRIM(codigo) != '' ORDER BY id"
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()


def forzar_suplencia(
    db,
    grupo_id: int,
    oficio: str,
    aliado_original_codigo: str,
    suplente_codigo: str,
    admin_codigo: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias de forzar_competencia para compatibilidad con código existente."""
    return db.forzar_competencia(grupo_id, oficio, aliado_original_codigo, suplente_codigo, admin_codigo=admin_codigo)


def _audit_log(db, cursor, entidad: str, entidad_id: int, accion: str,
               actor_tipo: str = "", actor_codigo: str = "", detalles: str = "") -> None:
    """Registra una acción en audit_log."""
    cursor.execute("""
        INSERT INTO audit_log (entidad, entidad_id, accion, actor_tipo, actor_codigo, detalles)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (entidad, entidad_id, accion, actor_tipo or None, actor_codigo or None, detalles or None))


def _es_condicion_aliado_placeholder_sql(db) -> str:
    """Condición SQL (sin WHERE) para detectar placeholders reales de invitación."""
    return """(
        LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
    )"""


def _ejecutar_purga_placeholders(db, cursor) -> int:
    """Compatibilidad: no elimina placeholders de BD."""
    return 0


def _purgar_placeholders_control_aliados(db, conn, cursor) -> None:
    """Compatibilidad: ya no se purgan placeholders automáticamente."""
    cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'purgar_placeholders_control_v1'")
    if cursor.fetchone():
        return
    cursor.execute("INSERT INTO migraciones (nombre) VALUES ('purgar_placeholders_control_v1')")


def purgar_aliados_placeholder(db) -> Dict[str, Any]:
    """Compatibilidad: no elimina filas; placeholders se ocultan en listados."""
    return {'status': 'success', 'eliminados': 0}

