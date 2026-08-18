"""Cálculo centralizado de comisión RUANA en reembolsos (FASE 05).

Comisión fija: 12 % del importe bruto cobrado.
Todo en céntimos enteros; redondeo: división entera (floor) sobre producto.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.financial.refund_estados import CausaReembolso

COMISION_PORCENTAJE = 12


@dataclass(frozen=True)
class ImpactoComisionRefund:
    comision_total_cents: int
    comision_conservada_cents: int
    comision_devuelta_cents: int
    parte_ejecutada_cents: int
    parte_no_ejecutada_cents: int
    causa_aplicada: str
    redondeo_aplicado: str


def _comision_sobre(importe_cents: int) -> int:
    if importe_cents <= 0:
        return 0
    return (importe_cents * COMISION_PORCENTAJE) // 100


def calcular_impacto_comision_refund(
    *,
    importe_bruto_cents: int,
    causa: CausaReembolso,
    parte_ejecutada_cents: int = 0,
    conservar_comision_total: bool = False,
) -> tuple[Optional[ImpactoComisionRefund], Optional[str]]:
    """
    Calcula impacto de comisión según causa aprobada.

    Returns:
        (impacto, error) — error si validación falla o causa INDETERMINADO.
    """
    if importe_bruto_cents <= 0:
        return None, "importe_bruto_cents debe ser > 0"
    if causa == CausaReembolso.INDETERMINADO:
        return None, "causa indeterminada: no se puede calcular comisión"

    comision_total = _comision_sobre(importe_bruto_cents)
    redondeo = f"floor(importe*{COMISION_PORCENTAJE}/100)"

    if causa == CausaReembolso.SERVICIO_NO_INICIADO:
        return ImpactoComisionRefund(
            comision_total_cents=comision_total,
            comision_conservada_cents=0,
            comision_devuelta_cents=comision_total,
            parte_ejecutada_cents=0,
            parte_no_ejecutada_cents=importe_bruto_cents,
            causa_aplicada=causa.value,
            redondeo_aplicado=redondeo,
        ), None

    if causa == CausaReembolso.ERROR_RUANA:
        return ImpactoComisionRefund(
            comision_total_cents=comision_total,
            comision_conservada_cents=0,
            comision_devuelta_cents=comision_total,
            parte_ejecutada_cents=0,
            parte_no_ejecutada_cents=importe_bruto_cents,
            causa_aplicada=causa.value,
            redondeo_aplicado=redondeo,
        ), None

    if causa in (
        CausaReembolso.INCUMPLIMIENTO_PROFESIONAL,
        CausaReembolso.SERVICIO_PARCIAL,
    ):
        if parte_ejecutada_cents < 0:
            return None, "parte_ejecutada_cents no puede ser negativa"
        if parte_ejecutada_cents > importe_bruto_cents:
            return None, "parte_ejecutada supera importe bruto"
        parte_no = importe_bruto_cents - parte_ejecutada_cents
        conservada = _comision_sobre(parte_ejecutada_cents)
        devuelta = comision_total - conservada
        if devuelta < 0:
            return None, "comisión devuelta inválida"
        if conservada + devuelta != comision_total:
            return None, "suma comisión conservada + devuelta != total"
        return ImpactoComisionRefund(
            comision_total_cents=comision_total,
            comision_conservada_cents=conservada,
            comision_devuelta_cents=devuelta,
            parte_ejecutada_cents=parte_ejecutada_cents,
            parte_no_ejecutada_cents=parte_no,
            causa_aplicada=causa.value,
            redondeo_aplicado=redondeo,
        ), None

    if causa == CausaReembolso.CANCELACION_INJUSTIFICADA_CONTRATANTE:
        if conservar_comision_total:
            return ImpactoComisionRefund(
                comision_total_cents=comision_total,
                comision_conservada_cents=comision_total,
                comision_devuelta_cents=0,
                parte_ejecutada_cents=importe_bruto_cents,
                parte_no_ejecutada_cents=0,
                causa_aplicada=causa.value,
                redondeo_aplicado=redondeo,
            ), None
        return ImpactoComisionRefund(
            comision_total_cents=comision_total,
            comision_conservada_cents=0,
            comision_devuelta_cents=comision_total,
            parte_ejecutada_cents=0,
            parte_no_ejecutada_cents=importe_bruto_cents,
            causa_aplicada=causa.value,
            redondeo_aplicado=redondeo,
        ), None

    return None, f"causa no soportada: {causa.value}"
