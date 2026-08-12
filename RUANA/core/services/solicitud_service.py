"""Servicio de dominio solicitud (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de solicitudes vía SolicitudRepo.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from core.repositories.solicitud_repo import SolicitudRepo

_repo = SolicitudRepo()


def _extra_cols_candidato_asignada(cols: List[str]) -> str:
    extra = ""
    if "candidato_por_codigo" in cols:
        extra += ", candidato_por_codigo, candidato_por_nombre, candidato_at"
    if "asignada_a_codigo" in cols:
        extra += ", asignada_a_codigo, asignada_a_nombre"
    return extra


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
            row = _repo.select_grupo_estado(cursor, int(solicitud_id))
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            grupo_id, estado = row[0], (row[1] or '').strip().lower()
            if estado != 'pendiente':
                return {
                    'status': 'error',
                    'message': 'La solicitud ya no está pendiente de candidato',
                }
            r2 = _repo.select_aliado_grupo_nombre(cursor, codigo_proponente.strip())
            if not r2:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            if r2[0] != grupo_id:
                return {
                    'status': 'error',
                    'message': 'Solo un aliado del mismo grupo puede proponer candidato',
                }
            nombre = r2[1] or ''
            rowcount = _repo.update_candidato_pendiente(
                cursor, int(solicitud_id), codigo_proponente.strip(), nombre
            )
            conn.commit()
            if rowcount == 0:
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
            inv = _repo.select_invitacion_solicitud_id(cursor, codigo_invitacion)
            if not inv:
                return {'status': 'error', 'message': 'Invitación no encontrada'}
            solicitud_id = inv['solicitud_id'] if hasattr(inv, 'keys') else inv[0]
            if solicitud_id is None:
                return {'status': 'success', 'ok': True, 'vinculada': False}
            aliado = _repo.select_aliado_codigo_nombre(cursor, nuevo_aliado_codigo)
            if not aliado:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            nombre_nuevo = aliado['nombre'] if hasattr(aliado, 'keys') else aliado[1]
            sol = _repo.select_solicitud_basica(cursor, int(solicitud_id))
            if not sol:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            estado = (sol['estado'] if hasattr(sol, 'keys') else sol[3] or '').strip().lower()
            oficio = (sol['oficio'] if hasattr(sol, 'keys') else sol[1]) or ''
            descripcion = (sol['descripcion'] if hasattr(sol, 'keys') else sol[2]) or ''
            if estado in ('candidato_pendiente', 'pendiente'):
                _repo.update_asignar_y_pendiente(
                    cursor, int(solicitud_id), nuevo_aliado_codigo, nombre_nuevo or ''
                )
            else:
                _repo.update_asignar_si_vacio(
                    cursor, int(solicitud_id), nuevo_aliado_codigo, nombre_nuevo or ''
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
            row = _repo.select_aliado_grupo_nombre(cursor, codigo.strip())
            if not row:
                return {'status': 'error', 'message': 'Aliado no válido'}
            grupo_id, nombre = row[0], row[1] or ''
            if grupo_id is None:
                return {'status': 'error', 'message': 'No perteneces a un grupo'}
            oficio = (oficio or '').strip()
            descripcion = (descripcion or '').strip()
            if not oficio:
                return {'status': 'error', 'message': 'Oficio requerido'}
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return {'status': 'error', 'message': 'Tabla solicitudes no migrada'}
            sid = _repo.insertar_pendiente(
                cursor, grupo_id, codigo.strip(), nombre, oficio, descripcion
            )
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
            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
            if not aliado:
                return []
            grupo_id = aliado[0]
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            has_asignada = 'asignada_a_codigo' in cols
            if grupo_id is None and not has_asignada:
                return []
            if grupo_id is not None and has_asignada:
                return _repo.listar_activas_grupo_o_asignada(cursor, codigo, grupo_id)
            elif grupo_id is not None:
                return _repo.listar_activas_grupo(cursor, codigo, grupo_id)
            else:
                return _repo.listar_activas_asignadas(cursor, codigo)
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
            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo.strip())
            if not aliado or aliado[0] is None:
                return []
            grupo_id = aliado[0]
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            extra = _extra_cols_candidato_asignada(cols)
            return _repo.listar_propias(cursor, grupo_id, codigo.strip(), extra)
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
            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo.strip())
            if not aliado or aliado[0] is None:
                return []
            grupo_id = aliado[0]
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            extra = _extra_cols_candidato_asignada(cols)
            return _repo.listar_historial_grupo(cursor, grupo_id, limite, extra)
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
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            return _repo.listar_pendientes_por_cp(cursor, codigo_postal.strip())
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
            row = _repo.select_grupo_estado(cursor, solicitud_id)
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            grupo_id, estado = row[0], row[1]
            if estado != 'pendiente':
                return {'status': 'error', 'message': 'La solicitud ya fue atendida'}
            r2 = _repo.select_aliado_grupo_nombre(cursor, codigo.strip())
            if not r2:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            if r2[0] != grupo_id:
                return {'status': 'error', 'message': 'Solo un aliado del mismo grupo puede atender'}
            nombre_atendido = r2[1] or ''
            rowcount = _repo.update_atendida(
                cursor, solicitud_id, codigo.strip(), nombre_atendido
            )
            conn.commit()
            if rowcount == 0:
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
            cols = _repo.columnas_solicitudes(cursor)
            if 'atendido_por_codigo' not in cols or 'atendido_at' not in cols:
                return {'status': 'error', 'message': 'Tabla solicitudes sin columnas atendido_por/atendido_at'}
            row = _repo.select_atendido_info(cursor, solicitud_id)
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            estado = row[1]
            atendido_por = row[2]
            atendido_at = row[3]
            nombre_admin = (admin_codigo or '').strip() or 'Admin'
            codigo_str = (admin_codigo or '').strip()
            if estado == 'pendiente':
                _repo.update_atendida_admin(cursor, solicitud_id, codigo_str, nombre_admin)
            elif not atendido_por and not atendido_at:
                _repo.update_rellenar_atendido_admin(cursor, solicitud_id, codigo_str, nombre_admin)
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
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return
            codigo_atendido = None
            nombre_atendido = None
            if invitador_aliado_id is not None:
                row = _repo.select_aliado_codigo_nombre_por_id(cursor, int(invitador_aliado_id))
                if row:
                    codigo_atendido, nombre_atendido = row[0], row[1] or ''
            if codigo_atendido is None:
                codigo_atendido = ''
                nombre_atendido = ''
            _repo.update_atendida(cursor, solicitud_id, codigo_atendido, nombre_atendido)
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
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            return _repo.listar_admin_todas(cursor)
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
            return _repo.contar_pendientes(cursor)
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
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return 0
            estado_atendida = "atendida" if 'atendido_por_codigo' in cols else "contestada"
            return _repo.contar_enviadas_por_estado(cursor, codigo.strip(), estado_atendida)
        except Exception:
            return 0
        finally:
            conn.close()
