"""Servicio de dominio notificación (Campamento Base).

Extracción desde DBManager. Las fachadas permanecen en DBManager.
SQL de notificaciones vía NotificacionRepo.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from core.repositories.notificacion_repo import NotificacionRepo
from core.services import actividad_cinta_service

_repo = NotificacionRepo()

MAX_ACTIVIDAD_CINTA = actividad_cinta_service.MAX_ACTIVIDAD_CINTA


def preparar_actividad_cinta(
    db,
    aliado_codigo: str,
    avisos_grupo: Optional[List[Dict[str, Any]]] = None,
    limite: int = MAX_ACTIVIDAD_CINTA,
) -> List[Dict[str, Any]]:
    """Fachada → actividad_cinta_service (fuente única de la cinta)."""
    return actividad_cinta_service.preparar_actividad_cinta(
        db, aliado_codigo, avisos_grupo=avisos_grupo, limite=limite
    )


def preparar_actividad_cinta_para_aliado(
    db,
    aliado_codigo: str,
    limite: int = MAX_ACTIVIDAD_CINTA,
) -> List[Dict[str, Any]]:
    """Fachada → actividad_cinta_service."""
    return actividad_cinta_service.preparar_actividad_cinta_para_aliado(
        db, aliado_codigo, limite=limite
    )


def notificar_grupo_actividad(
    db,
    grupo_id: int,
    tipo: str,
    titulo: str,
    mensaje: str,
    metadata: Optional[Dict[str, Any]] = None,
    excluir_codigo: Optional[str] = None,
    cursor=None,
) -> None:
    """Fachada → actividad_cinta_service."""
    return actividad_cinta_service.notificar_grupo_actividad(
        db,
        grupo_id,
        tipo,
        titulo,
        mensaje,
        metadata=metadata,
        excluir_codigo=excluir_codigo,
        cursor=cursor,
    )


def crear_notificacion_aliado(
    db,
    aliado_codigo: str,
    tipo: str,
    titulo: str,
    mensaje: str,
    metadata: Optional[Dict[str, Any]] = None,
    cursor=None,
) -> None:
    """Inserta una notificación persistente para un aliado."""
    codigo = (aliado_codigo or "").strip()
    if not codigo:
        return
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    try:
        if cursor is not None:
            _repo.insertar(cursor, codigo, tipo, titulo, mensaje, meta_json)
            return
        with db._lock:
            conn = db._connect()
            try:
                cur = conn.cursor()
                _repo.insertar(cur, codigo, tipo, titulo, mensaje, meta_json)
                conn.commit()
            finally:
                conn.close()
    except Exception:
        return


def listar_notificaciones_aliado(
    db, aliado_codigo: str, limite: int = 50
) -> List[Dict[str, Any]]:
    """Lista notificaciones del aliado. metadata es JSON con qr_paypal_path, bizum_num, etc."""
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm:
        return []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_por_aliado(
                cursor, codigo_norm, max(1, min(limite, 200))
            )
            out = []
            for item in rows:
                if item.get("metadata"):
                    try:
                        item["metadata"] = json.loads(item["metadata"])
                    except Exception:
                        pass
                out.append(item)
            return out
        except Exception as e:
            print(f"Error listando notificaciones aliado: {e}")
            return []
        finally:
            conn.close()


def marcar_notificacion_leida(
    db, notificacion_id: int, aliado_codigo: str
) -> Dict[str, Any]:
    """Marca una notificación como leída solo si pertenece al aliado."""
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm:
        return {"status": "error", "message": "Código requerido"}
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            rowcount = _repo.marcar_leida(cursor, notificacion_id, codigo_norm)
            conn.commit()
            if rowcount > 0:
                return {"status": "success"}
            return {
                "status": "error",
                "message": "Notificación no encontrada o no pertenece al aliado",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def marcar_todas_notificaciones_leidas(db, aliado_codigo: str) -> Dict[str, Any]:
    """Marca todas las notificaciones del aliado como leídas."""
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm:
        return {"status": "error", "message": "Código requerido"}
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            actualizadas = _repo.marcar_todas_leidas(cursor, codigo_norm)
            conn.commit()
            return {"status": "success", "actualizadas": actualizadas}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def marcar_notificaciones_contacto_leidas(
    db,
    cursor,
    aliado_codigo: str,
    contacto_id: int,
    tipos: Optional[List[str]] = None,
) -> int:
    """Marca como leídas las notificaciones de un aliado ligadas a un contacto."""
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm or not contacto_id:
        return 0
    return _repo.marcar_contacto_leidas(cursor, codigo_norm, contacto_id, tipos)
