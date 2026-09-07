"""Servicio territorial: resolución CP → ciudad y proximidad (v1 extensible)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.db_constants import RUANA_ROOT

_CATALOG_PATH = RUANA_ROOT / "config" / "cp_ciudad_es.json"
_CATALOG_CACHE: Optional[Dict[str, Any]] = None


def _cargar_catalogo() -> Dict[str, Any]:
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE
    try:
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            _CATALOG_CACHE = json.load(f)
    except Exception:
        _CATALOG_CACHE = {"prefijos": {}, "exactos": {}}
    return _CATALOG_CACHE


def normalizar_ciudad(ciudad: str) -> str:
    t = (ciudad or "").strip()
    if not t:
        return ""
    return re.sub(r"\s+", " ", t)


def resolver_ciudad_por_cp(codigo_postal: str) -> Optional[Dict[str, str]]:
    """Resuelve ciudad/provincia desde catálogo estático (exacto → prefijo 2 dígitos)."""
    cp = (codigo_postal or "").strip()
    if not cp or not cp.isdigit():
        return None
    cat = _cargar_catalogo()
    exactos = cat.get("exactos") or {}
    if cp in exactos:
        row = exactos[cp]
        return {
            "ciudad": normalizar_ciudad(row.get("ciudad") or ""),
            "provincia": normalizar_ciudad(row.get("provincia") or ""),
        }
    prefijos = cat.get("prefijos") or {}
    if len(cp) >= 2:
        pref = cp[:2]
        if pref in prefijos:
            row = prefijos[pref]
            return {
                "ciudad": normalizar_ciudad(row.get("ciudad") or ""),
                "provincia": normalizar_ciudad(row.get("provincia") or ""),
            }
    return None


def asegurar_cp_ciudad_en_bd(db, codigo_postal: str) -> Optional[Dict[str, str]]:
    """Persiste CP→ciudad en tabla cp_ciudad si se puede resolver."""
    cp = (codigo_postal or "").strip()
    if not cp:
        return None
    resuelto = resolver_ciudad_por_cp(cp)
    if not resuelto or not resuelto.get("ciudad"):
        return resuelto
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO cp_ciudad (codigo_postal, ciudad, provincia)
                VALUES (?, ?, ?)
                ON CONFLICT(codigo_postal) DO UPDATE SET
                    ciudad = excluded.ciudad,
                    provincia = excluded.provincia
                """,
                (cp, resuelto["ciudad"], resuelto.get("provincia") or None),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()
    return resuelto


def resolver_ciudad(db, codigo_postal: str) -> Optional[Dict[str, str]]:
    """Primero BD, luego catálogo estático."""
    cp = (codigo_postal or "").strip()
    if not cp:
        return None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ciudad, provincia FROM cp_ciudad WHERE codigo_postal = ?",
                (cp,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return {"ciudad": row[0], "provincia": row[1] or ""}
        except Exception:
            pass
        finally:
            if conn:
                conn.close()
    resuelto = resolver_ciudad_por_cp(cp)
    if resuelto:
        asegurar_cp_ciudad_en_bd(db, cp)
    return resuelto


def cp_misma_ciudad(cp_a: str, cp_b: str, db=None) -> bool:
    """True si ambos CP pertenecen a la misma ciudad según catálogo/BD."""
    a = (cp_a or "").strip()
    b = (cp_b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    if db is not None:
        ra = resolver_ciudad(db, a)
        rb = resolver_ciudad(db, b)
    else:
        ra = resolver_ciudad_por_cp(a)
        rb = resolver_ciudad_por_cp(b)
    if not ra or not rb:
        return False
    return normalizar_ciudad(ra.get("ciudad") or "").lower() == normalizar_ciudad(
        rb.get("ciudad") or ""
    ).lower()


def distancia_cp_heuristica(cp_a: str, cp_b: str) -> int:
    """
    Heurística determinista v1 para ordenar CPs de la misma ciudad.
    Sustituible por coordenadas/geo sin cambiar la API de proximidad_territorial.
    Combina longitud de prefijo común y diferencia numérica.
    """
    a = (cp_a or "").strip()
    b = (cp_b or "").strip()
    if a == b:
        return 0
    prefijo = 0
    for x, y in zip(a, b):
        if x == y:
            prefijo += 1
        else:
            break
    try:
        diff = abs(int(a) - int(b))
    except ValueError:
        diff = 9999
    # Mayor prefijo común = más cercano; menor diff numérica = más cercano
    return max(0, 1000 - prefijo * 100 + min(diff, 999))


def proximidad_territorial(
    cp_viewer: str,
    cp_other: str,
    db=None,
) -> Tuple[int, int]:
    """
    Devuelve (nivel, orden) para sorting: nivel 1=mismo CP, 2=misma ciudad, 3=otro.
    """
    v = (cp_viewer or "").strip()
    o = (cp_other or "").strip()
    if not v or not o:
        return (3, 9999)
    if v == o:
        return (1, 0)
    if cp_misma_ciudad(v, o, db=db):
        return (2, distancia_cp_heuristica(v, o))
    return (3, 9999)
