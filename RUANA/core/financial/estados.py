"""Estados financieros canónicos de una operación RUANA (FASE 01)."""
from __future__ import annotations

from enum import Enum


class EstadoFinanciero(str, Enum):
    """Estado operativo financiero de un encargo/contacto."""

    PAGO_NO_INICIADO = "PAGO_NO_INICIADO"
    PAGO_PENDIENTE = "PAGO_PENDIENTE"
    PAGO_CONFIRMADO = "PAGO_CONFIRMADO"
    TRABAJO_EN_CURSO = "TRABAJO_EN_CURSO"
    TRABAJO_ENTREGADO = "TRABAJO_ENTREGADO"
    ESPERANDO_CONFIRMACION = "ESPERANDO_CONFIRMACION"
    LIBERACION_AUTORIZADA = "LIBERACION_AUTORIZADA"
    TRANSFERENCIA_PENDIENTE = "TRANSFERENCIA_PENDIENTE"
    TRANSFERENCIA_ENVIADA = "TRANSFERENCIA_ENVIADA"
    TRANSFERIDO = "TRANSFERIDO"

    PAGO_FALLIDO = "PAGO_FALLIDO"
    PAGO_CANCELADO = "PAGO_CANCELADO"
    CONFLICTO_ABIERTO = "CONFLICTO_ABIERTO"
    REEMBOLSO_PENDIENTE = "REEMBOLSO_PENDIENTE"
    REEMBOLSADO = "REEMBOLSADO"
    DISPUTA_STRIPE = "DISPUTA_STRIPE"
    TRANSFERENCIA_FALLIDA = "TRANSFERENCIA_FALLIDA"
    TRANSFERENCIA_REVERTIDA = "TRANSFERENCIA_REVERTIDA"
    CANCELADO = "CANCELADO"

    MIGRACION_PENDIENTE = "MIGRACION_PENDIENTE"

    @classmethod
    def from_value(cls, value: str) -> "EstadoFinanciero":
        try:
            return cls(str(value).strip().upper())
        except ValueError as exc:
            raise ValueError(f"Estado financiero desconocido: {value}") from exc

    @property
    def es_terminal(self) -> bool:
        return self in _ESTADOS_TERMINALES

    @property
    def es_excepcion(self) -> bool:
        return self in _ESTADOS_EXCEPCION

    @property
    def bloquea_transferencia(self) -> bool:
        return self in _ESTADOS_BLOQUEO_TRANSFERENCIA


class EstadoTransferencia(str, Enum):
    """Sub-estado del dinero retenido/transferido (independiente del servicio)."""

    NO_APLICA = "NO_APLICA"
    RETENIDO = "RETENIDO"
    PENDIENTE = "PENDIENTE"
    ENVIADA = "ENVIADA"
    COMPLETADA = "COMPLETADA"
    FALLIDA = "FALLIDA"
    REVERTIDA = "REVERTIDA"


_ESTADOS_TERMINALES = frozenset({
    EstadoFinanciero.TRANSFERIDO,
    EstadoFinanciero.PAGO_FALLIDO,
    EstadoFinanciero.PAGO_CANCELADO,
    EstadoFinanciero.REEMBOLSADO,
    EstadoFinanciero.CANCELADO,
    EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
})

_ESTADOS_EXCEPCION = frozenset({
    EstadoFinanciero.PAGO_FALLIDO,
    EstadoFinanciero.PAGO_CANCELADO,
    EstadoFinanciero.CONFLICTO_ABIERTO,
    EstadoFinanciero.REEMBOLSO_PENDIENTE,
    EstadoFinanciero.REEMBOLSADO,
    EstadoFinanciero.DISPUTA_STRIPE,
    EstadoFinanciero.TRANSFERENCIA_FALLIDA,
    EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
    EstadoFinanciero.CANCELADO,
})

_ESTADOS_BLOQUEO_TRANSFERENCIA = frozenset({
    EstadoFinanciero.CONFLICTO_ABIERTO,
    EstadoFinanciero.DISPUTA_STRIPE,
    EstadoFinanciero.REEMBOLSO_PENDIENTE,
    EstadoFinanciero.REEMBOLSADO,
})
