"""Servicio de dominio invitacion (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de invitaciones vía InvitacionRepo.
"""
from __future__ import annotations

import random
import string

from core.db_constants import RUANA_CODIGO_INVITACION_REGEX

import sqlite3
from typing import Any, Dict, List, Optional

from core.repositories.invitacion_repo import InvitacionRepo

_repo = InvitacionRepo()

# --- Extraído de DBManager (invitacion) ---

def _registrar_invitacion(db,
    codigo_invitacion: str,
    invitador_aliado_id: int,
    solicitud_id: Optional[int] = None,
    grupo_id: Optional[int] = None,
    tipo: str = "ampliar_red",
) -> None:
    """Registra que este código de invitación fue creado por el aliado invitador."""
    codigo_invitacion = (codigo_invitacion or "").strip()
    if not codigo_invitacion or invitador_aliado_id is None:
        raise ValueError("codigo_invitacion e invitador_aliado_id son obligatorios")
    sid = None
    if solicitud_id is not None:
        try:
            sid = int(solicitud_id)
        except (TypeError, ValueError):
            sid = None
    gid = None
    if grupo_id is not None:
        try:
            gid = int(grupo_id)
        except (TypeError, ValueError):
            gid = None
    tipo_norm = (tipo or "ampliar_red").strip() or "ampliar_red"
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            try:
                db._migrar_invitaciones_solicitud_id(conn, cursor)
                db._migrar_invitaciones_crecimiento_grupo(conn, cursor)
            except Exception:
                pass
            if db.backend == "postgres":
                _repo.upsert_invitacion_postgres(
                    cursor, codigo_invitacion, invitador_aliado_id, sid, gid, tipo_norm
                )
            else:
                _repo.upsert_invitacion_sqlite(
                    cursor, codigo_invitacion, invitador_aliado_id, sid, gid, tipo_norm
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
                    if not _repo.existe_campana(cursor, codigo):
                        break
                else:
                    return {'status': 'error', 'message': 'No se pudo generar codigo de campana unico'}

            if not re.match(r'^[A-Z0-9][A-Z0-9_-]{3,39}$', codigo):
                return {'status': 'error', 'message': 'El codigo debe tener 4-40 caracteres alfanumericos, guion o guion bajo'}

            if _repo.existe_campana(cursor, codigo):
                return {'status': 'error', 'message': f'El codigo {codigo} ya existe'}

            _repo.insertar_campana(
                cursor, codigo, nombre, codigo_postal, max_usos_int,
                (creado_por_admin_codigo or "").strip(),
            )
            conn.commit()

            row = _repo.select_campana(cursor, codigo)
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
            return [dict(r) for r in _repo.listar_campanas(cursor, limite)]
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
            row = _repo.select_campana(cursor, codigo)
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
            row = _repo.select_campana(cursor, codigo)
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
            if _repo.incrementar_uso_campana(cursor, codigo) != 1:
                conn.rollback()
                return False
            _repo.insertar_uso_campana(cursor, codigo, nuevo_aliado_codigo)
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
            rowcount = _repo.desactivar_campana(cursor, codigo)
            conn.commit()
            if rowcount != 1:
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
            cols = _repo.columnas_invitaciones(cursor)
            if 'creado_en' not in cols:
                return []
            return [dict(r) for r in _repo.listar_invitaciones_recientes(cursor, limite)]
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
            row = _repo.select_invitacion_con_invitador(cursor, codigo_invitacion)
            if not row:
                return False
            usado = int(row['usado'] or 0)
            codigo_invitador = row['codigo_invitador']
            tipo_inv = (row['tipo'] or '').strip() or 'ampliar_red'
            grupo_id_inv = row['grupo_id']
            if (row['invitador_estado'] or '').strip() == 'sistema':
                origen = 'admin_invitacion'
            elif row['solicitud_id']:
                origen = 'yo_conozco_a_alguien'
            elif tipo_inv == 'crecimiento_grupo':
                origen = 'crecimiento_grupo'
            else:
                origen = 'ampliar_red'
            ya_registrado = False
            row_aliado = _repo.select_invitado_por_codigo(cursor, nuevo_aliado_codigo)
            if row_aliado and (row_aliado[0] or '').strip():
                ya_registrado = True
            if not ya_registrado:
                ya_registrado = _repo.existe_referido(cursor, nuevo_aliado_codigo)
            if not ya_registrado and usado == 0:
                if tipo_inv == 'crecimiento_grupo':
                    from core.services import grupo_crecimiento_service
                    grupo_crecimiento_service.otorgar_recompensa_registro(
                        db,
                        codigo_invitador,
                        nuevo_aliado_codigo,
                        codigo_invitacion,
                        grupo_id_inv,
                    )
                else:
                    db.aplicar_cambio_score(codigo_invitador, 3, 'aliado_referido_registro_valido')
            if usado == 0:
                _repo.marcar_invitacion_usada(cursor, codigo_invitacion)
            conn.commit()
        except Exception:
            return False
        finally:
            if conn:
                conn.close()
    if not codigo_invitador:
        return False
    return db.asignar_invitado_por(nuevo_aliado_codigo, codigo_invitador, origen) or True

def mensaje_compartir_invitacion_oficio(
    oficio: str, codigo: str, registro_url: str = ""
) -> str:
    """Mensaje para copiar/compartir una invitación por oficio faltante."""
    oficio_txt = (oficio or "").strip() or "profesional"
    codigo_txt = (codigo or "").strip()
    url = (registro_url or "").strip()
    partes = [
        f"¿Conoces un {oficio_txt}?",
        "",
        "RUANA está buscando un profesional de este oficio para formar parte de un grupo de profesionales de su zona.",
        "",
        "Si te registras con este código de invitación, el usuario que te invitó recibirá 3 puntos de score por tu incorporación justo después de que tu registro como aliado haya sido confirmado.",
        "",
        "Regístrate en RUANA utilizando este código de invitación:",
        "",
        codigo_txt,
    ]
    if url:
        partes.extend(["", url])
    return "\n".join(partes)


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

            row = _repo.select_invitacion_oficio_pendiente(cursor, grupo_id, oficio)
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

            _repo.insertar_invitacion_oficio(cursor, codigo, grupo_id, oficio, aliado_id)
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
            row = _repo.select_invitacion_oficio(cursor, codigo)
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
            row = _repo.select_invitacion_oficio_consumo(cursor, codigo)
            if not row:
                return False
            invitacion_id = row['id']
            aliado_id = row['aliado_id']
            estado = (row['estado'] or '').strip()
            r2 = _repo.select_codigo_aliado_por_id(cursor, aliado_id)
            if not r2:
                return False
            codigo_invitador = r2[0]
            ya_registrado = False
            row_aliado = _repo.select_invitado_por_codigo(cursor, nuevo_aliado_codigo)
            if row_aliado and (row_aliado[0] or '').strip():
                ya_registrado = True
            if not ya_registrado:
                ya_registrado = _repo.existe_referido(cursor, nuevo_aliado_codigo)
            if estado == 'pendiente':
                _repo.marcar_invitacion_oficio_usada(cursor, nuevo_aliado_codigo, invitacion_id)
                if not ya_registrado:
                    db.aplicar_cambio_score(
                        codigo_invitador, db.REGLA9_DELTA, 'invitacion_oficio_usada'
                    )
            elif estado == 'usado' and not ya_registrado:
                _repo.update_codigo_referido_oficio_si_vacio(
                    cursor, nuevo_aliado_codigo, invitacion_id
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
            return _repo.existe_codigo_invitacion(cursor, codigo)
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
            row = _repo.select_invitacion_pendiente(cursor, codigo)
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
            deleted = _repo.eliminar_aliado_placeholder(cursor, codigo) > 0
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

