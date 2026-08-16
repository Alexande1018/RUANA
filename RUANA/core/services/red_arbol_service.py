"""Servicio de presentación del árbol genealógico RUANA v2.

Separa PADRE (invitado_por_codigo — quién incorporó) de ORIGEN (invitado_origen — cómo llegó).
Nodos virtuales para campañas ADMIN y aliados sin atribución; no altera reglas de score.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from core.repositories.referido_repo import ReferidoRepo
from core.services import referido_service

_repo = ReferidoRepo()

# Identificadores de nodos virtuales (solo presentación; no son aliados reales)
VIRTUAL_RUANA = "__RUANA__"
VIRTUAL_SIN_ATRIBUCION = "__SIN_ATRIBUCION__"
VIRTUAL_PENDIENTE_VINCULO = "__PENDIENTE_VINCULO__"
VIRTUAL_CAMPANA_PREFIX = "__CAMPANA__:"

ORIGENES_SIN_PADRE_REAL = frozenset({
    "campana", "organico", "huerfano", "sin_atribucion",
})

ORIGEN_ALIADO_LEGACY = frozenset({"aliado", "ampliar_red", "yo_conozco_a_alguien"})


def es_nodo_virtual(codigo: str) -> bool:
    c = (codigo or "").strip()
    return (
        c == VIRTUAL_RUANA
        or c == VIRTUAL_SIN_ATRIBUCION
        or c == VIRTUAL_PENDIENTE_VINCULO
        or c.startswith(VIRTUAL_CAMPANA_PREFIX)
    )


def codigo_nodo_campana(codigo_campana: str) -> str:
    return f"{VIRTUAL_CAMPANA_PREFIX}{(codigo_campana or '').strip().upper()}"


def parse_codigo_campana(codigo_nodo: str) -> Optional[str]:
    c = (codigo_nodo or "").strip()
    if not c.startswith(VIRTUAL_CAMPANA_PREFIX):
        return None
    return c[len(VIRTUAL_CAMPANA_PREFIX):].strip() or None


def _db_text(val: Any, default: str = "") -> str:
    return referido_service._db_text(val, default)


def _enriquecer_nodo_aliado(db, nodo: Dict[str, Any], grafo: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    codigo = (nodo.get("codigo") or "").strip()
    if grafo:
        hijos = (grafo.get("hijos_por_padre") or {}).get(codigo, [])
        nodo["hijos_directos"] = len(hijos)
        nodo["tiene_hijos"] = len(hijos) > 0
    else:
        count = referido_service.contar_referidos_por_codigo(db, codigo)
        nodo["hijos_directos"] = count
        nodo["referidos_count"] = count
        nodo["tiene_hijos"] = count > 0
    estado = (nodo.get("estado") or "").strip().lower()
    nodo["tipo_nodo"] = "aliado"
    nodo["virtual"] = False
    nodo["perfil_eliminado"] = estado == "eliminado"
    nodo["perfil_pausado"] = estado == "suspendido_temporal"
    padre = (nodo.get("invitador_codigo") or "").strip()
    if not padre:
        inv = referido_service.obtener_invitador_de(db, codigo)
        if inv:
            padre = (inv.get("codigo") or "").strip()
            nodo["invitador_codigo"] = padre
            nodo["invitador_nombre"] = inv.get("nombre") or ""
    origen = (nodo.get("origen") or "").strip()
    nodo["padre_codigo"] = padre or None
    nodo["padre_nombre"] = nodo.get("invitador_nombre") or None
    nodo["origen"] = origen
    nodo["origen_label"] = db.etiqueta_origen_referido(origen)
    return nodo


def _nodo_virtual(
    codigo: str,
    nombre: str,
    tipo_nodo: str,
    *,
    subtitulo: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = meta or {}
    hijos = int(meta.get("hijos_directos") or meta.get("miembros") or 0)
    return {
        "codigo": codigo,
        "nombre": nombre,
        "oficio": subtitulo,
        "estado": "virtual",
        "score": None,
        "tipo_nodo": tipo_nodo,
        "virtual": True,
        "referidos_count": hijos,
        "hijos_directos": hijos,
        "tiene_hijos": hijos > 0,
        "origen": meta.get("origen") or "",
        "origen_label": meta.get("origen_label") or "",
        "expandible": hijos > 0,
        **{k: v for k, v in meta.items() if k not in ("hijos_directos", "miembros")},
    }


def _listar_campanas_con_miembros(db) -> List[Dict[str, Any]]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if not _repo._tabla_existe(cursor, "invitacion_campana_usos"):
                return []
            cursor.execute(
                """
                SELECT c.codigo, c.nombre, COUNT(u.codigo_aliado) AS miembros
                FROM invitacion_campanas c
                JOIN invitacion_campana_usos u ON u.codigo_campana = c.codigo
                GROUP BY c.codigo, c.nombre
                HAVING COUNT(u.codigo_aliado) > 0
                ORDER BY c.nombre ASC, c.codigo ASC
                """
            )
            return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()


def _contar_sin_atribucion(db) -> int:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            admin = db.obtener_codigo_admin_referidos()
            vis = _repo._visible_en_arbol_clause(False, "a", cursor=cursor)
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM aliados a
                WHERE {vis}
                  AND (a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = '')
                  AND COALESCE(a.invitado_origen, '') IN ('organico', 'huerfano', 'sin_atribucion', '')
                  AND a.codigo != ?
                """,
                (admin or "",),
            )
            row = cursor.fetchone()
            return int(row[0] or 0) if row else 0
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()


def listar_raices_arbol_admin(db, incluir_pendientes: bool = False) -> List[Dict[str, Any]]:
    """Raíces del bosque global: aliados reales + nodos virtuales campaña/sin atribución."""
    referido_service.sincronizar_referidos_completo(db)
    grafo = referido_service._cargar_grafo_referidos_red(db, incluir_pendientes)
    raices_codigos = referido_service._resolver_raices_referidos(db, grafo, incluir_pendientes)
    nodos: List[Dict[str, Any]] = []
    for codigo in raices_codigos:
        n = referido_service._nodo_desde_grafo(db, grafo, codigo)
        if not n:
            n = referido_service._nodo_referido_resumen(db, codigo)
        if n:
            nodos.append(_enriquecer_nodo_aliado(db, n, grafo))

    for camp in _listar_campanas_con_miembros(db):
        codigo_c = (camp.get("codigo") or "").strip()
        nodos.append(
            _nodo_virtual(
                codigo_nodo_campana(codigo_c),
                camp.get("nombre") or codigo_c,
                "campana",
                subtitulo=f"Campaña · {codigo_c}",
                meta={
                    "codigo_campana": codigo_c,
                    "miembros": int(camp.get("miembros") or 0),
                    "origen": "campana",
                    "origen_label": db.etiqueta_origen_referido("campana"),
                },
            )
        )

    sin_attr = _contar_sin_atribucion(db)
    if sin_attr > 0:
        nodos.append(
            _nodo_virtual(
                VIRTUAL_SIN_ATRIBUCION,
                "Sin atribución",
                "sin_atribucion",
                subtitulo="Registro orgánico o origen desconocido",
                meta={
                    "miembros": sin_attr,
                    "origen": "sin_atribucion",
                    "origen_label": db.etiqueta_origen_referido("sin_atribucion"),
                },
            )
        )
    return nodos


def _listar_hijos_campana(db, codigo_campana: str) -> List[Dict[str, Any]]:
    codigo_campana = (codigo_campana or "").strip().upper()
    if not codigo_campana:
        return []
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            vis = _repo._visible_en_arbol_clause(False, "a", cursor=cursor)
            cursor.execute(
                f"""
                SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                       a.estado, a.score, a.telefono, a.email, a.creado_en,
                       COALESCE(a.invitado_origen, '') AS origen
                FROM invitacion_campana_usos u
                JOIN aliados a ON a.codigo = u.codigo_aliado
                WHERE u.codigo_campana = ?
                  AND {vis}
                ORDER BY a.creado_en ASC
                """,
                (codigo_campana,),
            )
            rows = cursor.fetchall()
        except Exception:
            rows = []
        finally:
            if conn:
                conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["zona"] = item.get("codigo_postal") or ""
        item["origen"] = (item.get("origen") or "campana").strip() or "campana"
        item["origen_label"] = db.etiqueta_origen_referido(item["origen"])
        item["padre_codigo"] = None
        item["invitador_codigo"] = ""
        item = _enriquecer_nodo_aliado(db, item)
        result.append(item)
    return result


def _listar_hijos_sin_atribucion(db) -> List[Dict[str, Any]]:
    admin = db.obtener_codigo_admin_referidos()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            vis = _repo._visible_en_arbol_clause(False, "a", cursor=cursor)
            cursor.execute(
                f"""
                SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                       a.estado, a.score, a.telefono, a.email, a.creado_en,
                       COALESCE(a.invitado_origen, '') AS origen
                FROM aliados a
                WHERE {vis}
                  AND (a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = '')
                  AND COALESCE(a.invitado_origen, '') IN ('organico', 'huerfano', 'sin_atribucion', '')
                  AND a.codigo != ?
                ORDER BY a.creado_en ASC
                """,
                (admin or "",),
            )
            rows = cursor.fetchall()
        except Exception:
            rows = []
        finally:
            if conn:
                conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["zona"] = item.get("codigo_postal") or ""
        origen = (item.get("origen") or "organico").strip()
        if origen == "huerfano":
            origen = "organico"
        item["origen"] = origen or "organico"
        item["origen_label"] = db.etiqueta_origen_referido(item["origen"])
        item["padre_codigo"] = None
        item = _enriquecer_nodo_aliado(db, item)
        result.append(item)
    return result


def listar_hijos_arbol(
    db,
    codigo_padre: str,
    *,
    incluir_pendientes: bool = False,
    codigo_sesion: Optional[str] = None,
    modo_admin: bool = False,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Hijos directos de un nodo real o virtual."""
    codigo_padre = (codigo_padre or "").strip()
    if not codigo_padre:
        return None, []

    if es_nodo_virtual(codigo_padre):
        if not modo_admin:
            return None, []
        if codigo_padre == VIRTUAL_SIN_ATRIBUCION:
            return (
                _nodo_virtual(
                    VIRTUAL_SIN_ATRIBUCION,
                    "Sin atribución",
                    "sin_atribucion",
                    meta={"miembros": _contar_sin_atribucion(db)},
                ),
                _listar_hijos_sin_atribucion(db),
            )
        if codigo_padre == VIRTUAL_PENDIENTE_VINCULO:
            pendientes = _listar_hijos_pendientes_vinculo(db)
            return (
                _nodo_virtual(
                    VIRTUAL_PENDIENTE_VINCULO,
                    "Pendientes de vincular",
                    "pendiente_vinculo",
                    meta={"miembros": len(pendientes)},
                ),
                pendientes,
            )
        codigo_camp = parse_codigo_campana(codigo_padre)
        if codigo_camp:
            camp = db.obtener_campana_invitacion(codigo_camp) or {}
            nodo = _nodo_virtual(
                codigo_padre,
                camp.get("nombre") or codigo_camp,
                "campana",
                subtitulo=f"Campaña · {codigo_camp}",
                meta={"codigo_campana": codigo_camp},
            )
            return nodo, _listar_hijos_campana(db, codigo_camp)
        return None, []

    if codigo_sesion and not modo_admin:
        if not referido_service.aliado_puede_ver_nodo_referidos(db, codigo_sesion, codigo_padre):
            return None, []

    nodo = referido_service.obtener_nodo_referidos(db, codigo_padre)
    if not nodo:
        return None, []
    nodo = _enriquecer_nodo_aliado(db, nodo)
    hijos = referido_service.listar_referidos_directos(db, codigo_padre, incluir_pendientes)
    hijos_enriquecidos = [_enriquecer_nodo_aliado(db, h) for h in hijos]
    return nodo, hijos_enriquecidos


def obtener_detalle_aliado_red(
    db,
    codigo: str,
    *,
    codigo_sesion: Optional[str] = None,
    modo_admin: bool = False,
) -> Optional[Dict[str, Any]]:
    """Detalle enriquecido para panel lateral."""
    codigo = (codigo or "").strip()
    if es_nodo_virtual(codigo):
        return None
    if codigo_sesion and not modo_admin:
        if not referido_service.aliado_puede_ver_nodo_referidos(db, codigo_sesion, codigo):
            return None
    aliado = db.obtener_aliado_por_codigo(codigo)
    if not aliado:
        with db._lock:
            conn = None
            try:
                conn = db._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT codigo, nombre, marca, oficio, codigo_postal, estado, score,
                           email, telefono, creado_en, invitado_por_codigo, invitado_origen
                    FROM aliados WHERE codigo = ?
                    """,
                    (codigo,),
                )
                row = cursor.fetchone()
                if row:
                    aliado = dict(row)
            except Exception:
                aliado = None
            finally:
                if conn:
                    conn.close()
    if not aliado and modo_admin:
        eliminados = db.listar_aliados_eliminados(limite=500)
        for e in eliminados:
            if (e.get("codigo") or "").strip() == codigo:
                aliado = {
                    "codigo": codigo,
                    "nombre": e.get("nombre") or "[Perfil eliminado]",
                    "estado": "eliminado",
                    "oficio": e.get("oficio") or "",
                    "codigo_postal": e.get("codigo_postal") or "",
                    "marca": e.get("marca") or "",
                    "score": None,
                    "creado_en": e.get("eliminado_en"),
                }
                break
    if not aliado:
        return None

    invitador = referido_service.obtener_invitador_de(db, codigo)
    hijos = referido_service.contar_referidos_por_codigo(db, codigo)
    origen = (aliado.get("invitado_origen") or "").strip()
    if not origen:
        origen = db._obtener_origen_referido(codigo)

    ruta = referido_service.obtener_ruta_linaje_hacia_arriba(db, codigo)
    nivel = max(0, len(ruta) - 1)

    detalle = {
        "codigo": codigo,
        "nombre": aliado.get("nombre") or "",
        "marca": aliado.get("marca") or "",
        "oficio": aliado.get("oficio") or "",
        "codigo_postal": aliado.get("codigo_postal") or "",
        "estado": aliado.get("estado") or "activo",
        "score": aliado.get("score"),
        "email": aliado.get("email") if modo_admin else None,
        "telefono": aliado.get("telefono") if modo_admin else None,
        "creado_en": _db_text(aliado.get("creado_en")),
        "origen": origen,
        "origen_label": db.etiqueta_origen_referido(origen),
        "padre_codigo": (invitador or {}).get("codigo"),
        "padre_nombre": (invitador or {}).get("nombre"),
        "hijos_directos": hijos,
        "nivel_red": nivel,
        "perfil_eliminado": (aliado.get("estado") or "").strip().lower() == "eliminado",
        "perfil_pausado": (aliado.get("estado") or "").strip().lower() == "suspendido_temporal",
        "tipo_nodo": "aliado",
        "virtual": False,
        "permisos": {
            "puede_mensaje": False,
            "puede_pausar": modo_admin,
            "puede_eliminar": modo_admin,
        },
    }
    return detalle


def diagnostico_linaje(db) -> Dict[str, Any]:
    """Clasificación A–G de aliados para migración segura."""
    referido_service.sincronizar_referidos_completo(db)
    admin = db.obtener_codigo_admin_referidos()
    stats = {
        "total_aliados": 0,
        "padre_conocido": 0,
        "padre_desconocido": 0,
        "reconstruibles_referidos": 0,
        "contradictorios": 0,
        "campanas": 0,
        "organicos": 0,
        "sin_atribucion": 0,
        "huérfanos_visuales": 0,
    }
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            vis = _repo._visible_en_grafo_clause(False, "a", cursor=cursor)
            cursor.execute(
                f"""
                SELECT a.codigo,
                       COALESCE(a.invitado_por_codigo, '') AS padre,
                       COALESCE(a.invitado_origen, '') AS origen
                FROM aliados a
                WHERE {vis}
                  AND COALESCE(a.estado, '') != 'sistema'
                """
            )
            rows = [dict(r) for r in cursor.fetchall()]
        except Exception:
            rows = []
        finally:
            if conn:
                conn.close()

    stats["total_aliados"] = len(rows)
    for row in rows:
        padre = (row.get("padre") or "").strip()
        origen = (row.get("origen") or "").strip()
        codigo = row.get("codigo")

        if origen == "campana":
            stats["campanas"] += 1
            continue

        if padre and padre != admin:
            stats["padre_conocido"] += 1
        elif origen in ("organico", "sin_atribucion") or (not padre and origen in ("", "huerfano")):
            stats["organicos"] += 1
            stats["sin_atribucion"] += 1
        elif origen == "huerfano" and padre == admin:
            stats["sin_atribucion"] += 1
        elif not padre:
            stats["padre_desconocido"] += 1
        else:
            stats["padre_conocido"] += 1

    # Contradictorias referidos vs linaje
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if _repo.aliados_tiene_invitado_por(cursor) and _repo._tabla_existe(cursor, "referidos"):
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM aliados a
                    JOIN referidos r ON r.codigo_referido = a.codigo
                    WHERE COALESCE(a.invitado_por_codigo, '') != ''
                      AND TRIM(a.invitado_por_codigo) != TRIM(r.codigo_invitador)
                    """
                )
                stats["contradictorios"] = int((cursor.fetchone() or [0])[0])
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

    stats["huérfanos_visuales"] = stats["sin_atribucion"] + stats["campanas"]
    return stats


def migrar_linaje_historico_v2(db) -> Dict[str, int]:
    """Backfill seguro: campañas y huérfanos sin inventar padre aliado."""
    stats = {
        "campanas_sin_padre": 0,
        "huerfanos_a_organico": 0,
        "referidos_campana_limpiados": 0,
        "aliado_a_ampliar_red": 0,
    }
    admin = db.obtener_codigo_admin_referidos()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            # Campañas: quitar padre admin inventado
            if _repo.aliados_tiene_invitado_por(cursor) and _repo._tabla_existe(cursor, "invitacion_campana_usos"):
                cursor.execute(
                    """
                    UPDATE aliados
                    SET invitado_por_codigo = NULL,
                        invitado_origen = 'campana'
                    WHERE codigo IN (
                        SELECT u.codigo_aliado FROM invitacion_campana_usos u
                    )
                    AND (
                        invitado_por_codigo IS NULL
                        OR invitado_por_codigo = ?
                        OR COALESCE(invitado_origen, '') IN ('campana', 'huerfano', '')
                    )
                    """,
                    (admin or "",),
                )
                stats["campanas_sin_padre"] = cursor.rowcount
            # Huérfanos bajo admin → orgánico sin padre
            if _repo.aliados_tiene_invitado_por(cursor):
                cursor.execute(
                    """
                    UPDATE aliados
                    SET invitado_por_codigo = NULL,
                        invitado_origen = 'organico'
                    WHERE invitado_por_codigo = ?
                      AND COALESCE(invitado_origen, '') IN ('huerfano', '')
                      AND codigo NOT IN (
                          SELECT codigo_aliado FROM invitacion_campana_usos
                      )
                    """,
                    (admin or "",),
                )
                stats["huerfanos_a_organico"] = cursor.rowcount
            # Normalizar origen aliado legacy → ampliar_red donde no hay solicitud
            if _repo._tabla_existe(cursor, "invitaciones"):
                cursor.execute(
                    """
                    UPDATE aliados
                    SET invitado_origen = 'ampliar_red'
                    WHERE COALESCE(invitado_origen, '') = 'aliado'
                      AND codigo IN (
                          SELECT DISTINCT a.codigo FROM aliados a
                          JOIN referidos r ON r.codigo_referido = a.codigo
                          LEFT JOIN invitaciones i ON i.codigo = r.codigo_referido
                          WHERE i.solicitud_id IS NULL OR i.solicitud_id = 0
                      )
                    """
                )
                stats["aliado_a_ampliar_red"] = cursor.rowcount
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            if conn:
                conn.close()
    return stats


def _foto_perfil_select(cursor, alias: str = "a") -> str:
    if _repo.aliados_tiene_foto_perfil(cursor):
        return f", COALESCE({alias}.foto_perfil_url, '') AS foto_perfil_url"
    return ", '' AS foto_perfil_url"


def _enriquecer_arbol_recursivo(
    db,
    nodo: Optional[Dict[str, Any]],
    grafo: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not nodo:
        return None
    if nodo.get("virtual"):
        refs = []
        for hijo in nodo.get("referidos") or []:
            enriched = _enriquecer_arbol_recursivo(db, hijo, grafo)
            if enriched:
                refs.append(enriched)
        nodo["referidos"] = refs
        return nodo
    nodo = _enriquecer_nodo_aliado(db, nodo, grafo)
    refs = []
    for hijo in nodo.get("referidos") or []:
        enriched = _enriquecer_arbol_recursivo(db, hijo, grafo)
        if enriched:
            refs.append(enriched)
    nodo["referidos"] = refs
    return nodo


def _codigos_en_arbol(nodo: Optional[Dict[str, Any]], acc: Optional[set] = None) -> set:
    acc = acc or set()
    if not nodo:
        return acc
    codigo = (nodo.get("codigo") or "").strip()
    if codigo:
        acc.add(codigo)
    for hijo in nodo.get("referidos") or []:
        _codigos_en_arbol(hijo, acc)
    return acc


def _construir_subarbol_si_no_incluido(
    db,
    grafo: Dict[str, Any],
    codigo: str,
    max_depth: int,
    incluidos: set,
) -> Optional[Dict[str, Any]]:
    codigo = (codigo or "").strip()
    if not codigo or codigo in incluidos:
        return None
    arbol = referido_service._construir_arbol_desde_grafo(db, grafo, codigo, max_depth)
    if arbol:
        enriched = _enriquecer_arbol_recursivo(db, arbol, grafo)
        incluidos.update(_codigos_en_arbol(enriched))
        return enriched
    nodo = referido_service._nodo_desde_grafo(db, grafo, codigo)
    if not nodo:
        nodo = referido_service._nodo_referido_resumen(db, codigo)
    if not nodo:
        return None
    enriched = _enriquecer_nodo_aliado(db, nodo, grafo)
    enriched["referidos"] = []
    incluidos.add(codigo)
    return enriched


def _listar_hijos_pendientes_vinculo(db) -> List[Dict[str, Any]]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_aliados_fuera_red(cursor)
        except Exception:
            rows = []
        finally:
            if conn:
                conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["zona"] = item.get("codigo_postal") or ""
        origen = (item.get("origen") or "sin_atribucion").strip() or "sin_atribucion"
        item["origen"] = origen
        item["origen_label"] = db.etiqueta_origen_referido(origen)
        item["padre_codigo"] = None
        item = _enriquecer_nodo_aliado(db, item)
        result.append(item)
    return result


def obtener_bosque_arbol_admin_completo(
    db,
    max_depth: int = 50,
    incluir_pendientes: bool = True,
) -> List[Dict[str, Any]]:
    """Bosque admin con todos los aliados: raíces reales, campañas, sin atribución y pendientes."""
    referido_service.sincronizar_referidos_completo(db)
    max_depth = max(1, min(int(max_depth or 50), 50))
    grafo = referido_service._cargar_grafo_referidos_red(db, incluir_pendientes)
    incluidos: set = set()
    bosques: List[Dict[str, Any]] = []

    raices = referido_service._resolver_raices_referidos(db, grafo, incluir_pendientes)
    for codigo in raices:
        arbol = _construir_subarbol_si_no_incluido(db, grafo, codigo, max_depth, incluidos)
        if arbol:
            bosques.append(arbol)

    for camp in _listar_campanas_con_miembros(db):
        codigo_c = (camp.get("codigo") or "").strip()
        hijos_planos = _listar_hijos_campana(db, codigo_c)
        hijos_arboles: List[Dict[str, Any]] = []
        for h in hijos_planos:
            hc = (h.get("codigo") or "").strip()
            sub = _construir_subarbol_si_no_incluido(db, grafo, hc, max_depth, incluidos)
            if sub:
                hijos_arboles.append(sub)
        if hijos_arboles:
            bosques.append(
                _nodo_virtual(
                    codigo_nodo_campana(codigo_c),
                    camp.get("nombre") or codigo_c,
                    "campana",
                    subtitulo=f"Campaña · {codigo_c}",
                    meta={
                        "codigo_campana": codigo_c,
                        "miembros": len(hijos_arboles),
                        "origen": "campana",
                        "origen_label": db.etiqueta_origen_referido("campana"),
                        "referidos": hijos_arboles,
                    },
                )
            )

    sin_hijos = _listar_hijos_sin_atribucion(db)
    sin_arboles: List[Dict[str, Any]] = []
    for h in sin_hijos:
        hc = (h.get("codigo") or "").strip()
        sub = _construir_subarbol_si_no_incluido(db, grafo, hc, max_depth, incluidos)
        if sub:
            sin_arboles.append(sub)
    if sin_arboles:
        bosques.append(
            _nodo_virtual(
                VIRTUAL_SIN_ATRIBUCION,
                "Sin atribución",
                "sin_atribucion",
                subtitulo="Registro orgánico o origen desconocido",
                meta={
                    "miembros": len(sin_arboles),
                    "origen": "sin_atribucion",
                    "origen_label": db.etiqueta_origen_referido("sin_atribucion"),
                    "referidos": sin_arboles,
                },
            )
        )

    pendientes = _listar_hijos_pendientes_vinculo(db)
    pend_arboles: List[Dict[str, Any]] = []
    for h in pendientes:
        hc = (h.get("codigo") or "").strip()
        sub = _construir_subarbol_si_no_incluido(db, grafo, hc, max_depth, incluidos)
        if sub:
            pend_arboles.append(sub)
    if pend_arboles:
        bosques.append(
            _nodo_virtual(
                VIRTUAL_PENDIENTE_VINCULO,
                "Pendientes de vincular",
                "pendiente_vinculo",
                subtitulo="Aliados registrados sin linaje completo",
                meta={
                    "miembros": len(pend_arboles),
                    "origen": "sin_atribucion",
                    "origen_label": "Pendiente de vincular",
                    "referidos": pend_arboles,
                },
            )
        )

    return bosques
