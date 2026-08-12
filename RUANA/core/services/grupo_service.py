"""Servicio de dominio grupo (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de grupos vía GrupoRepo.
"""
from __future__ import annotations

import string

from core.db_constants import MAX_GRUPOS_POR_CP, SUFIJOS_GRUPO, ESTADOS_GRUPO
from core.repositories.grupo_repo import GrupoRepo

import sqlite3
import random
from typing import Any, Dict, List, Optional

_repo = GrupoRepo()

# --- Extraído de DBManager (grupo) ---

def _generar_id_unico_grupo(db) -> str:
    """Genera un ID alfanumérico no secuencial (8 caracteres) para el nombre del grupo."""
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choices(caracteres, k=8))

def _generar_nombre_grupo(db, cursor) -> str:
    """
    Genera nombre único en BD con formato RUANA-<ID_UNICO>-<SUFIJO>.
    Valida unicidad en base de datos; reintenta si hay colisión.
    """
    intentos_max = 50
    for _ in range(intentos_max):
        id_part = db._generar_id_unico_grupo()
        sufijo = random.choice(SUFIJOS_GRUPO)
        nombre = f"RUANA-{id_part}-{sufijo}"
        if not _repo.existe_nombre(cursor, nombre):
            return nombre
    raise RuntimeError("No se pudo generar nombre único para el grupo tras varios intentos")

def obtener_grupos_activos_por_cp(db, codigo_postal: str) -> List[Dict[str, Any]]:
    """Lista grupos activos en el código postal (datos desde BD, sin listas abstractas)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(row) for row in _repo.listar_activos_por_cp(cursor, codigo_postal)]
        except Exception:
            return []
        finally:
            conn.close()

def _grupo_tiene_oficio(db, cursor, grupo_id: int, oficio: str) -> bool:
    """True si ya existe un aliado activo en el grupo con ese oficio. Compatible con plaza (oficio, especializacion)."""
    if not oficio or not grupo_id:
        return False
    return _repo.tiene_oficio(cursor, grupo_id, oficio.strip())

def _grupo_tiene_plaza(db, cursor, grupo_id: int, oficio_principal: str, especializacion: Optional[str] = None) -> bool:
    """True si la plaza (oficio_principal) ya está ocupada en el grupo. Plaza por oficio principal únicamente."""
    if not grupo_id or not oficio_principal:
        return False
    return db._grupo_tiene_oficio(cursor, grupo_id, oficio_principal.strip())

def plaza_ocupada_en_grupo(db, grupo_id: int, oficio_principal: str, especializacion: Optional[str] = None) -> bool:
    """True si la plaza (oficio_principal) ya está ocupada en el grupo. Thread-safe. especializacion ignorado."""
    if not grupo_id or not oficio_principal:
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return db._grupo_tiene_oficio(cursor, grupo_id, oficio_principal.strip())
        except Exception:
            return True
        finally:
            conn.close()

def buscar_grupo_sin_oficio(db, codigo_postal: str, oficio: str, especializacion: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Devuelve un grupo activo en ese CP donde el oficio esté libre. especializacion ignorado."""
    if not codigo_postal or not oficio:
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            for row in _repo.listar_activos_por_cp(cursor, codigo_postal):
                g = dict(row)
                if not db._grupo_tiene_oficio(cursor, g['id'], oficio):
                    return g
            return None
        except Exception:
            return None
        finally:
            conn.close()

def buscar_grupo_formacion_en_cp(db, codigo_postal: str, oficio: str) -> Optional[Dict[str, Any]]:
    """
    Grupo activo en el CP con menos aliados activos donde la plaza del oficio esté libre.
    Usado para reubicar al perdedor de una competencia (grupo en formación).
    """
    if not codigo_postal or not oficio:
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            candidatos = []
            for row in _repo.listar_activos_por_cp_con_n_aliados(cursor, codigo_postal):
                g = dict(row)
                if not db._grupo_tiene_oficio(cursor, g['id'], oficio):
                    candidatos.append(g)
            return candidatos[0] if candidatos else None
        except Exception:
            return None
        finally:
            conn.close()

def contar_grupos_activos_por_cp(db, codigo_postal: str) -> int:
    """Cuenta grupos activos en el código postal (límite máximo MAX_GRUPOS_POR_CP)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.contar_activos_por_cp(cursor, codigo_postal)
        except Exception:
            return 0
        finally:
            conn.close()

def crear_grupo_en_cp(db, codigo_postal: str, ciudad: str = "", provincia: str = "") -> Dict[str, Any]:
    """Crea siempre un nuevo grupo en el CP (nombre automático). No comprueba límite; llamador debe asegurar < MAX_GRUPOS_POR_CP."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            nombre = db._generar_nombre_grupo(cursor)
            gid = _repo.insertar_grupo(cursor, nombre, codigo_postal, ciudad, provincia)
            conn.commit()
            return dict(_repo.select_grupo_por_id(cursor, gid))
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def contar_aliados_activos_grupo(db, grupo_id: int) -> int:
    """Cuenta aliados activos en el grupo. Grupo viable = mínimo 2."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.contar_aliados_activos(cursor, grupo_id)
        except Exception:
            return 0
        finally:
            conn.close()

def info_grupo_para_panel(db, grupo_id: int) -> Optional[Dict[str, Any]]:
    """
    Información del grupo para el panel del aliado (sin scores ni métricas de otros).
    Devuelve: nombre, estado, num_oficios, oficios_faltantes (según catálogo RUANA).
    """
    grupo = db.obtener_grupo_por_id(grupo_id)
    if not grupo:
        return None
    oficios_en_grupo = db.obtener_oficios_grupo(grupo_id)
    catalogo = db.get_catalogo_oficios_ruana()
    oficios_faltantes = sorted([o for o in catalogo if o and o not in oficios_en_grupo])
    return {
        'nombre': grupo.get('nombre') or '---',
        'estado': grupo.get('estado') or 'activo',
        'num_oficios': len(oficios_en_grupo),
        'oficios_faltantes': oficios_faltantes,
    }

def procesar_viabilidad_grupo(db, grupo_id: int) -> Dict[str, Any]:
    """
    Viabilidad mínima: grupo viable = mínimo 2 aliados activos.
    Si el grupo baja a 1 aliado:
    - Intenta fusión con otro grupo del mismo CP con <3 aliados y sin oficios repetidos; el más antiguo absorbe.
    - Si no es posible fusionar: reasigna el aliado a un grupo compatible, o crea uno nuevo; marca grupo como DISUELTO.
    El nombre del grupo disuelto queda retirado permanentemente (no se reutiliza).
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            grupo = db.obtener_grupo_por_id(grupo_id)
            if not grupo:
                return {'status': 'error', 'message': 'Grupo no encontrado'}

            if grupo.get('estado') == 'disuelto':
                return {'status': 'ok', 'message': 'Grupo ya disuelto'}

            n = db.contar_aliados_activos_grupo(grupo_id)
            if n >= 2:
                return {'status': 'ok', 'message': 'Grupo viable', 'aliados_activos': n}
            if n == 0:
                _repo.update_estado_disuelto(cursor, grupo_id)
                conn.commit()
                return {'status': 'ok', 'accion': 'disuelto', 'motivo': 'sin aliados activos'}

            # 1 aliado activo: obtener su oficio y CP
            row = _repo.select_aliado_activo_del_grupo(cursor, grupo_id)
            if not row:
                _repo.update_estado_disuelto(cursor, grupo_id)
                conn.commit()
                return {'status': 'ok', 'accion': 'disuelto'}

            aliado_id, codigo_aliado, oficio_aliado, codigo_postal = row[0], row[1], (row[2] or '').strip(), (row[3] or '')
            if not codigo_postal:
                _repo.update_estado_disuelto(cursor, grupo_id)
                conn.commit()
                return {'status': 'ok', 'accion': 'disuelto', 'motivo': 'sin cp'}

            # Intentar fusión: candidato mismo CP, <3 aliados, sin ese oficio
            candidato = db._buscar_candidato_fusion(cursor, grupo_id, codigo_postal, oficio_aliado)
            if candidato:
                # Grupo más antiguo absorbe (comparar fecha_creacion o id)
                try:
                    t_our = grupo.get('fecha_creacion') or ''
                    t_oth = candidato.get('fecha_creacion') or ''
                    id_our = grupo.get('id')
                    id_oth = candidato.get('id')
                except Exception:
                    id_our, id_oth = grupo.get('id'), candidato.get('id')
                if (t_oth < t_our) or (t_oth == t_our and id_oth < id_our):
                    absorbedor_id, disolver_id = candidato['id'], grupo_id
                else:
                    absorbedor_id, disolver_id = grupo_id, candidato['id']
                db._fusionar_grupos_mas_antiguo_absorbe(conn, cursor, absorbedor_id, disolver_id)
                conn.commit()
                return {'status': 'ok', 'accion': 'fusionado', 'absorbedor_id': absorbedor_id, 'disuelto_id': disolver_id}

            # No fusión: reasignar a grupo compatible o crear nuevo
            compatible = db._buscar_grupo_compatible_mismo_cp(cursor, codigo_postal, oficio_aliado, grupo_id)
            if compatible:
                _repo.update_aliado_grupo_id(cursor, compatible['id'], aliado_id)
                _repo.update_estado_disuelto(cursor, grupo_id)
                conn.commit()
                return {'status': 'ok', 'accion': 'reasignado', 'nuevo_grupo_id': compatible['id'], 'disuelto_id': grupo_id}

            # Sin grupo compatible: crear nuevo grupo y asignar aliado
            r = _repo.select_ciudad_provincia(cursor, grupo_id)
            ciudad = r[0] if r and r[0] else ''
            provincia = r[1] if r and r[1] else ''
            conn.commit()
            conn.close()

            nuevo = db.crear_grupo_en_cp(codigo_postal, ciudad, provincia)
            if isinstance(nuevo, dict) and nuevo.get('id'):
                with db._lock:
                    conn2 = db._connect()
                    cursor2 = conn2.cursor()
                    _repo.update_aliado_grupo_id(cursor2, nuevo['id'], aliado_id)
                    _repo.update_estado_disuelto(cursor2, grupo_id)
                    conn2.commit()
                    conn2.close()
                return {'status': 'ok', 'accion': 'reasignado_nuevo_grupo', 'nuevo_grupo_id': nuevo['id'], 'disuelto_id': grupo_id}

            with db._lock:
                conn2 = db._connect()
                cursor2 = conn2.cursor()
                _repo.update_estado_disuelto(cursor2, grupo_id)
                conn2.commit()
                conn2.close()
            return {'status': 'ok', 'accion': 'disuelto', 'motivo': 'sin fusion ni compatible'}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

def obtener_avisos_grupo(db, grupo_id: int, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
    """Avisos del grupo (ej. competencia). No incluye scores individuales."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(row) for row in _repo.listar_avisos(cursor, grupo_id, tipo)]
        except Exception:
            return []
        finally:
            conn.close()

def cerrar_oficio_grupo(db, grupo_id: int, oficio: str, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    """Marca la plaza (grupo + oficio) como cerrada; no se asignan nuevos aliados a esa plaza."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            oficio_s = (oficio or '').strip()
            if not oficio_s:
                return {'status': 'error', 'message': 'Oficio obligatorio'}
            if not _repo.existe_grupo_activo(cursor, grupo_id):
                return {'status': 'error', 'message': 'Grupo no encontrado o no activo'}
            _repo.insertar_oficio_cerrado(cursor, grupo_id, oficio_s)
            conn.commit()
            try:
                db.registrar_evento_sistema(
                    'cerrar_oficio',
                    f'Oficio {oficio_s} cerrado en grupo {grupo_id}',
                    actor_tipo='admin',
                    actor_codigo=admin_codigo,
                    metadata={'grupo_id': grupo_id, 'oficio': oficio_s},
                )
            except Exception:
                pass
            return {'status': 'success', 'message': f'Oficio {oficio_s} cerrado en el grupo'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

def abrir_plaza_grupo(db, grupo_id: int, oficio: str, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    """Reabre la plaza (quita el cierre de grupo + oficio)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            oficio_s = (oficio or '').strip()
            if not oficio_s:
                return {'status': 'error', 'message': 'Oficio obligatorio'}
            _repo.delete_oficio_cerrado(cursor, grupo_id, oficio_s)
            conn.commit()
            try:
                db.registrar_evento_sistema(
                    'abrir_plaza',
                    f'Plaza reabierta: grupo {grupo_id}, oficio {oficio_s}',
                    actor_tipo='admin',
                    actor_codigo=admin_codigo,
                    metadata={'grupo_id': grupo_id, 'oficio': oficio_s},
                )
            except Exception:
                pass
            return {'status': 'success', 'message': f'Plaza abierta para oficio {oficio_s} en el grupo'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

def listar_oficios_cerrados_grupo(db, grupo_id: int) -> List[str]:
    """Lista los oficios cerrados (en grupo_oficio_cerrado) para un grupo. Para uso en admin «Reabrir plaza»."""
    if not grupo_id:
        return []
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return [row[0].strip() for row in _repo.listar_oficios_cerrados(cursor, grupo_id) if row[0]]
        except Exception:
            return []
        finally:
            conn.close()

def contar_grupos(db) -> Dict[str, int]:
    """
    Cuenta grupos territoriales: total (todos), activos, en_competencia, disueltos.
    Dinámico según se creen o disuelvan.
    """
    conn = None
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            total = _repo.contar_total(cursor)
            activos = _repo.contar_por_estado(cursor, 'activo')
            en_competencia = _repo.contar_por_estado(cursor, 'en_competencia')
            disueltos = _repo.contar_por_estado(cursor, 'disuelto')
            return {
                'total': total,
                'activos': activos,
                'en_competencia': en_competencia,
                'disueltos': disueltos,
            }
        except Exception:
            return {'total': 0, 'activos': 0, 'en_competencia': 0, 'disueltos': 0}
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

