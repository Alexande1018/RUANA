"""Máquina de estados financiera explícita (FASE 01)."""
from __future__ import annotations

from typing import Dict, FrozenSet, Optional, Set

from core.financial.estados import EstadoFinanciero, EstadoTransferencia


class TransicionInvalidaError(ValueError):
    """Transición no permitida por la máquina de estados."""


class TransicionBloqueadaError(TransicionInvalidaError):
    """Transición bloqueada por conflicto, disputa u otra regla de negocio."""


# Transiciones explícitas permitidas (FASE 01)
_TRANSICIONES: Dict[EstadoFinanciero, FrozenSet[EstadoFinanciero]] = {
    EstadoFinanciero.PAGO_NO_INICIADO: frozenset({EstadoFinanciero.PAGO_PENDIENTE}),
    EstadoFinanciero.PAGO_PENDIENTE: frozenset({
        EstadoFinanciero.PAGO_CONFIRMADO,
        EstadoFinanciero.PAGO_FALLIDO,
        EstadoFinanciero.PAGO_CANCELADO,
    }),
    EstadoFinanciero.PAGO_CONFIRMADO: frozenset({
        EstadoFinanciero.TRABAJO_EN_CURSO,
        EstadoFinanciero.REEMBOLSO_PENDIENTE,
        EstadoFinanciero.DISPUTA_STRIPE,
    }),
    EstadoFinanciero.TRABAJO_EN_CURSO: frozenset({
        EstadoFinanciero.TRABAJO_ENTREGADO,
        EstadoFinanciero.ESPERANDO_CONFIRMACION,
        EstadoFinanciero.CONFLICTO_ABIERTO,
    }),
    EstadoFinanciero.TRABAJO_ENTREGADO: frozenset({
        EstadoFinanciero.ESPERANDO_CONFIRMACION,
        EstadoFinanciero.CONFLICTO_ABIERTO,
    }),
    EstadoFinanciero.ESPERANDO_CONFIRMACION: frozenset({
        EstadoFinanciero.LIBERACION_AUTORIZADA,
        EstadoFinanciero.CONFLICTO_ABIERTO,
    }),
    EstadoFinanciero.LIBERACION_AUTORIZADA: frozenset({
        EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
    }),
    EstadoFinanciero.TRANSFERENCIA_PENDIENTE: frozenset({
        EstadoFinanciero.TRANSFERENCIA_ENVIADA,
        EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
        EstadoFinanciero.DISPUTA_STRIPE,
    }),
    EstadoFinanciero.TRANSFERENCIA_ENVIADA: frozenset({
        EstadoFinanciero.TRANSFERIDO,
        EstadoFinanciero.TRANSFERENCIA_FALLIDA,
        EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
        EstadoFinanciero.DISPUTA_STRIPE,
    }),
    EstadoFinanciero.TRANSFERIDO: frozenset({
        EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
    }),
    EstadoFinanciero.CONFLICTO_ABIERTO: frozenset({
        EstadoFinanciero.ESPERANDO_CONFIRMACION,
        EstadoFinanciero.TRABAJO_ENTREGADO,
        EstadoFinanciero.REEMBOLSO_PENDIENTE,
        EstadoFinanciero.CANCELADO,
    }),
    EstadoFinanciero.REEMBOLSO_PENDIENTE: frozenset({EstadoFinanciero.REEMBOLSADO}),
    EstadoFinanciero.TRANSFERENCIA_FALLIDA: frozenset({
        EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
        EstadoFinanciero.CANCELADO,
    }),
    EstadoFinanciero.MIGRACION_PENDIENTE: frozenset({
        EstadoFinanciero.PAGO_NO_INICIADO,
        EstadoFinanciero.PAGO_PENDIENTE,
        EstadoFinanciero.PAGO_CONFIRMADO,
        EstadoFinanciero.ESPERANDO_CONFIRMACION,
        EstadoFinanciero.TRANSFERIDO,
        EstadoFinanciero.CONFLICTO_ABIERTO,
    }),
}

_ESTADOS_BLOQUEADOS_PARA_TRANSFERENCIA = frozenset({
    EstadoFinanciero.LIBERACION_AUTORIZADA,
    EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
    EstadoFinanciero.TRANSFERENCIA_ENVIADA,
    EstadoFinanciero.TRANSFERIDO,
})

_ESTADOS_CANCELADOS = frozenset({
    EstadoFinanciero.PAGO_CANCELADO,
    EstadoFinanciero.CANCELADO,
    EstadoFinanciero.REEMBOLSADO,
})

_MAPA_ESTADO_TRANSFERENCIA: Dict[EstadoFinanciero, EstadoTransferencia] = {
    EstadoFinanciero.PAGO_NO_INICIADO: EstadoTransferencia.NO_APLICA,
    EstadoFinanciero.PAGO_PENDIENTE: EstadoTransferencia.NO_APLICA,
    EstadoFinanciero.PAGO_CONFIRMADO: EstadoTransferencia.RETENIDO,
    EstadoFinanciero.TRABAJO_EN_CURSO: EstadoTransferencia.RETENIDO,
    EstadoFinanciero.TRABAJO_ENTREGADO: EstadoTransferencia.RETENIDO,
    EstadoFinanciero.ESPERANDO_CONFIRMACION: EstadoTransferencia.RETENIDO,
    EstadoFinanciero.CONFLICTO_ABIERTO: EstadoTransferencia.RETENIDO,
    EstadoFinanciero.LIBERACION_AUTORIZADA: EstadoTransferencia.PENDIENTE,
    EstadoFinanciero.TRANSFERENCIA_PENDIENTE: EstadoTransferencia.PENDIENTE,
    EstadoFinanciero.TRANSFERENCIA_ENVIADA: EstadoTransferencia.ENVIADA,
    EstadoFinanciero.TRANSFERIDO: EstadoTransferencia.COMPLETADA,
    EstadoFinanciero.TRANSFERENCIA_FALLIDA: EstadoTransferencia.FALLIDA,
    EstadoFinanciero.TRANSFERENCIA_REVERTIDA: EstadoTransferencia.REVERTIDA,
    EstadoFinanciero.DISPUTA_STRIPE: EstadoTransferencia.RETENIDO,
}


class FinancialStateMachine:
    """Validación pura de transiciones financieras."""

    @staticmethod
    def transiciones_desde(estado: EstadoFinanciero) -> Set[EstadoFinanciero]:
        return set(_TRANSICIONES.get(estado, frozenset()))

    @staticmethod
    def puede_transicionar(
        estado_actual: EstadoFinanciero,
        estado_nuevo: EstadoFinanciero,
        *,
        conflicto_abierto: bool = False,
        ya_transferido: bool = False,
        desde_estado_cancelado: bool = False,
    ) -> bool:
        try:
            FinancialStateMachine.validar_transicion(
                estado_actual,
                estado_nuevo,
                conflicto_abierto=conflicto_abierto,
                ya_transferido=ya_transferido,
                desde_estado_cancelado=desde_estado_cancelado,
            )
            return True
        except TransicionInvalidaError:
            return False

    @staticmethod
    def validar_transicion(
        estado_actual: EstadoFinanciero,
        estado_nuevo: EstadoFinanciero,
        *,
        conflicto_abierto: bool = False,
        ya_transferido: bool = False,
        desde_estado_cancelado: bool = False,
    ) -> None:
        if estado_actual == estado_nuevo:
            return

        if desde_estado_cancelado or estado_actual in _ESTADOS_CANCELADOS:
            raise TransicionInvalidaError(
                f"INVARIANTE 9: operación cancelada no puede volver al flujo normal "
                f"({estado_actual.value} → {estado_nuevo.value})"
            )

        if ya_transferido and estado_nuevo == EstadoFinanciero.TRANSFERENCIA_PENDIENTE:
            raise TransicionInvalidaError(
                "INVARIANTE 8: operación TRANSFERIDO no puede volver a TRANSFERENCIA_PENDIENTE"
            )

        if conflicto_abierto and estado_nuevo in _ESTADOS_BLOQUEADOS_PARA_TRANSFERENCIA:
            raise TransicionBloqueadaError(
                f"INVARIANTE 7: conflicto abierto bloquea transferencia "
                f"({estado_actual.value} → {estado_nuevo.value})"
            )

        if estado_actual.bloquea_transferencia and estado_nuevo in _ESTADOS_BLOQUEADOS_PARA_TRANSFERENCIA:
            raise TransicionBloqueadaError(
                f"Estado {estado_actual.value} bloquea transferencia hacia {estado_nuevo.value}"
            )

        permitidas = _TRANSICIONES.get(estado_actual, frozenset())
        if estado_nuevo not in permitidas:
            raise TransicionInvalidaError(
                f"Transición no permitida: {estado_actual.value} → {estado_nuevo.value}"
            )

    @staticmethod
    def estado_transferencia_para(estado: EstadoFinanciero) -> EstadoTransferencia:
        return _MAPA_ESTADO_TRANSFERENCIA.get(estado, EstadoTransferencia.NO_APLICA)

    @staticmethod
    def ruta_liberacion_completa() -> tuple:
        """Secuencia atómica usada por el flujo Stripe actual (compatibilidad)."""
        return (
            EstadoFinanciero.LIBERACION_AUTORIZADA,
            EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
            EstadoFinanciero.TRANSFERENCIA_ENVIADA,
            EstadoFinanciero.TRANSFERIDO,
        )
