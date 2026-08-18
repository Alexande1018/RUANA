"""Autorización para automatización y monitorización financiera (FASE 11). Deny-by-default."""
from __future__ import annotations

from typing import FrozenSet, Iterable, Set

AUTOMATION_EXECUTE = "financial.automation.execute"
MONITORING_VIEW = "financial.monitoring.view"

ALL_AUTOMATION_PERMISSIONS: FrozenSet[str] = frozenset({
    AUTOMATION_EXECUTE,
    MONITORING_VIEW,
})

_LEGACY_MAP: dict[str, FrozenSet[str]] = {
    "leer": frozenset({MONITORING_VIEW}),
    "escribir": frozenset({MONITORING_VIEW}),
    "configurar": ALL_AUTOMATION_PERMISSIONS,
    "eliminar": ALL_AUTOMATION_PERMISSIONS,
}


def permisos_automation_efectivos(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    efectivos: Set[str] = set()
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if not raw:
            continue
        if raw in ALL_AUTOMATION_PERMISSIONS:
            efectivos.add(raw)
            continue
        key = raw.lower()
        if key in _LEGACY_MAP:
            efectivos |= set(_LEGACY_MAP[key])
    return efectivos


def tiene_permiso_automation(permisos_legacy: Iterable[str] | None, permiso: str) -> bool:
    if permiso not in ALL_AUTOMATION_PERMISSIONS:
        return False
    return permiso in permisos_automation_efectivos(permisos_legacy)
