"""Estados internos de disputas Stripe (FASE 06)."""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Set


class EstadoDisputa(str, Enum):
    ABIERTO = "ABIERTO"
    EN_INVESTIGACION = "EN_INVESTIGACION"
    EVIDENCIA_PENDIENTE = "EVIDENCIA_PENDIENTE"
    EVIDENCIA_EN_PREPARACION = "EVIDENCIA_EN_PREPARACION"
    EVIDENCIA_ENVIADA = "EVIDENCIA_ENVIADA"
    GANADA = "GANADA"
    PERDIDA = "PERDIDA"
    CERRADA = "CERRADA"
    ESCALADA = "ESCALADA"

    @classmethod
    def es_terminal(cls, estado: "EstadoDisputa") -> bool:
        return estado in (cls.GANADA, cls.PERDIDA, cls.CERRADA)

    @classmethod
    def bloquea_operaciones(cls, estado: "EstadoDisputa") -> bool:
        return not cls.es_terminal(estado)


_TRANSICIONES: dict[EstadoDisputa, FrozenSet[EstadoDisputa]] = {
    EstadoDisputa.ABIERTO: frozenset({
        EstadoDisputa.EN_INVESTIGACION,
        EstadoDisputa.EVIDENCIA_PENDIENTE,
    }),
    EstadoDisputa.EN_INVESTIGACION: frozenset({
        EstadoDisputa.EVIDENCIA_EN_PREPARACION,
        EstadoDisputa.ESCALADA,
    }),
    EstadoDisputa.EVIDENCIA_PENDIENTE: frozenset({EstadoDisputa.EVIDENCIA_EN_PREPARACION}),
    EstadoDisputa.EVIDENCIA_EN_PREPARACION: frozenset({EstadoDisputa.EVIDENCIA_ENVIADA}),
    EstadoDisputa.EVIDENCIA_ENVIADA: frozenset({EstadoDisputa.GANADA, EstadoDisputa.PERDIDA}),
    EstadoDisputa.GANADA: frozenset({EstadoDisputa.CERRADA}),
    EstadoDisputa.PERDIDA: frozenset({EstadoDisputa.CERRADA}),
    EstadoDisputa.ESCALADA: frozenset({EstadoDisputa.EN_INVESTIGACION}),
    EstadoDisputa.CERRADA: frozenset(),
}


class TipoEvidenciaDisputa(str, Enum):
    SERVICIO_ENTREGADO = "servicio_entregado"
    COMUNICACION = "comunicacion"
    CONTRATO = "contrato"
    RECIBO = "recibo"
    PRUEBA_ENTREGA = "prueba_entrega"
    IDENTIDAD = "identidad"
    OTRO = "otro"


# Mapeo Stripe status → estado interno sugerido (no forzado sin transición válida)
_STRIPE_STATUS_MAP: dict[str, EstadoDisputa] = {
    "needs_response": EstadoDisputa.EVIDENCIA_PENDIENTE,
    "warning_needs_response": EstadoDisputa.EVIDENCIA_PENDIENTE,
    "under_review": EstadoDisputa.EVIDENCIA_ENVIADA,
    "won": EstadoDisputa.GANADA,
    "lost": EstadoDisputa.PERDIDA,
    "charge_refunded": EstadoDisputa.CERRADA,
    "warning_closed": EstadoDisputa.CERRADA,
}


def puede_transicionar(origen: EstadoDisputa, destino: EstadoDisputa) -> bool:
    if origen == destino:
        return True
    return destino in _TRANSICIONES.get(origen, frozenset())


def estados_abiertos() -> Set[str]:
    return {e.value for e in EstadoDisputa if EstadoDisputa.bloquea_operaciones(e)}


def mapear_estado_stripe(status: str) -> EstadoDisputa | None:
    return _STRIPE_STATUS_MAP.get((status or "").strip().lower())
