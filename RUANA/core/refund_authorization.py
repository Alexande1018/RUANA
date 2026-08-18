"""Autorización granular para reembolsos financieros (FASE 05).

Mapeo legacy (deny-by-default):
| Legacy      | Permisos refund efectivos |
|-------------|---------------------------|
| leer        | financial.refund.view     |
| escribir    | view + request            |
| configurar  | view + request + authorize + execute + reconcile |
| eliminar    | todos                     |
"""
from __future__ import annotations

from typing import FrozenSet, Iterable, Set

REFUND_VIEW = "financial.refund.view"
REFUND_REQUEST = "financial.refund.request"
REFUND_AUTHORIZE = "financial.refund.authorize"
REFUND_EXECUTE = "financial.refund.execute"
REFUND_RECONCILE = "financial.refund.reconcile"

ALL_REFUND_PERMISSIONS: FrozenSet[str] = frozenset({
    REFUND_VIEW,
    REFUND_REQUEST,
    REFUND_AUTHORIZE,
    REFUND_EXECUTE,
    REFUND_RECONCILE,
})

_LEGACY_MAP: dict[str, FrozenSet[str]] = {
    "leer": frozenset({REFUND_VIEW}),
    "escribir": frozenset({REFUND_VIEW, REFUND_REQUEST}),
    "configurar": ALL_REFUND_PERMISSIONS,
    "eliminar": ALL_REFUND_PERMISSIONS,
}


def permisos_refund_efectivos(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    efectivos: Set[str] = set()
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if not raw:
            continue
        if raw in ALL_REFUND_PERMISSIONS:
            efectivos.add(raw)
            continue
        key = raw.lower()
        if key in _LEGACY_MAP:
            efectivos |= set(_LEGACY_MAP[key])
    return efectivos


def tiene_permiso_refund(permisos_legacy: Iterable[str] | None, permiso: str) -> bool:
    if permiso not in ALL_REFUND_PERMISSIONS:
        return False
    return permiso in permisos_refund_efectivos(permisos_legacy)
