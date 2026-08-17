"""Modelo financiero y máquina de estados transaccional (FASE 01)."""

from core.financial.estados import EstadoFinanciero, EstadoTransferencia
from core.financial.modelo import ModeloFinanciero, InvarianteFinancieraError
from core.financial.state_machine import (
    FinancialStateMachine,
    TransicionInvalidaError,
    TransicionBloqueadaError,
)

__all__ = [
    "EstadoFinanciero",
    "EstadoTransferencia",
    "ModeloFinanciero",
    "InvarianteFinancieraError",
    "FinancialStateMachine",
    "TransicionInvalidaError",
    "TransicionBloqueadaError",
]
