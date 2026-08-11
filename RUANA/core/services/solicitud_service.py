"""Servicio de dominio solicitud (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional
# --- Extraído de DBManager (solicitud) ---

def marcar_solicitud_candidato_pendiente(db, solicitud_id: int, codigo_proponente: str) -> Dict[str, Any]:
    """
    «Conozco a alguien»: la solicitud no se cierra; pasa a candidato_pendiente
    mientras el invitado no se registre.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            try:
                db._migrar_solicitudes_candidato(conn, cursor)
            except Exception:
                pass
            cursor.execute(
                "SELECT grupo_id, estado FROM solicitudes WHERE id = ?",
                (int(solicitud_id),),
            )
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            grupo_id, estado = row[0], (row[1] or '').strip().lower()
            if estado != 'pendiente':
                return {
                    'status': 'error',
                    'message': 'La solicitud ya no está pendiente de candidato',
                }
            cursor.execute(
                "SELECT grupo_id, nombre FROM aliados WHERE codigo = ?",
                (codigo_proponente.strip(),),
            )
            r2 = cursor.fetchone()
            if not r2:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            if r2[0] != grupo_id:
                return {
                    'status': 'error',
                    'message': 'Solo un aliado del mismo grupo puede proponer candidato',
                }
            nombre = r2[1] or ''
            cursor.execute(
                """
                UPDATE solicitudes
                SET estado = 'candidato_pendiente',
                    candidato_por_codigo = ?,
                    candidato_por_nombre = ?,
                    candidato_at = CURRENT_TIMESTAMP
                WHERE id = ? AND estado = 'pendiente'
                """,
                (codigo_proponente.strip(), nombre, int(solicitud_id)),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return {
                    'status': 'error',
                    'message': 'La solicitud ya no está pendiente de candidato',
                }
            return {'status': 'success', 'ok': True, 'estado': 'candidato_pendiente'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

def vincular_solicitud_a_aliado_incorporado(db,
    codigo_invitacion: str,
    nuevo_aliado_codigo: str,
) -> Dict[str, Any]:
    """
    Tras registrarse con el código de «Conozco a alguien», vincula la solicitud
    al nuevo aliado, la deja disponible (pendiente) y le notifica.
    """
    codigo_invitacion = (codigo_invitacion or '').strip()
    nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
    if not codigo_invitacion or not nuevo_aliado_codigo:
        return {'status': 'error', 'message': 'Código requerido'}

    notif_payload = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                db._migrar_invitaciones_solicitud_id(conn, cursor)
                db._migrar_solicitudes_candidato(conn, cursor)
            except Exception:
                pass
            cursor.execute(
                """
                SELECT i.solicitud_id, i.codigo
                FROM invitaciones i
                WHERE i.codigo = ?
                """,
                (codigo_invitacion,),
            )
            inv = cursor.fetchone()
            if not inv:
                return {'status': 'error', 'message': 'Invitación no encontrada'}
            solicitud_id = inv['solicitud_id'] if hasattr(inv, 'keys') else inv[0]
            if solicitud_id is None:
                return {'status': 'success', 'ok': True, 'vinculada': False}
            cursor.execute(
                "SELECT codigo, nombre FROM aliados WHERE codigo = ?",
                (nuevo_aliado_codigo,),
            )
            aliado = cursor.fetchone()
            if not aliado:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            nombre_nuevo = aliado['nombre'] if hasattr(aliado, 'keys') else aliado[1]
            cursor.execute(
                """
                SELECT id, oficio, descripcion, estado, solicitante_codigo
                FROM solicitudes WHERE id = ?
                """,
                (int(solicitud_id),),
            )
            sol = cursor.fetchone()
            if not sol:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            estado = (sol['estado'] if hasattr(sol, 'keys') else sol[3] or '').strip().lower()
            oficio = (sol['oficio'] if hasattr(sol, 'keys') else sol[1]) or ''
            descripcion = (sol['descripcion'] if hasattr(sol, 'keys') else sol[2]) or ''
            if estado in ('candidato_pendiente', 'pendiente'):
                cursor.execute(
                    """
                    UPDATE solicitudes
                    SET estado = 'pendiente',
                        asignada_a_codigo = ?,
                        asignada_a_nombre = ?
                    WHERE id = ?
                    """,
                    (nuevo_aliado_codigo, nombre_nuevo or '', int(solicitud_id)),
                )
            else:
                cursor.execute(
                    """
                    UPDATE solicitudes
                    SET asignada_a_codigo = COALESCE(asignada_a_codigo, ?),
                        asignada_a_nombre = COALESCE(asignada_a_nombre, ?)
                    WHERE id = ?
                    """,
                    (nuevo_aliado_codigo, nombre_nuevo or '', int(solicitud_id)),
                )
            conn.commit()
            oficio_txt = oficio.strip() or 'una solicitud'
            desc_corta = (descripcion or '').strip()
            if len(desc_corta) > 120:
                desc_corta = desc_corta[:117] + '…'
            mensaje = (
                f"Tienes una solicitud disponible para atender"
                f"{(' · ' + oficio_txt) if oficio_txt else ''}."
            )
            if desc_corta:
                mensaje += f" {desc_corta}"
            notif_payload = {
                'codigo': nuevo_aliado_codigo,
                'mensaje': mensaje,
                'solicitud_id': int(solicitud_id),
                'oficio': oficio,
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

    if notif_payload:
        db._crear_notificacion_aliado(
            notif_payload['codigo'],
            'solicitud_asignada',
            'Solicitud disponible',
            notif_payload['mensaje'],
            metadata={
                'solicitud_id': notif_payload['solicitud_id'],
                'oficio': notif_payload['oficio'],
                'origen': 'conozco_alguien',
            },
        )
        return {
            'status': 'success',
            'ok': True,
            'vinculada': True,
            'solicitud_id': notif_payload['solicitud_id'],
        }
    return {'status': 'success', 'ok': True, 'vinculada': False}

def crear_solicitud_por_codigo(db, codigo: str, oficio: str, descripcion: str) -> Dict[str, Any]:
    """Crea solicitud: obtiene aliado por código, inserta en solicitudes con estado pendiente."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT grupo_id, nombre FROM aliados WHERE codigo = ?", (codigo.strip(),))
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Aliado no válido'}
            grupo_id, nombre = row[0], row[1] or ''
            if grupo_id is None:
                return {'status': 'error', 'message': 'No perteneces a un grupo'}
            oficio = (oficio or '').strip()
            descripcion = (descripcion or '').strip()
            if not oficio:
                return {'status': 'error', 'message': 'Oficio requerido'}
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return {'status': 'error', 'message': 'Tabla solicitudes no migrada'}
            cursor.execute("""
                INSERT INTO solicitudes (grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado)
                VALUES (?, ?, ?, ?, ?, 'pendiente')
            """, (grupo_id, codigo.strip(), nombre, oficio, descripcion))
            sid = cursor.lastrowid
            conn.commit()
            return {'status': 'success', 'ok': True, 'id': sid}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def listar_solicitudes_activas_por_codigo(db, codigo: str) -> List[Dict[str, Any]]:
    """Solo mismo grupo, estado pendiente, excluye las propias. GET /api/solicitudes?codigo=.
    También incluye solicitudes pendientes asignadas a este aliado (p. ej. tras «Conozco a alguien»).
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            codigo = codigo.strip()
            cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            if not row:
                return []
            grupo_id = row[0]
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return []
            has_asignada = 'asignada_a_codigo' in cols
            if grupo_id is None and not has_asignada:
                return []
            if grupo_id is not None and has_asignada:
                cursor.execute("""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                           asignada_a_codigo, asignada_a_nombre
                    FROM solicitudes
                    WHERE estado = 'pendiente'
                      AND solicitante_codigo != ?
                      AND (grupo_id = ? OR asignada_a_codigo = ?)
                    ORDER BY created_at DESC
                """, (codigo, grupo_id, codigo))
            elif grupo_id is not None:
                cursor.execute("""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at
                    FROM solicitudes
                    WHERE grupo_id = ? AND estado = 'pendiente' AND solicitante_codigo != ?
                    ORDER BY created_at DESC
                """, (grupo_id, codigo))
            else:
                cursor.execute("""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                           asignada_a_codigo, asignada_a_nombre
                    FROM solicitudes
                    WHERE estado = 'pendiente' AND asignada_a_codigo = ?
                    ORDER BY created_at DESC
                """, (codigo,))
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return []
        finally:
            conn.close()

def listar_solicitudes_propias_por_codigo(db, codigo: str) -> List[Dict[str, Any]]:
    """Solicitudes creadas por el aliado (sus propias solicitudes). Mismo grupo, cualquier estado (pendiente/atendida)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo.strip(),))
            row = cursor.fetchone()
            if not row or row[0] is None:
                return []
            grupo_id = row[0]
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return []
            extra = ''
            if 'candidato_por_codigo' in cols:
                extra += ', candidato_por_codigo, candidato_por_nombre, candidato_at'
            if 'asignada_a_codigo' in cols:
                extra += ', asignada_a_codigo, asignada_a_nombre'
            cursor.execute(f"""
                SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                       atendido_por_codigo, atendido_por_nombre, atendido_at{extra}
                FROM solicitudes
                WHERE grupo_id = ? AND solicitante_codigo = ?
                ORDER BY created_at DESC
            """, (grupo_id, codigo.strip()))
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return []
        finally:
            conn.close()

def listar_solicitudes_historial_grupo_por_codigo(db, codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
    """Historial de solicitudes del grupo (todas: pendiente y atendidas). Ordenado por fecha descendente."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo.strip(),))
            row = cursor.fetchone()
            if not row or row[0] is None:
                return []
            grupo_id = row[0]
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return []
            extra = ''
            if 'candidato_por_codigo' in cols:
                extra += ', candidato_por_codigo, candidato_por_nombre, candidato_at'
            if 'asignada_a_codigo' in cols:
                extra += ', asignada_a_codigo, asignada_a_nombre'
            cursor.execute(f"""
                SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                       atendido_por_codigo, atendido_por_nombre, atendido_at{extra}
                FROM solicitudes
                WHERE grupo_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (grupo_id, limite))
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return []
        finally:
            conn.close()

def obtener_solicitudes_grupo(db, codigo_postal: str) -> List[Dict[str, Any]]:
    """Obtiene solicitudes pendientes de todos los grupos activos en el código postal."""
    if not codigo_postal or not str(codigo_postal).strip():
        return []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return []
            cursor.execute("""
                SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre, s.oficio, s.descripcion,
                       s.estado, s.created_at, g.nombre AS grupo_nombre
                FROM solicitudes s
                JOIN grupos g ON g.id = s.grupo_id
                WHERE g.codigo_postal = ? AND g.estado = 'activo' AND s.estado = 'pendiente'
                ORDER BY s.created_at DESC
            """, (codigo_postal.strip(),))
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return []
        finally:
            conn.close()

def atender_solicitud_por_id(db, solicitud_id: int, codigo: str) -> Dict[str, Any]:
    """Marca solicitud como atendida y registra quién atendió. Solo mismo grupo."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT grupo_id, estado FROM solicitudes WHERE id = ?", (solicitud_id,))
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            grupo_id, estado = row[0], row[1]
            if estado != 'pendiente':
                return {'status': 'error', 'message': 'La solicitud ya fue atendida'}
            cursor.execute("SELECT grupo_id, nombre FROM aliados WHERE codigo = ?", (codigo.strip(),))
            r2 = cursor.fetchone()
            if not r2:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            if r2[0] != grupo_id:
                return {'status': 'error', 'message': 'Solo un aliado del mismo grupo puede atender'}
            nombre_atendido = r2[1] or ''
            cursor.execute("""
                UPDATE solicitudes
                SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
                WHERE id = ? AND estado = 'pendiente'
            """, (codigo.strip(), nombre_atendido, solicitud_id))
            conn.commit()
            if cursor.rowcount == 0:
                return {'status': 'error', 'message': 'La solicitud ya fue atendida'}
            return {'status': 'success', 'ok': True}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def marcar_solicitud_atendida_por_admin(db, solicitud_id: int, admin_codigo: str) -> Dict[str, Any]:
    """Marca la solicitud como atendida y registra al admin como 'Atendido por' y 'Atendido at'. Si ya estaba atendida pero con columnas vacías, las rellena."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'atendido_por_codigo' not in cols or 'atendido_at' not in cols:
                return {'status': 'error', 'message': 'Tabla solicitudes sin columnas atendido_por/atendido_at'}
            cursor.execute("SELECT id, estado, atendido_por_codigo, atendido_at FROM solicitudes WHERE id = ?", (solicitud_id,))
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            estado = row[1]
            atendido_por = row[2]
            atendido_at = row[3]
            nombre_admin = (admin_codigo or '').strip() or 'Admin'
            codigo_str = (admin_codigo or '').strip()
            if estado == 'pendiente':
                cursor.execute("""
                    UPDATE solicitudes
                    SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (codigo_str, nombre_admin, solicitud_id))
            elif not atendido_por and not atendido_at:
                cursor.execute("""
                    UPDATE solicitudes
                    SET atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = COALESCE(atendido_at, CURRENT_TIMESTAMP)
                    WHERE id = ?
                """, (codigo_str, nombre_admin, solicitud_id))
            else:
                return {'status': 'success', 'ok': True}
            conn.commit()
            return {'status': 'success', 'ok': True}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def marcar_solicitud_contestada(db, solicitud_id: int, invitador_aliado_id: Optional[int] = None) -> None:
    """Marca la solicitud como atendida/contestada (p. ej. desde 'Conozco a alguien'). Opcional: invitador_aliado_id para registrar quién contestó."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return
            codigo_atendido = None
            nombre_atendido = None
            if invitador_aliado_id is not None:
                cursor.execute("SELECT codigo, nombre FROM aliados WHERE id = ?", (int(invitador_aliado_id),))
                row = cursor.fetchone()
                if row:
                    codigo_atendido, nombre_atendido = row[0], row[1] or ''
            if codigo_atendido is None:
                codigo_atendido = ''
                nombre_atendido = ''
            cursor.execute("""
                UPDATE solicitudes
                SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
                WHERE id = ? AND estado = 'pendiente'
            """, (codigo_atendido, nombre_atendido, solicitud_id))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

def listar_solicitudes_admin_todas(db) -> List[Dict[str, Any]]:
    """Todas las solicitudes para el panel admin. Orden created_at DESC."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return []
            cursor.execute("""
                SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre, s.oficio, s.descripcion,
                       s.estado, s.atendido_por_codigo, s.atendido_por_nombre, s.created_at, s.atendido_at,
                       g.nombre AS grupo_nombre
                FROM solicitudes s
                LEFT JOIN grupos g ON g.id = s.grupo_id
                ORDER BY s.created_at DESC
            """)
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return []
        finally:
            conn.close()

def contar_solicitudes_activas(db) -> int:
    """Cuenta solicitudes en estado pendiente (activas)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente'"
            )
            return cursor.fetchone()[0] or 0
        except Exception:
            return 0
        finally:
            conn.close()

def contar_solicitudes_enviadas_contestadas(db, codigo: str) -> int:
    """Cuenta solicitudes enviadas por el aliado (solicitante) que fueron atendidas/contestadas."""
    if not codigo or not str(codigo).strip():
        return 0
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(solicitudes)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'solicitante_codigo' not in cols:
                return 0
            estado_atendida = "atendida" if 'atendido_por_codigo' in cols else "contestada"
            cursor.execute(
                "SELECT COUNT(*) FROM solicitudes WHERE solicitante_codigo = ? AND estado = ?",
                (codigo.strip(), estado_atendida),
            )
            return cursor.fetchone()[0] or 0
        except Exception:
            return 0
        finally:
            conn.close()

