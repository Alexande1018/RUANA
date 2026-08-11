"""Servicio de dominio invitacion (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
"""
from __future__ import annotations

import string

from core.db_constants import RUANA_CODIGO_INVITACION_REGEX

import sqlite3
from typing import Any, Dict, List, Optional
# --- Extraído de DBManager (invitacion) ---

def _registrar_invitacion(db,
    codigo_invitacion: str,
    invitador_aliado_id: int,
    solicitud_id: Optional[int] = None,
) -> None:
    """Registra que este código de invitación fue creado por el aliado invitador (para +3 al completar)."""
    codigo_invitacion = (codigo_invitacion or "").strip()
    if not codigo_invitacion or invitador_aliado_id is None:
        raise ValueError("codigo_invitacion e invitador_aliado_id son obligatorios")
    sid = None
    if solicitud_id is not None:
        try:
            sid = int(solicitud_id)
        except (TypeError, ValueError):
            sid = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            # Asegurar columna solicitud_id en instalaciones antiguas
            try:
                db._migrar_invitaciones_solicitud_id(conn, cursor)
            except Exception:
                pass
            if db.backend == "postgres":
                cursor.execute(
                    """
                    INSERT INTO invitaciones (codigo, invitador_aliado_id, usado, solicitud_id)
                    VALUES (?, ?, 0, ?)
                    ON CONFLICT (codigo) DO UPDATE SET
                        invitador_aliado_id = EXCLUDED.invitador_aliado_id,
                        usado = 0,
                        solicitud_id = COALESCE(EXCLUDED.solicitud_id, invitaciones.solicitud_id)
                    """,
                    (codigo_invitacion, int(invitador_aliado_id), sid),
                )
            else:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO invitaciones (codigo, invitador_aliado_id, usado, solicitud_id)
                    VALUES (?, ?, 0, ?)
                    """,
                    (codigo_invitacion, int(invitador_aliado_id), sid),
                )
            conn.commit()
        finally:
            if conn:
                conn.close()

def crear_campana_invitacion(db, codigo: str = "", nombre: str = "",
                              codigo_postal: str = "", max_usos: int = 100,
                              creado_por_admin_codigo: str = "") -> Dict[str, Any]:
    """Crea un codigo multiuso administrado para registros por invitacion."""
    import random
    import re
    codigo = (codigo or "").strip().upper()
    nombre = (nombre or "").strip() or "Campana de invitacion"
    codigo_postal = (codigo_postal or "").strip()
    try:
        max_usos_int = int(max_usos)
    except (TypeError, ValueError):
        max_usos_int = 100
    max_usos_int = max(1, min(max_usos_int, 10000))

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if not codigo:
                for _ in range(100):
                    codigo = "RUANA-" + "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
                    cursor.execute("SELECT codigo FROM invitacion_campanas WHERE codigo = ?", (codigo,))
                    if not cursor.fetchone():
                        break
                else:
                    return {'status': 'error', 'message': 'No se pudo generar codigo de campana unico'}

            if not re.match(r'^[A-Z0-9][A-Z0-9_-]{3,39}$', codigo):
                return {'status': 'error', 'message': 'El codigo debe tener 4-40 caracteres alfanumericos, guion o guion bajo'}

            cursor.execute("SELECT codigo FROM invitacion_campanas WHERE codigo = ?", (codigo,))
            if cursor.fetchone():
                return {'status': 'error', 'message': f'El codigo {codigo} ya existe'}

            cursor.execute("""
                INSERT INTO invitacion_campanas
                (codigo, nombre, codigo_postal, max_usos, usos_actuales, activo, creado_por_admin_codigo)
                VALUES (?, ?, ?, ?, 0, 1, ?)
            """, (codigo, nombre, codigo_postal, max_usos_int, (creado_por_admin_codigo or "").strip()))
            conn.commit()

            cursor.execute("SELECT * FROM invitacion_campanas WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            return {'status': 'success', 'campana': dict(row)}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def listar_campanas_invitacion(db, limite: int = 50) -> List[Dict[str, Any]]:
    """Lista campanas de invitacion multiuso para el panel admin."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            limite = max(1, min(int(limite or 50), 200))
            cursor.execute("""
                SELECT codigo, nombre, codigo_postal, max_usos, usos_actuales, activo,
                       creado_por_admin_codigo, creado_en, desactivado_en
                FROM invitacion_campanas
                ORDER BY creado_en DESC
                LIMIT ?
            """, (limite,))
            return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

def validar_campana_invitacion(db, codigo: str) -> Optional[Dict[str, Any]]:
    """Devuelve la campana si existe, esta activa y aun tiene usos disponibles."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM invitacion_campanas WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            if not row:
                return None
            campana = dict(row)
            if int(campana.get('activo') or 0) != 1:
                return None
            max_usos = int(campana.get('max_usos') or 0)
            usos_actuales = int(campana.get('usos_actuales') or 0)
            if max_usos > 0 and usos_actuales >= max_usos:
                return None
            campana['usos_restantes'] = max(0, max_usos - usos_actuales)
            return campana
        except Exception:
            return None
        finally:
            if conn:
                conn.close()

def obtener_campana_invitacion(db, codigo: str) -> Optional[Dict[str, Any]]:
    """Devuelve una campana por codigo aunque este agotada o desactivada."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM invitacion_campanas WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            if conn:
                conn.close()

def consumir_campana_invitacion(db, codigo: str, nuevo_aliado_codigo: str) -> bool:
    """Marca un uso de campana si aun queda cupo disponible."""
    codigo = (codigo or "").strip().upper()
    nuevo_aliado_codigo = (nuevo_aliado_codigo or "").strip()
    if not codigo or not nuevo_aliado_codigo:
        return False
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE invitacion_campanas
                SET usos_actuales = usos_actuales + 1
                WHERE codigo = ?
                  AND activo = 1
                  AND usos_actuales < max_usos
            """, (codigo,))
            if cursor.rowcount != 1:
                conn.rollback()
                return False
            cursor.execute("""
                INSERT OR IGNORE INTO invitacion_campana_usos (codigo_campana, codigo_aliado)
                VALUES (?, ?)
            """, (codigo, nuevo_aliado_codigo))
            conn.commit()
            db._registrar_referido_campana_admin(codigo, nuevo_aliado_codigo)
            return True
        except Exception:
            return False
        finally:
            if conn:
                conn.close()

def desactivar_campana_invitacion(db, codigo: str) -> Dict[str, Any]:
    """Desactiva una campana multiuso para que deje de validar."""
    codigo = (codigo or "").strip().upper()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE invitacion_campanas
                SET activo = 0, desactivado_en = CURRENT_TIMESTAMP
                WHERE codigo = ?
            """, (codigo,))
            conn.commit()
            if cursor.rowcount != 1:
                return {'status': 'error', 'message': 'Campana no encontrada'}
            return {'status': 'success', 'codigo': codigo}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def listar_invitaciones_recientes(db, limite: int = 20) -> List[Dict[str, Any]]:
    """Lista las últimas invitaciones generadas (para panel admin). Incluye código, invitador, fecha, usado."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(invitaciones)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'creado_en' not in cols:
                return []
            cursor.execute("""
                SELECT i.codigo, i.invitador_aliado_id, i.creado_en, i.usado,
                       a.codigo AS invitador_codigo, a.nombre AS invitador_nombre
                FROM invitaciones i
                LEFT JOIN aliados a ON a.id = i.invitador_aliado_id
                ORDER BY i.creado_en DESC
                LIMIT ?
            """, (limite,))
            return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

def consumir_invitacion_y_recompensar(db, codigo_invitacion: str, nuevo_aliado_codigo: str) -> bool:
    """
    Registra el referido y da +3 al invitador si la invitación aún no estaba usada.
    Idempotente: si ya estaba usada pero faltaba el vínculo en referidos, lo crea sin duplicar score.
    """
    codigo_invitacion = (codigo_invitacion or '').strip()
    nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
    if not codigo_invitacion or not nuevo_aliado_codigo:
        return False
    codigo_invitador = None
    origen = 'aliado'
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT i.usado, i.invitador_aliado_id, inv.codigo AS codigo_invitador,
                       inv.estado AS invitador_estado
                FROM invitaciones i
                JOIN aliados inv ON inv.id = i.invitador_aliado_id
                WHERE i.codigo = ?
            """, (codigo_invitacion,))
            row = cursor.fetchone()
            if not row:
                return False
            usado = int(row['usado'] or 0)
            codigo_invitador = row['codigo_invitador']
            origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
            ya_registrado = False
            cursor.execute(
                "SELECT invitado_por_codigo FROM aliados WHERE codigo = ?",
                (nuevo_aliado_codigo,),
            )
            row_aliado = cursor.fetchone()
            if row_aliado and (row_aliado[0] or '').strip():
                ya_registrado = True
            if not ya_registrado:
                cursor.execute(
                    "SELECT 1 FROM referidos WHERE codigo_referido = ?",
                    (nuevo_aliado_codigo,),
                )
                ya_registrado = cursor.fetchone() is not None
            if not ya_registrado and usado == 0:
                db.aplicar_cambio_score(codigo_invitador, 3, 'aliado_referido_registro_valido')
            if usado == 0:
                cursor.execute(
                    "UPDATE invitaciones SET usado = 1 WHERE codigo = ?",
                    (codigo_invitacion,),
                )
            conn.commit()
        except Exception:
            return False
        finally:
            if conn:
                conn.close()
    if not codigo_invitador:
        return False
    return db.asignar_invitado_por(nuevo_aliado_codigo, codigo_invitador, origen) or True

def generar_invitacion_oficio(db, codigo_aliado: str, oficio: str) -> Dict[str, Any]:
    """
    Genera o devuelve una invitación por oficio para el grupo del aliado.
    Formato código: RUANA-{grupo_id}-{OFICIO_NORM}-{4 chars}
    Si ya existe una invitación pendiente para grupo+oficio, devuelve la existente.
    """
    import re
    oficio = (oficio or '').strip()
    if not oficio:
        return {'status': 'error', 'message': 'Oficio requerido'}

    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            aliado = db.obtener_aliado_por_codigo(codigo_aliado)
            if not aliado:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            grupo_id = aliado.get('grupo_id')
            aliado_id = aliado.get('id')
            if not grupo_id or not aliado_id:
                return {'status': 'error', 'message': 'El aliado no pertenece a un grupo'}

            oficios_faltantes = db.info_grupo_para_panel(grupo_id)
            if not oficios_faltantes or oficio not in (oficios_faltantes.get('oficios_faltantes') or []):
                return {'status': 'error', 'message': 'El oficio no está en la lista de oficios faltantes'}

            cursor.execute(
                "SELECT codigo FROM invitaciones_oficio WHERE grupo_id = ? AND oficio = ? AND estado = 'pendiente' LIMIT 1",
                (grupo_id, oficio)
            )
            row = cursor.fetchone()
            if row:
                return {'status': 'success', 'codigo': row[0]}

            # Normalizar oficio: solo A-Z0-9, máx 20 chars (formato aceptado por validación)
            oficio_norm = re.sub(r'[^A-Za-z0-9]', '', oficio).upper() or 'OFICIO'
            oficio_norm = (oficio_norm[:20] if len(oficio_norm) > 20 else oficio_norm)
            # Sufijo: exactamente 4 caracteres A-Z o 0-9 (formato aceptado)
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            codigo = f"RUANA-{grupo_id}-{oficio_norm}-{suffix}"
            # Verificar que el código generado cumple el formato aceptado
            if not re.match(RUANA_CODIGO_INVITACION_REGEX, codigo):
                # Fallback si hay inconsistencia
                codigo = f"RUANA-{grupo_id}-OFICIO-{suffix}"

            cursor.execute(
                "INSERT INTO invitaciones_oficio (codigo, grupo_id, oficio, aliado_id, estado) VALUES (?, ?, ?, ?, 'pendiente')",
                (codigo, grupo_id, oficio, aliado_id)
            )
            conn.commit()
            return {'status': 'success', 'codigo': codigo}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def validar_invitacion_oficio(db, codigo: str) -> Optional[Dict[str, Any]]:
    """
    Valida si un código de invitación por oficio (RUANA-{grupo_id}-{OFICIO}-{4chars})
    existe y está pendiente. Devuelve la invitación con grupo_id, oficio, zona, etc.
    Si ya fue usada (estado='usado') o no existe, devuelve None.
    """
    import re
    codigo = (codigo or '').strip().upper()
    if not codigo or not re.match(RUANA_CODIGO_INVITACION_REGEX, codigo):
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, codigo, grupo_id, oficio, aliado_id, estado FROM invitaciones_oficio WHERE codigo = ?",
                (codigo,)
            )
            row = cursor.fetchone()
            conn.close()
            if not row or (row[5] or '').lower() != 'pendiente':
                return None
            inv = dict(row)
            grupo = db.obtener_grupo_por_id(inv['grupo_id'])
            if not grupo:
                return None
            return {
                'codigo': inv['codigo'],
                'grupo_id': inv['grupo_id'],
                'oficio': inv['oficio'],
                'aliado_id': inv['aliado_id'],
                'zona': grupo.get('codigo_postal') or '',
                'grupo': grupo.get('nombre') or '',
                'codigo_postal': grupo.get('codigo_postal') or '',
            }
        except Exception:
            return None

def consumir_invitacion_oficio(db, codigo: str, nuevo_aliado_codigo: str) -> bool:
    """
    Marca una invitación por oficio como usada, registra referido y da +5 al generador
    (Regla 9 del score operativo). Idempotente si ya estaba usada pero faltaba el vínculo.
    """
    codigo = (codigo or '').strip().upper()
    nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
    if not codigo or not nuevo_aliado_codigo:
        return False
    codigo_invitador = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, aliado_id, estado FROM invitaciones_oficio WHERE codigo = ?",
                (codigo,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            invitacion_id = row['id']
            aliado_id = row['aliado_id']
            estado = (row['estado'] or '').strip()
            cursor.execute("SELECT codigo FROM aliados WHERE id = ?", (aliado_id,))
            r2 = cursor.fetchone()
            if not r2:
                return False
            codigo_invitador = r2[0]
            ya_registrado = False
            cursor.execute(
                "SELECT invitado_por_codigo FROM aliados WHERE codigo = ?",
                (nuevo_aliado_codigo,),
            )
            row_aliado = cursor.fetchone()
            if row_aliado and (row_aliado[0] or '').strip():
                ya_registrado = True
            if not ya_registrado:
                cursor.execute(
                    "SELECT 1 FROM referidos WHERE codigo_referido = ?",
                    (nuevo_aliado_codigo,),
                )
                ya_registrado = cursor.fetchone() is not None
            if estado == 'pendiente':
                cursor.execute(
                    "UPDATE invitaciones_oficio SET estado = 'usado', codigo_referido = ? WHERE id = ?",
                    (nuevo_aliado_codigo, invitacion_id),
                )
                if not ya_registrado:
                    db.aplicar_cambio_score(
                        codigo_invitador, db.REGLA9_DELTA, 'invitacion_oficio_usada'
                    )
            elif estado == 'usado' and not ya_registrado:
                cursor.execute(
                    "UPDATE invitaciones_oficio SET codigo_referido = ? WHERE id = ? AND COALESCE(codigo_referido, '') = ''",
                    (nuevo_aliado_codigo, invitacion_id),
                )
            conn.commit()
        except Exception:
            return False
        finally:
            if conn:
                conn.close()
    if not codigo_invitador:
        return False
    return db.asignar_invitado_por(nuevo_aliado_codigo, codigo_invitador, 'oficio') or True

def invitacion_codigo_existe(db, codigo: str) -> bool:
    """True si el código ya está registrado en la tabla invitaciones."""
    codigo = (codigo or '').strip()
    if not codigo:
        return False
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM invitaciones WHERE codigo = ?", (codigo,))
            return cursor.fetchone() is not None
        except Exception as e:
            print(f"Error verificando codigo invitacion: {e}")
            return False
        finally:
            if conn:
                conn.close()

def obtener_invitacion_pendiente(db, codigo: str) -> Optional[Dict[str, Any]]:
    """
    Devuelve una invitación aliado/admin aún no usada (tabla invitaciones).
    No incluye campañas ni invitaciones por oficio.
    """
    codigo = (codigo or '').strip()
    if not codigo:
        return None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT i.codigo, i.invitador_aliado_id, i.usado, i.creado_en,
                       i.solicitud_id,
                       inv.codigo AS codigo_invitador,
                       inv.codigo_postal AS zona_invitador,
                       inv.id AS invitador_id
                FROM invitaciones i
                JOIN aliados inv ON inv.id = i.invitador_aliado_id
                WHERE i.codigo = ? AND COALESCE(i.usado, 0) = 0
                """,
                (codigo,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)
        except Exception as e:
            print(f"Error obtener_invitacion_pendiente: {e}")
            return None
        finally:
            if conn:
                conn.close()

def eliminar_aliado_placeholder(db, codigo: str) -> bool:
    """
    Elimina un aliado placeholder (pendiente_completar) tras usar su código de invitación.
    Evita duplicados inútiles en el panel de control de aliados.
    """
    codigo = (codigo or '').strip()
    if not codigo:
        return False
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM aliados
                WHERE codigo = ?
                  AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
                """,
                (codigo,),
            )
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        except Exception as e:
            print(f"Error eliminar_aliado_placeholder: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False
        finally:
            if conn:
                conn.close()

