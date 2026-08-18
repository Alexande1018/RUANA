"""Estados, tipos y resoluciones formales de conflictos financieros (FASE 04)."""
from __future__ import annotations

from enum import Enum


class EstadoConflicto(str, Enum):
    ABIERTO = "ABIERTO"
    EN_INVESTIGACION = "EN_INVESTIGACION"
    PENDIENTE_DE_EVIDENCIA = "PENDIENTE_DE_EVIDENCIA"
    RESUELTO = "RESUELTO"
    ESCALADO = "ESCALADO"
    CERRADO = "CERRADO"

    @classmethod
    def bloquea_financiero(cls, estado: "EstadoConflicto") -> bool:
        return estado in _ESTADOS_BLOQUEO_FINANCIERO


class TipoConflicto(str, Enum):
    SERVICIO_NO_REALIZADO = "SERVICIO_NO_REALIZADO"
    TRABAJO_INCOMPLETO = "TRABAJO_INCOMPLETO"
    IMPORTE_DISPUTADO = "IMPORTE_DISPUTADO"
    CALIDAD_DISPUTADA = "CALIDAD_DISPUTADA"
    PLAZO_DISPUTADO = "PLAZO_DISPUTADO"
    INCUMPLIMIENTO = "INCUMPLIMIENTO"
    OTRO = "OTRO"

    @classmethod
    def from_legacy(cls, legacy: str) -> "TipoConflicto":
        m = {
            "importe_discrepante": cls.IMPORTE_DISPUTADO,
            "sin_confirmacion_trabajo": cls.PLAZO_DISPUTADO,
        }
        return m.get((legacy or "").strip().lower(), cls.OTRO)


class ResolucionConflicto(str, Enum):
    LIBERAR_PROFESIONAL = "LIBERAR_PROFESIONAL"
    REEMBOLSAR_TOTAL = "REEMBOLSAR_TOTAL"
    REEMBOLSAR_PARCIAL = "REEMBOLSAR_PARCIAL"
    DIVIDIR_IMPORTE = "DIVIDIR_IMPORTE"
    MANTENER_RETENIDO = "MANTENER_RETENIDO"
    ESCALAR_ADMIN = "ESCALAR_ADMIN"


_ESTADOS_BLOQUEO_FINANCIERO = frozenset({
    EstadoConflicto.ABIERTO,
    EstadoConflicto.EN_INVESTIGACION,
    EstadoConflicto.PENDIENTE_DE_EVIDENCIA,
    EstadoConflicto.ESCALADO,
})

# Legacy payment_conflicts.estado → estado_conflicto
_LEGACY_ESTADO_MAP = {
    "PENDIENTE_PRUEBA": EstadoConflicto.ABIERTO,
    "EN_REVISION": EstadoConflicto.EN_INVESTIGACION,
    "RESUELTO": EstadoConflicto.CERRADO,
    "RECHAZADO": EstadoConflicto.CERRADO,
}


def normalizar_estado_conflicto(
    estado_conflicto: str | None, legacy_estado: str | None = None,
) -> EstadoConflicto | None:
    raw = (estado_conflicto or "").strip().upper()
    if raw:
        try:
            return EstadoConflicto(raw)
        except ValueError:
            pass
    leg = (legacy_estado or "").strip().upper()
    return _LEGACY_ESTADO_MAP.get(leg)
