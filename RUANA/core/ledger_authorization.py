"""Autorización granular del ledger financiero (FASE 08). Deny-by-default."""
from __future__ import annotations

from typing import FrozenSet, Iterable, Set

LEDGER_VIEW = "financial.ledger.view"
LEDGER_RECONCILE = "financial.ledger.reconcile"
LEDGER_ADJUST = "financial.ledger.adjust"
LEDGER_VOID = "financial.ledger.void"

ALL_LEDGER_PERMISSIONS: FrozenSet[str] = frozenset({
    LEDGER_VIEW,
    LEDGER_RECONCILE,
    LEDGER_ADJUST,
    LEDGER_VOID,
})

_LEGACY_MAP: dict[str, FrozenSet[str]] = {
    "leer": frozenset({LEDGER_VIEW}),
    "escribir": frozenset({LEDGER_VIEW, LEDGER_RECONCILE}),
    "configurar": ALL_LEDGER_PERMISSIONS,
    "eliminar": ALL_LEDGER_PERMISSIONS,
}


def permisos_ledger_efectivos(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    efectivos: Set[str] = set()
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if not raw:
            continue
        if raw in ALL_LEDGER_PERMISSIONS:
            efectivos.add(raw)
            continue
        key = raw.lower()
        if key in _LEGACY_MAP:
            efectivos |= set(_LEGACY_MAP[key])
    return efectivos


def tiene_permiso_ledger(permisos_legacy: Iterable[str] | None, permiso: str) -> bool:
    if permiso not in ALL_LEDGER_PERMISSIONS:
        return False
    return permiso in permisos_ledger_efectivos(permisos_legacy)
