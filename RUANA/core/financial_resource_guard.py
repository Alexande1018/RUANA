"""Validación anti-IDOR de recursos financieros (FASE 10)."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.repositories.financial_conflict_repo import FinancialConflictRepo
from core.repositories.financial_dispute_repo import FinancialDisputeRepo
from core.repositories.financial_refund_repo import FinancialRefundRepo
from core.repositories.pago_repo import PagoRepo

_conflict_repo = FinancialConflictRepo()
_dispute_repo = FinancialDisputeRepo()
_refund_repo = FinancialRefundRepo()
_pago_repo = PagoRepo()


def validar_contacto_existe(cursor, contacto_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
    if not row:
        return False, None
    return True, dict(row) if hasattr(row, "keys") else {}


def validar_conflicto(cursor, conflict_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    row = _conflict_repo.select_por_id(cursor, conflict_id)
    return (row is not None, row)


def validar_disputa(cursor, dispute_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    row = _dispute_repo.select_por_id(cursor, dispute_id)
    return (row is not None, row)


def validar_refund(cursor, refund_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    row = _refund_repo.select_por_id(cursor, refund_id)
    return (row is not None, row)


def validar_contacto_conflicto_coherente(conflicto: Dict[str, Any], contacto_id: int) -> bool:
    tid = conflicto.get("trabajo_id") or conflicto.get("contacto_id")
    return int(tid or 0) == int(contacto_id)


def validar_contacto_disputa_coherente(disputa: Dict[str, Any], contacto_id: int) -> bool:
    return int(disputa.get("contacto_id") or 0) == int(contacto_id)
