"""Resumen y bootstrap del panel admin (conteos compartidos)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.services import (
    admin_service,
    aliado_service,
    catalogo_service,
    grupo_service,
    solicitud_service,
)

_BOOTSTRAP_TTL_S = 20.0
_META_CLAVE = "admin_bootstrap"
_bootstrap_cache: Dict[str, Any] = {"ts": 0.0, "generation": None, "payload": None}


SUMMARY_COUNT_KEYS = (
    "total_users",
    "active_users",
    "retadores",
    "suplentes",
    "en_espera",
    "en_riesgo",
    "solicitudes_activas",
    "oficios_ocupados",
    "grupos",
    "grupos_activos",
    "grupos_en_competencia",
    "grupos_disueltos",
    "aliados_sin_grupo_territorial",
    "estado_sistema",
)


def _estado_sistema(en_riesgo: int, active_users: int, contactos_metricas: Dict[str, Any]) -> str:
    contactos_disputa = contactos_metricas.get("contactos_en_disputa", 0) or 0
    contactos_disputa_prolongada = contactos_metricas.get(
        "contactos_en_disputa_prolongada", 0
    ) or 0
    pct_riesgo = (en_riesgo / active_users * 100) if active_users else 0
    if pct_riesgo <= 10 and contactos_disputa <= 2 and contactos_disputa_prolongada == 0:
        return "Estable"
    if pct_riesgo <= 25 and contactos_disputa <= 5:
        return "Alerta"
    return "Cr?tico"


def build_dashboard_summary(
    db,
    aliados: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Misma fórmula que GET /api/admin/dashboard-summary.

    Un solo ``listar_aliados`` (sin backfill) si no se pasa ``aliados``.
    Sigue siendo el SQL caro de ``listar_admin`` (``a.*`` + 5 subconsultas
    por fila): la mejora es llamarlo una vez, no aligerar la query.
    """
    if aliados is None:
        aliados = aliado_service.listar_aliados(db)
    total_users = len(aliados)
    active_users = len([a for a in aliados if a.get("estado") == "activo"])
    retadores = db.contar_retadores_activos()
    suplentes = retadores
    en_espera = db.contar_aliados_en_espera() if hasattr(db, "contar_aliados_en_espera") else 0
    en_riesgo = db.contar_aliados_en_riesgo()
    solicitudes_activas = solicitud_service.contar_solicitudes_activas(db)
    oficios_ocupados = catalogo_service.contar_oficios_ocupados(db)
    grupos_data = grupo_service.contar_grupos(db)
    grupos = int(grupos_data.get("total", 0) or 0)
    from core.services import territorio_migracion_service

    check = territorio_migracion_service.comprobar_migracion(db)
    sin_territorial = int(check.get("total") or 0)
    contactos_metricas = admin_service.obtener_metricas_contactos(db)
    estado_sistema = _estado_sistema(en_riesgo, active_users, contactos_metricas)
    summary = {
        "total_users": total_users,
        "active_users": active_users,
        "retadores": retadores,
        "suplentes": suplentes,
        "en_espera": en_espera,
        "en_riesgo": en_riesgo,
        "solicitudes_activas": solicitudes_activas,
        "oficios_ocupados": oficios_ocupados,
        "grupos": grupos,
        "grupos_activos": int(grupos_data.get("activos", 0) or 0),
        "grupos_en_competencia": int(grupos_data.get("en_competencia", 0) or 0),
        "grupos_disueltos": int(grupos_data.get("disueltos", 0) or 0),
        "aliados_sin_grupo_territorial": sin_territorial,
        "estado_sistema": estado_sistema,
    }
    return summary, aliados


_LITE_KEYS = (
    "codigo",
    "nombre",
    "codigo_postal",
    "oficio",
    "oficio_principal",
    "estado",
    "estado_panel",
    "score",
    "score_panel",
    "grupo_id",
    "grupo_nombre",
    "zona",
    "invitado_por_codigo",
    "invitado_por_nombre",
    "invitado_origen",
    "invitado_origen_label",
    "hijos_directos_count",
    "especializaciones",
    "ciudad",
    "provincia",
)


def aliados_lite(aliados: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in aliados:
        item = {k: raw.get(k) for k in _LITE_KEYS if k in raw or k in (
            "codigo", "nombre", "estado", "codigo_postal", "grupo_id"
        )}
        out.append(item)
    return out


def build_admin_bootstrap(db, permisos: Optional[List[str]] = None) -> Dict[str, Any]:
    summary, aliados = build_dashboard_summary(db)
    pendientes = aliado_service.listar_aliados_pendiente_validacion(db)
    payload = {
        "status": "success",
        "summary": summary,
        "aliados": aliados,
        "pendientes": pendientes,
        "permisos": list(permisos or []),
    }
    return payload


def _ensure_meta_table(cursor) -> None:
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS ruana_cache_meta ("
        "clave TEXT PRIMARY KEY,"
        "generacion INTEGER NOT NULL DEFAULT 0"
        ")"
    )


def _generation_from_row(row: Any) -> int:
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(row.get("generacion") or 0)
    try:
        return int(row["generacion"])
    except (KeyError, TypeError, IndexError):
        return int(row[0])


def read_admin_bootstrap_generation(db) -> int:
    """Generación compartida (SQLite/Postgres). Visible para todos los workers."""
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _ensure_meta_table(cursor)
            cursor.execute(
                "SELECT generacion FROM ruana_cache_meta WHERE clave = ?",
                (_META_CLAVE,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "INSERT INTO ruana_cache_meta (clave, generacion) VALUES (?, 0)",
                    (_META_CLAVE,),
                )
                conn.commit()
                return 0
            return _generation_from_row(row)
        finally:
            conn.close()


def bump_admin_bootstrap_generation(db) -> int:
    """Invalida el cache en todos los workers: incrementa la generación en BD."""
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _ensure_meta_table(cursor)
            cursor.execute(
                "UPDATE ruana_cache_meta SET generacion = generacion + 1 WHERE clave = ?",
                (_META_CLAVE,),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) == 0:
                cursor.execute(
                    "INSERT INTO ruana_cache_meta (clave, generacion) VALUES (?, 1)",
                    (_META_CLAVE,),
                )
                generation = 1
            else:
                cursor.execute(
                    "SELECT generacion FROM ruana_cache_meta WHERE clave = ?",
                    (_META_CLAVE,),
                )
                generation = _generation_from_row(cursor.fetchone())
            conn.commit()
        finally:
            conn.close()
    clear_admin_bootstrap_cache()
    return generation


def get_admin_bootstrap_cached(db, permisos: Optional[List[str]] = None) -> Dict[str, Any]:
    now = time.time()
    generation = read_admin_bootstrap_generation(db)
    cached = _bootstrap_cache.get("payload")
    ts = float(_bootstrap_cache.get("ts") or 0)
    cached_gen = _bootstrap_cache.get("generation")
    if (
        cached
        and cached_gen == generation
        and (now - ts) < _BOOTSTRAP_TTL_S
    ):
        data = dict(cached)
        data["permisos"] = list(permisos or [])
        data["cache"] = "hit"
        data["generation"] = generation
        return data
    payload = build_admin_bootstrap(db, permisos=permisos)
    _bootstrap_cache["ts"] = now
    _bootstrap_cache["generation"] = generation
    _bootstrap_cache["payload"] = {
        "status": payload["status"],
        "summary": payload["summary"],
        "aliados": payload["aliados"],
        "pendientes": payload["pendientes"],
    }
    out = dict(payload)
    out["cache"] = "miss"
    out["generation"] = generation
    return out


def clear_admin_bootstrap_cache() -> None:
    _bootstrap_cache["ts"] = 0.0
    _bootstrap_cache["generation"] = None
    _bootstrap_cache["payload"] = None
