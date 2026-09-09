"""Recomendación de profesional cercano sin abrir el directorio de otros grupos."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from core.db_constants import PROXIMIDAD_DISTANCIA_MAX, PROXIMIDAD_NIVEL_MAX
from core.repositories.territorio_repo import TerritorioRepo
from core.services import catalogo_service, notificacion_service, territorio_service

_repo = TerritorioRepo()


def _row_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return dict(row)
    return {}


def _escanear_candidatos(
    db,
    cursor,
    oficio: str,
    grupo_id: int,
    codigo: str,
    cp_viewer: str,
) -> Optional[Dict[str, Any]]:
    candidatos = []
    for row in _repo.listar_profesionales_oficio_fuera_grupo(
        cursor, oficio, int(grupo_id), codigo
    ):
        item = _row_dict(row)
        if not catalogo_service.oficios_equivalentes(db, oficio, item.get("oficio") or ""):
            continue
        cp_other = (item.get("codigo_postal") or item.get("grupo_cp") or "").strip()
        # Catálogo estático: no abrir otra conexión mientras el caller ya tiene una.
        nivel, orden = territorio_service.proximidad_territorial(cp_viewer, cp_other)
        if nivel > PROXIMIDAD_NIVEL_MAX:
            continue
        if nivel == 2 and orden > PROXIMIDAD_DISTANCIA_MAX:
            continue
        item["nivel_proximidad"] = nivel
        item["orden_proximidad"] = orden
        if nivel == 1:
            item["etiqueta_proximidad"] = "Mismo código postal, otro grupo"
        elif nivel == 2:
            item["etiqueta_proximidad"] = "Misma ciudad"
        else:
            item["etiqueta_proximidad"] = "Cercano"
        candidatos.append(item)
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: (x.get("nivel_proximidad", 9), x.get("orden_proximidad", 9999)))
    best = candidatos[0]
    return {
        "codigo": best.get("codigo"),
        "nombre": best.get("nombre"),
        "oficio": best.get("oficio"),
        "codigo_postal": best.get("codigo_postal"),
        "etiqueta_proximidad": best.get("etiqueta_proximidad"),
        "nivel_proximidad": best.get("nivel_proximidad"),
        "mismo_grupo": False,
    }


def recomendar_profesional(
    db,
    codigo_aliado: str,
    oficio: str,
    *,
    cursor=None,
    aliado: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Devuelve el profesional activo más cercano del oficio pedido que no pertenece
    al grupo del solicitante. No lista el directorio ajeno: un único candidato.

    Si el caller ya tiene conexión abierta, pasa ``cursor`` y ``aliado`` para no
    abrir una segunda conexión (en Postgres eso deja el envío colgado).
    """
    codigo = (codigo_aliado or "").strip()
    of = (oficio or "").strip()
    if not codigo or not of:
        return None
    if cursor is not None:
        ctx = aliado or {}
        grupo_id = ctx.get("grupo_id")
        if not grupo_id:
            return None
        cp_viewer = (ctx.get("codigo_postal") or "").strip()
        try:
            return _escanear_candidatos(db, cursor, of, int(grupo_id), codigo, cp_viewer)
        except Exception as exc:
            print(f"Error recomendar_profesional: {exc}")
            return None
    row = db.obtener_aliado_por_codigo(codigo)
    if not row:
        return None
    grupo_id = row.get("grupo_id")
    if not grupo_id:
        return None
    cp_viewer = (row.get("codigo_postal") or "").strip()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            return _escanear_candidatos(
                db, conn.cursor(), of, int(grupo_id), codigo, cp_viewer
            )
        except Exception as exc:
            print(f"Error recomendar_profesional: {exc}")
            return None
        finally:
            if conn:
                conn.close()


def solicitar_contacto_proximidad(
    db,
    solicitante_codigo: str,
    oficio: str,
    profesional_codigo: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Notifica al profesional recomendado. No concede acceso al directorio del otro grupo.
    """
    solicitante = (solicitante_codigo or "").strip()
    of = (oficio or "").strip()
    if not solicitante or not of:
        return {"status": "error", "message": "Solicitante y oficio obligatorios"}
    rec = None
    if profesional_codigo:
        rec = recomendar_profesional(db, solicitante, of)
        if rec and rec.get("codigo") != (profesional_codigo or "").strip():
            dest = db.obtener_aliado_por_codigo((profesional_codigo or "").strip())
            sol = db.obtener_aliado_por_codigo(solicitante)
            if dest and sol and dest.get("grupo_id") != sol.get("grupo_id"):
                rec = {
                    "codigo": dest.get("codigo"),
                    "nombre": dest.get("nombre"),
                    "oficio": dest.get("oficio"),
                    "codigo_postal": dest.get("codigo_postal"),
                    "etiqueta_proximidad": "Profesional cercano",
                    "nivel_proximidad": 2,
                    "mismo_grupo": False,
                }
            else:
                rec = None
    if rec is None:
        rec = recomendar_profesional(db, solicitante, of)
    if not rec:
        return {"status": "success", "proximidad": None, "notificado": False}
    sol_row = db.obtener_aliado_por_codigo(solicitante) or {}
    nombre_sol = sol_row.get("nombre") or solicitante
    notificacion_service.crear_notificacion_aliado(
        db,
        rec["codigo"],
        tipo="proximidad_solicitud",
        titulo="Solicitud de un aliado cercano",
        mensaje=(
            f"{nombre_sol} busca un profesional de {of} y no hay plaza de ese oficio "
            f"en su grupo territorial. Su código postal es "
            f"{(sol_row.get('codigo_postal') or '—')}."
        ),
        metadata={
            "solicitante_codigo": solicitante,
            "oficio": of,
            "codigo_postal_solicitante": sol_row.get("codigo_postal"),
        },
    )
    return {"status": "success", "proximidad": rec, "notificado": True}
