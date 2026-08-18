"""Estados de reconciliación avanzada (FASE 07)."""
from __future__ import annotations

from enum import Enum


class EstadoReconciliacionAvanzada(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    FETCHING = "FETCHING"
    MATCHED = "MATCHED"
    MATCHED_WITH_WARNINGS = "MATCHED_WITH_WARNINGS"
    PENDING = "PENDING"
    MISMATCH = "MISMATCH"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    RESOLVED = "RESOLVED"

    @classmethod
    def es_terminal(cls, estado: "EstadoReconciliacionAvanzada") -> bool:
        return estado in (
            cls.MATCHED,
            cls.MATCHED_WITH_WARNINGS,
            cls.MISMATCH,
            cls.RESOLVED,
            cls.ERROR,
        )


class StripeFetchStatus(str, Enum):
    OK = "ok"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    ERROR = "error"
