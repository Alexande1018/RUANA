"""Plan de cuentas del ledger financiero (FASE 08)."""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet


class CuentaLedger(str, Enum):
  # Activos
    STRIPE_BALANCE = "STRIPE_BALANCE"
    STRIPE_RECEIVABLE = "STRIPE_RECEIVABLE"
    FUNDS_HELD = "FUNDS_HELD"
    # Pasivos
    PROFESSIONAL_PAYABLE = "PROFESSIONAL_PAYABLE"
    CUSTOMER_REFUND_PAYABLE = "CUSTOMER_REFUND_PAYABLE"
    DISPUTE_PAYABLE = "DISPUTE_PAYABLE"
    # Ingresos
    RUANA_COMMISSION_REVENUE = "RUANA_COMMISSION_REVENUE"
    # Gastos
    STRIPE_PROCESSING_FEE = "STRIPE_PROCESSING_FEE"
    DISPUTE_LOSS = "DISPUTE_LOSS"
    REFUND_LOSS = "REFUND_LOSS"
    # Técnicas / clearing
    CLEARING_PAYMENTS = "CLEARING_PAYMENTS"
    CLEARING_TRANSFERS = "CLEARING_TRANSFERS"
    CLEARING_REFUNDS = "CLEARING_REFUNDS"


ALL_CUENTAS: FrozenSet[str] = frozenset(c.value for c in CuentaLedger)


def cuenta_valida(code: str) -> bool:
    return (code or "") in ALL_CUENTAS
