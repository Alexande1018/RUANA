"""Servicio de dominio notificación (Campamento Base).

Extracción desde DBManager. Las fachadas permanecen en DBManager.
SQL de notificaciones vía NotificacionRepo.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from core.repositories.notificacion_repo import NotificacionRepo

_repo = NotificacionRepo()

MAX_ACTIVIDAD_CINTA = 10

# Tipos operativos/personales que no deben aparecer en la cinta de actividad.
_CINTA_TIPOS_EXCLUIDOS = frozenset({
    "apoyo_ruana",
    "pago_aceptado",
    "pago_rechazado",
    "pago_stripe",
    "importe_impugnado",
    "prueba_conflicto_en_revision",
    "ruana_soporte",
    "ruana_soporte_estado",
    "score_change",
})


def _parse_creado_en(valor: Any) -> float:
    """Ordena por fecha real cuando exista; 0 si no es parseable."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return 0.0
    normalizado = texto.replace("Z", "+00:00")
    if " " in normalizado and "T" not in normalizado:
        normalizado = normalizado.replace(" ", "T", 1)
    try:
        from datetime import datetime

        return datetime.fromisoformat(normalizado).timestamp()
    except Exception:
        return 0.0


def _metadata_dict(notif: Dict[str, Any]) -> Dict[str, Any]:
    meta = notif.get("metadata")
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str) and meta.strip():
        try:
            parsed = json.loads(meta)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _formatear_notificacion_cinta(notif: Dict[str, Any]) -> Optional[str]:
    """Convierte una notificación existente en texto humano para la cinta."""
    tipo = str(notif.get("tipo") or "").strip()
    if not tipo or tipo in _CINTA_TIPOS_EXCLUIDOS:
        return None

    meta = _metadata_dict(notif)
    mensaje = str(notif.get("mensaje") or "").strip()

    if tipo == "solicitud_semanal_nueva":
        nombre = str(meta.get("solicitante_nombre") or "Un aliado").strip()
        return f"Nueva solicitud publicada por {nombre} en el grupo"

    if tipo == "solicitud_asignada":
        oficio = str(meta.get("oficio") or "").strip()
        if oficio:
            return f"Nueva solicitud de {oficio}"
        if mensaje:
            return mensaje
        return "Una solicitud acaba de ser asignada"

    if tipo == "competencia_inicio":
        return "Nueva competencia iniciada en tu grupo"

    if tipo == "competencia_titular":
        oficio = str(meta.get("oficio") or "").strip()
        if oficio:
            return f"Nueva competencia iniciada en tu grupo por {oficio}"
        return "Nueva competencia iniciada en tu grupo"

    if tipo == "competencia_victoria":
        oficio = str(meta.get("oficio") or "").strip()
        if oficio:
            return f"Acabas de ganar una competencia por {oficio}"
        return "Acabas de ganar una competencia"

    if tipo in ("competencia_derrota", "competencia_expulsion"):
        return "Has perdido una competencia"

    return None


def _formatear_aviso_grupo_cinta(aviso: Dict[str, Any]) -> Optional[str]:
    texto = str(aviso.get("texto") or "").strip()
    if not texto:
        return None
    tipo = str(aviso.get("tipo") or "").strip().lower()
    if tipo == "competencia":
        return "Nueva competencia iniciada en tu grupo"
    return texto


def preparar_actividad_cinta(
    db,
    aliado_codigo: str,
    avisos_grupo: Optional[List[Dict[str, Any]]] = None,
    limite: int = MAX_ACTIVIDAD_CINTA,
) -> List[Dict[str, Any]]:
    """Prepara hasta 10 noticias reales para la cinta (más reciente → más antigua)."""
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm:
        return []

    limite_final = max(0, min(int(limite or MAX_ACTIVIDAD_CINTA), MAX_ACTIVIDAD_CINTA))
    if limite_final == 0:
        return []

    items: List[Dict[str, Any]] = []

    for notif in listar_notificaciones_aliado(db, codigo_norm, limite=50):
        texto = _formatear_notificacion_cinta(notif)
        if not texto:
            continue
        notif_id = notif.get("id")
        items.append(
            {
                "id": f"notif-{notif_id}" if notif_id is not None else f"notif-{len(items)}",
                "texto": texto,
                "creado_en": notif.get("creado_en"),
                "tipo": notif.get("tipo"),
                "fuente": "notificacion",
            }
        )

    for aviso in avisos_grupo or []:
        texto = _formatear_aviso_grupo_cinta(aviso)
        if not texto:
            continue
        aviso_id = aviso.get("id")
        items.append(
            {
                "id": f"aviso-{aviso_id}" if aviso_id is not None else f"aviso-{len(items)}",
                "texto": texto,
                "creado_en": aviso.get("creado_en"),
                "tipo": aviso.get("tipo"),
                "fuente": "aviso_grupo",
            }
        )

    items.sort(key=lambda item: _parse_creado_en(item.get("creado_en")), reverse=True)

    vistos: set = set()
    unicos: List[Dict[str, Any]] = []
    for item in items:
        clave = item.get("texto")
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(item)
        if len(unicos) >= limite_final:
            break

    return unicos


def preparar_actividad_cinta_para_aliado(
    db,
    aliado_codigo: str,
    limite: int = MAX_ACTIVIDAD_CINTA,
) -> List[Dict[str, Any]]:
    """Prepara la cinta con avisos de grupo del aliado cuando corresponda."""
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm:
        return []

    avisos_grupo: List[Dict[str, Any]] = []
    try:
        aliado = db.obtener_aliado_por_codigo(codigo_norm)
        grupo_id = aliado.get("grupo_id") if aliado else None
        if grupo_id:
            avisos_grupo = db.obtener_avisos_grupo(grupo_id)
    except Exception:
        avisos_grupo = []

    return preparar_actividad_cinta(
        db, codigo_norm, avisos_grupo=avisos_grupo, limite=limite
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
