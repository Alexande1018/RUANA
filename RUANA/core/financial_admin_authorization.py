"""Autorización del panel administrativo financiero (FASE 09). Deny-by-default."""
from __future__ import annotations

from typing import FrozenSet, Iterable, Set

# Lectura
DASHBOARD_VIEW = "financial.dashboard.view"
PAYMENTS_VIEW = "financial.payments.view"
TRANSFERS_VIEW = "financial.transfers.view"
REFUNDS_VIEW = "financial.refunds.view"
DISPUTES_VIEW = "financial.disputes.view"
CONFLICTS_VIEW = "financial.conflicts.view"
RECONCILIATION_VIEW = "financial.reconciliation.view"
LEDGER_VIEW = "financial.ledger.view"
AUDIT_VIEW = "financial.audit.view"

ALL_PANEL_VIEW: FrozenSet[str] = frozenset({
    DASHBOARD_VIEW,
    PAYMENTS_VIEW,
    TRANSFERS_VIEW,
    REFUNDS_VIEW,
    DISPUTES_VIEW,
    CONFLICTS_VIEW,
    RECONCILIATION_VIEW,
    LEDGER_VIEW,
    AUDIT_VIEW,
})

_LEGACY_MAP: dict[str, FrozenSet[str]] = {
    "leer": frozenset({
        DASHBOARD_VIEW,
        PAYMENTS_VIEW,
        TRANSFERS_VIEW,
        REFUNDS_VIEW,
        DISPUTES_VIEW,
        CONFLICTS_VIEW,
        RECONCILIATION_VIEW,
        LEDGER_VIEW,
        AUDIT_VIEW,
    }),
    "escribir": ALL_PANEL_VIEW,
    "configurar": ALL_PANEL_VIEW,
    "eliminar": ALL_PANEL_VIEW,
}


def permisos_panel_efectivos(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    efectivos: Set[str] = set()
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if not raw:
            continue
        if raw in ALL_PANEL_VIEW:
            efectivos.add(raw)
            continue
        key = raw.lower()
        if key in _LEGACY_MAP:
            efectivos |= set(_LEGACY_MAP[key])
    return efectivos


def tiene_permiso_panel(permisos_legacy: Iterable[str] | None, permiso: str) -> bool:
    if permiso not in ALL_PANEL_VIEW:
        return False
    return permiso in permisos_panel_efectivos(permisos_legacy)
