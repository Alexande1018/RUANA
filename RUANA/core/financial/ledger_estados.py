"""Estados de transacciones del ledger (FASE 08)."""
from __future__ import annotations

from enum import Enum


class EstadoLedgerTransaction(str, Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    VOIDED = "VOIDED"

    @classmethod
    def es_inmutable(cls, estado: "EstadoLedgerTransaction") -> bool:
        return estado in (cls.POSTED, cls.VOIDED)
