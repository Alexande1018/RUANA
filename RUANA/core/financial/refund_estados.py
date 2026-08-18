"""Estados de reembolsos financieros (FASE 05)."""
from __future__ import annotations

from enum import Enum


class EstadoRefund(str, Enum):
    REQUESTED = "REQUESTED"
    STRIPE_PROCESSING = "STRIPE_PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"

    @classmethod
    def es_terminal(cls, estado: "EstadoRefund") -> bool:
        return estado in (cls.SUCCEEDED, cls.FAILED, cls.CANCELED)

    @classmethod
    def bloquea_nuevo_refund(cls, estado: "EstadoRefund") -> bool:
        return estado in (cls.REQUESTED, cls.STRIPE_PROCESSING, cls.PENDING_RECONCILIATION)


class CausaReembolso(str, Enum):
    """Causas RUANA aprobadas (reglas de negocio FASE 05)."""
    SERVICIO_NO_INICIADO = "SERVICIO_NO_INICIADO"
    INCUMPLIMIENTO_PROFESIONAL = "INCUMPLIMIENTO_PROFESIONAL"
    SERVICIO_PARCIAL = "SERVICIO_PARCIAL"
    CANCELACION_INJUSTIFICADA_CONTRATANTE = "CANCELACION_INJUSTIFICADA_CONTRATANTE"
    ERROR_RUANA = "ERROR_RUANA"
    INDETERMINADO = "INDETERMINADO"

    @classmethod
    def permite_ejecucion(cls, causa: "CausaReembolso") -> bool:
        return causa != cls.INDETERMINADO
