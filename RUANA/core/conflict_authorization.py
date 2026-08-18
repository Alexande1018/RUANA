"""Autorización granular para conflictos financieros (FASE 04.1).

Capa mínima reutilizable: deny-by-default, mapeo desde permisos legacy de admin.

Mapeo de roles legacy → permisos de conflicto
-----------------------------------------------
| Permiso legacy | Permisos de conflicto efectivos |
|----------------|----------------------------------|
| leer           | conflict.view                    |
| escribir       | view, comment, add_evidence, investigate, request_evidence |
| configurar     | todos los anteriores + resolve, escalate, close |
| eliminar       | todos (mismo nivel que configurar) |

Los permisos explícitos ``conflict.*`` en la sesión/JWT se respetan además del mapeo legacy.
"""
from __future__ import annotations

from typing import FrozenSet, Iterable, Optional, Set

# Permisos granulares (deny-by-default)
CONFLICT_VIEW = "conflict.view"
CONFLICT_ADD_EVIDENCE = "conflict.add_evidence"
CONFLICT_COMMENT = "conflict.comment"
CONFLICT_INVESTIGATE = "conflict.investigate"
CONFLICT_REQUEST_EVIDENCE = "conflict.request_evidence"
CONFLICT_RESOLVE = "conflict.resolve"
CONFLICT_ESCALATE = "conflict.escalate"
CONFLICT_CLOSE = "conflict.close"

ALL_CONFLICT_PERMISSIONS: FrozenSet[str] = frozenset({
    CONFLICT_VIEW,
    CONFLICT_ADD_EVIDENCE,
    CONFLICT_COMMENT,
    CONFLICT_INVESTIGATE,
    CONFLICT_REQUEST_EVIDENCE,
    CONFLICT_RESOLVE,
    CONFLICT_ESCALATE,
    CONFLICT_CLOSE,
})

_OPERATIONAL: FrozenSet[str] = frozenset({
    CONFLICT_VIEW,
    CONFLICT_ADD_EVIDENCE,
    CONFLICT_COMMENT,
    CONFLICT_INVESTIGATE,
    CONFLICT_REQUEST_EVIDENCE,
})

_FINANCIAL: FrozenSet[str] = frozenset({
    CONFLICT_RESOLVE,
    CONFLICT_ESCALATE,
    CONFLICT_CLOSE,
})

_LEGACY_MAP: dict[str, FrozenSet[str]] = {
    "leer": frozenset({CONFLICT_VIEW}),
    "escribir": _OPERATIONAL,
    "configurar": ALL_CONFLICT_PERMISSIONS,
    "eliminar": ALL_CONFLICT_PERMISSIONS,
}


def permisos_conflict_efectivos(permisos_legacy: Optional[Iterable[str]] = None) -> Set[str]:
    """Resuelve permisos efectivos de conflicto a partir de la lista legacy/explícita."""
    efectivos: Set[str] = set()
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if not raw:
            continue
        if raw in ALL_CONFLICT_PERMISSIONS:
            efectivos.add(raw)
            continue
        key = raw.lower()
        if key in _LEGACY_MAP:
            efectivos |= set(_LEGACY_MAP[key])
    return efectivos


def tiene_permiso_conflict(
    permisos_legacy: Optional[Iterable[str]],
    permiso_requerido: str,
) -> bool:
    """Deny-by-default: True solo si el permiso está concedido."""
    if permiso_requerido not in ALL_CONFLICT_PERMISSIONS:
        return False
    return permiso_requerido in permisos_conflict_efectivos(permisos_legacy)


def metadata_autorizacion(
    actor_codigo: str,
    permiso_usado: str,
    *,
    accion: str = "",
) -> dict:
    """Metadatos de auditoría para registrar actor y permiso empleado."""
    return {
        "actor_codigo": actor_codigo,
        "permiso_usado": permiso_usado,
        "accion_autorizacion": accion or permiso_usado,
    }
