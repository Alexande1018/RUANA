"""Autorización granular para disputas Stripe (FASE 06). Deny-by-default."""
from __future__ import annotations

from typing import FrozenSet, Iterable, Set

DISPUTE_VIEW = "financial.dispute.view"
DISPUTE_INVESTIGATE = "financial.dispute.investigate"
DISPUTE_ADD_EVIDENCE = "financial.dispute.add_evidence"
DISPUTE_SUBMIT_EVIDENCE = "financial.dispute.submit_evidence"
DISPUTE_RESOLVE = "financial.dispute.resolve"
DISPUTE_RECONCILE = "financial.dispute.reconcile"

ALL_DISPUTE_PERMISSIONS: FrozenSet[str] = frozenset({
    DISPUTE_VIEW,
    DISPUTE_INVESTIGATE,
    DISPUTE_ADD_EVIDENCE,
    DISPUTE_SUBMIT_EVIDENCE,
    DISPUTE_RESOLVE,
    DISPUTE_RECONCILE,
})

_LEGACY_MAP: dict[str, FrozenSet[str]] = {
    "leer": frozenset({DISPUTE_VIEW}),
    "escribir": frozenset({DISPUTE_VIEW, DISPUTE_INVESTIGATE, DISPUTE_ADD_EVIDENCE}),
    "configurar": ALL_DISPUTE_PERMISSIONS,
    "eliminar": ALL_DISPUTE_PERMISSIONS,
}


def permisos_dispute_efectivos(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    efectivos: Set[str] = set()
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if not raw:
            continue
        if raw in ALL_DISPUTE_PERMISSIONS:
            efectivos.add(raw)
            continue
        key = raw.lower()
        if key in _LEGACY_MAP:
            efectivos |= set(_LEGACY_MAP[key])
    return efectivos


def tiene_permiso_dispute(permisos_legacy: Iterable[str] | None, permiso: str) -> bool:
    if permiso not in ALL_DISPUTE_PERMISSIONS:
        return False
    return permiso in permisos_dispute_efectivos(permisos_legacy)
