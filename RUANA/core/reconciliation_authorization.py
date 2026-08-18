"""Autorización granular para reconciliación financiera (FASE 07). Deny-by-default."""
from __future__ import annotations

from typing import FrozenSet, Iterable, Set

RECON_VIEW = "financial.reconciliation.view"
RECON_EXECUTE = "financial.reconciliation.execute"
RECON_RESOLVE = "financial.reconciliation.resolve"

ALL_RECON_PERMISSIONS: FrozenSet[str] = frozenset({
    RECON_VIEW,
    RECON_EXECUTE,
    RECON_RESOLVE,
})

_LEGACY_MAP: dict[str, FrozenSet[str]] = {
    "leer": frozenset({RECON_VIEW}),
    "escribir": frozenset({RECON_VIEW, RECON_EXECUTE}),
    "configurar": ALL_RECON_PERMISSIONS,
    "eliminar": ALL_RECON_PERMISSIONS,
}


def permisos_recon_efectivos(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    efectivos: Set[str] = set()
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if not raw:
            continue
        if raw in ALL_RECON_PERMISSIONS:
            efectivos.add(raw)
            continue
        key = raw.lower()
        if key in _LEGACY_MAP:
            efectivos |= set(_LEGACY_MAP[key])
    return efectivos


def tiene_permiso_recon(permisos_legacy: Iterable[str] | None, permiso: str) -> bool:
    if permiso not in ALL_RECON_PERMISSIONS:
        return False
    return permiso in permisos_recon_efectivos(permisos_legacy)
