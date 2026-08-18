"""Catálogo central de permisos y capacidades financieras (FASE 10). Deny-by-default."""
from __future__ import annotations

from typing import FrozenSet, Iterable, Set

from core.conflict_authorization import (
    ALL_CONFLICT_PERMISSIONS,
    permisos_conflict_efectivos,
)
from core.dispute_authorization import ALL_DISPUTE_PERMISSIONS, permisos_dispute_efectivos
from core.financial_admin_authorization import ALL_PANEL_VIEW, permisos_panel_efectivos
from core.ledger_authorization import ALL_LEDGER_PERMISSIONS, permisos_ledger_efectivos
from core.reconciliation_authorization import ALL_RECON_PERMISSIONS, permisos_recon_efectivos
from core.refund_authorization import ALL_REFUND_PERMISSIONS, permisos_refund_efectivos

# --- Lectura panel ---
DASHBOARD_VIEW = "financial.dashboard.view"
PAYMENTS_VIEW = "financial.payments.view"
TRANSFERS_VIEW = "financial.transfers.view"
REFUNDS_VIEW = "financial.refunds.view"
DISPUTES_VIEW = "financial.disputes.view"
CONFLICTS_VIEW = "financial.conflicts.view"
RECONCILIATION_VIEW = "financial.reconciliation.view"
LEDGER_VIEW_PERM = "financial.ledger.view"
AUDIT_VIEW = "financial.audit.view"

# --- Acciones (canónicos FASE 10) ---
CONFLICT_INVESTIGATE = "financial.conflict.investigate"
CONFLICT_RESOLVE = "financial.conflict.resolve"
CONFLICT_ESCALATE = "financial.conflict.escalate"
DISPUTE_INVESTIGATE = "financial.dispute.investigate"
DISPUTE_ADD_EVIDENCE = "financial.dispute.add_evidence"
DISPUTE_SUBMIT_EVIDENCE = "financial.dispute.submit_evidence"
RECON_EXECUTE = "financial.reconciliation.execute"
RECON_RESOLVE = "financial.reconciliation.resolve"
LEDGER_RECONCILE = "financial.ledger.reconcile"
REFUND_REQUEST = "financial.refund.request"
REFUND_AUTHORIZE = "financial.refund.authorize"
REFUND_EXECUTE = "financial.refund.execute"
LEDGER_ADJUST = "financial.ledger.adjust"
LEDGER_VOID = "financial.ledger.void"

ALL_FINANCIAL_PERMISSIONS: FrozenSet[str] = frozenset({
    *ALL_PANEL_VIEW,
    *ALL_REFUND_PERMISSIONS,
    *ALL_DISPUTE_PERMISSIONS,
    *ALL_RECON_PERMISSIONS,
    *ALL_LEDGER_PERMISSIONS,
    *ALL_CONFLICT_PERMISSIONS,
    CONFLICT_INVESTIGATE,
    CONFLICT_RESOLVE,
    CONFLICT_ESCALATE,
    REFUNDS_VIEW,
    CONFLICTS_VIEW,
})

# Alias históricos → canónico FASE 10
PERMISSION_ALIASES: dict[str, str] = {
    "conflict.view": CONFLICTS_VIEW,
    "conflict.investigate": CONFLICT_INVESTIGATE,
    "conflict.add_evidence": "conflict.add_evidence",
    "conflict.comment": "conflict.comment",
    "conflict.request_evidence": "conflict.request_evidence",
    "conflict.resolve": CONFLICT_RESOLVE,
    "conflict.escalate": CONFLICT_ESCALATE,
    "conflict.close": "conflict.close",
    "financial.refund.view": REFUNDS_VIEW,
    "financial.dispute.view": DISPUTES_VIEW,
    "financial.reconciliation.view": RECONCILIATION_VIEW,
    "financial.ledger.view": LEDGER_VIEW_PERM,
}

# Capacidades (separación de funciones)
CAPABILITY_VIEWER = "VIEWER"
CAPABILITY_INVESTIGATOR = "INVESTIGATOR"
CAPABILITY_AUTHORIZER = "AUTHORIZER"
CAPABILITY_EXECUTOR = "EXECUTOR"
CAPABILITY_AUDITOR = "AUDITOR"
CAPABILITY_FINANCE_ADMIN = "FINANCE_ADMIN"

_CAPABILITY_PERMISSIONS: dict[str, FrozenSet[str]] = {
    CAPABILITY_VIEWER: frozenset({
        DASHBOARD_VIEW, PAYMENTS_VIEW, TRANSFERS_VIEW, REFUNDS_VIEW,
        DISPUTES_VIEW, CONFLICTS_VIEW, RECONCILIATION_VIEW, LEDGER_VIEW_PERM, AUDIT_VIEW,
        "financial.refund.view", "financial.dispute.view", "conflict.view",
        "financial.reconciliation.view", "financial.ledger.view",
    }),
    CAPABILITY_INVESTIGATOR: frozenset({
        CONFLICT_INVESTIGATE, DISPUTE_INVESTIGATE, DISPUTE_ADD_EVIDENCE,
        "conflict.add_evidence", "conflict.comment", "conflict.request_evidence",
    }),
    CAPABILITY_AUTHORIZER: frozenset({REFUND_AUTHORIZE, RECON_RESOLVE}),
    CAPABILITY_EXECUTOR: frozenset({
        REFUND_EXECUTE, RECON_EXECUTE, DISPUTE_SUBMIT_EVIDENCE,
        CONFLICT_RESOLVE, CONFLICT_ESCALATE, LEDGER_ADJUST, LEDGER_VOID,
        "conflict.resolve", "conflict.escalate", "financial.refund.execute",
        "financial.reconciliation.execute", "financial.dispute.submit_evidence",
        "financial.ledger.adjust", "financial.ledger.void",
    }),
    CAPABILITY_AUDITOR: frozenset({AUDIT_VIEW, LEDGER_RECONCILE, "financial.ledger.reconcile"}),
    CAPABILITY_FINANCE_ADMIN: ALL_FINANCIAL_PERMISSIONS,
}


def normalizar_permiso(permiso: str) -> str:
    p = (permiso or "").strip()
    return PERMISSION_ALIASES.get(p, p)


def permisos_financieros_efectivos(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    efectivos: Set[str] = set()
    efectivos |= permisos_panel_efectivos(permisos_legacy)
    efectivos |= permisos_refund_efectivos(permisos_legacy)
    efectivos |= permisos_dispute_efectivos(permisos_legacy)
    efectivos |= permisos_recon_efectivos(permisos_legacy)
    efectivos |= permisos_ledger_efectivos(permisos_legacy)
    efectivos |= permisos_conflict_efectivos(permisos_legacy)
    for p in permisos_legacy or ():
        raw = (p or "").strip()
        if raw in ALL_FINANCIAL_PERMISSIONS:
            efectivos.add(raw)
        canon = PERMISSION_ALIASES.get(raw)
        if canon:
            efectivos.add(canon)
    return {normalizar_permiso(p) for p in efectivos} | efectivos


def tiene_permiso_financiero(permisos_legacy: Iterable[str] | None, permiso_requerido: str) -> bool:
    req = normalizar_permiso(permiso_requerido)
    efectivos = permisos_financieros_efectivos(permisos_legacy)
    if req in efectivos:
        return True
    # Compat: permiso legacy sin prefijo financial
    for e in efectivos:
        if normalizar_permiso(e) == req:
            return True
    return False


def capacidades_efectivas(permisos_legacy: Iterable[str] | None = None) -> Set[str]:
    perms = permisos_financieros_efectivos(permisos_legacy)
    caps: Set[str] = set()
    for cap, needed in _CAPABILITY_PERMISSIONS.items():
        if cap == CAPABILITY_FINANCE_ADMIN:
            if "configurar" in {str(p).lower() for p in (permisos_legacy or [])}:
                caps.add(cap)
            continue
        if needed & perms:
            caps.add(cap)
    if "configurar" in {str(p).lower() for p in (permisos_legacy or [])}:
        caps.add(CAPABILITY_FINANCE_ADMIN)
    return caps


def puede_ejecutar_sin_aprobacion_previa(permisos_legacy: Iterable[str] | None) -> bool:
    """Solo FINANCE_ADMIN (configurar) puede saltar doble aprobación en entornos controlados."""
    return CAPABILITY_FINANCE_ADMIN in capacidades_efectivas(permisos_legacy)
