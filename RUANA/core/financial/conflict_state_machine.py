"""Máquina de estados de conflictos financieros (FASE 04)."""
from __future__ import annotations

from typing import Dict, FrozenSet, Set

from core.financial.conflict_estados import EstadoConflicto, ResolucionConflicto


class TransicionConflictoInvalidaError(ValueError):
    pass


_TRANSICIONES: Dict[EstadoConflicto, FrozenSet[EstadoConflicto]] = {
    EstadoConflicto.ABIERTO: frozenset({
        EstadoConflicto.EN_INVESTIGACION,
        EstadoConflicto.PENDIENTE_DE_EVIDENCIA,
    }),
    EstadoConflicto.EN_INVESTIGACION: frozenset({
        EstadoConflicto.PENDIENTE_DE_EVIDENCIA,
        EstadoConflicto.RESUELTO,
        EstadoConflicto.ESCALADO,
    }),
    EstadoConflicto.PENDIENTE_DE_EVIDENCIA: frozenset({
        EstadoConflicto.EN_INVESTIGACION,
    }),
    EstadoConflicto.ESCALADO: frozenset({
        EstadoConflicto.EN_INVESTIGACION,
    }),
    EstadoConflicto.RESUELTO: frozenset({
        EstadoConflicto.CERRADO,
    }),
    EstadoConflicto.CERRADO: frozenset(),
}


class ConflictStateMachine:
    @staticmethod
    def puede_transicionar(actual: EstadoConflicto, nuevo: EstadoConflicto) -> bool:
        if actual == nuevo:
            return True
        if actual == EstadoConflicto.CERRADO:
            return False
        if nuevo == EstadoConflicto.ABIERTO and actual != EstadoConflicto.ABIERTO:
            return False
        if actual == EstadoConflicto.RESUELTO and nuevo == EstadoConflicto.EN_INVESTIGACION:
            return False
        return nuevo in _TRANSICIONES.get(actual, frozenset())

    @staticmethod
    def validar_transicion(actual: EstadoConflicto, nuevo: EstadoConflicto) -> None:
        if not ConflictStateMachine.puede_transicionar(actual, nuevo):
            raise TransicionConflictoInvalidaError(
                f"Transición no permitida: {actual.value} → {nuevo.value}"
            )

    @staticmethod
    def transiciones_desde(estado: EstadoConflicto) -> Set[EstadoConflicto]:
        return set(_TRANSICIONES.get(estado, frozenset()))

    @staticmethod
    def estado_tras_resolucion(resolucion: ResolucionConflicto) -> EstadoConflicto:
        if resolucion == ResolucionConflicto.ESCALAR_ADMIN:
            return EstadoConflicto.ESCALADO
        if resolucion == ResolucionConflicto.MANTENER_RETENIDO:
            return EstadoConflicto.EN_INVESTIGACION
        return EstadoConflicto.RESUELTO
