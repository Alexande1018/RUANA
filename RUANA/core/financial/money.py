"""Operaciones monetarias en céntimos enteros (FASE 14).

Todo el cálculo financiero interno usa enteros; la conversión a euros (REAL en BD)
solo ocurre en el borde de persistencia legacy.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Tuple, Union

COMISION_RUANA_PCT = 12
CENTIMOS_POR_EURO = 100

AmountInput = Union[int, float, str, Decimal, None]


def importe_bd_a_cents(val: AmountInput) -> int:
    """Convierte un importe en euros (BD/API legacy) a céntimos enteros."""
    if val is None:
        return 0
    if isinstance(val, bool):
        return 0
    if isinstance(val, int):
        return max(0, int(val) * CENTIMOS_POR_EURO)
    text = str(val).strip()
    if not text:
        return 0
    cents = (Decimal(text) * CENTIMOS_POR_EURO).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, int(cents))


def cents_a_importe_bd(cents: int) -> float:
    """Convierte céntimos a euros para columnas REAL legacy (2 decimales exactos)."""
    return float(
        (Decimal(int(cents)) / Decimal(CENTIMOS_POR_EURO)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )


def comision_ruana_cents(importe_bruto_cents: int) -> int:
    if importe_bruto_cents <= 0:
        return 0
    return (int(importe_bruto_cents) * COMISION_RUANA_PCT) // 100


def neto_profesional_cents(importe_bruto_cents: int) -> int:
    bruto = max(0, int(importe_bruto_cents))
    return bruto - comision_ruana_cents(bruto)


def calcular_desglose_stripe_cents(importe_bruto_cents: int) -> Tuple[int, int, int, float]:
    """
    Reparto 88 % profesional / 12 % RUANA en céntimos enteros.

    Returns:
        (bruto_cents, apoyo_cents, neto_cents, comision_porcentaje_legacy)
    """
    bruto = max(0, int(importe_bruto_cents))
    apoyo = comision_ruana_cents(bruto)
    neto = bruto - apoyo
    comision_pct = COMISION_RUANA_PCT / CENTIMOS_POR_EURO
    return bruto, apoyo, neto, comision_pct


def stripe_amount_a_cents(amount: Any) -> int:
    """Importe Stripe API (ya en céntimos) como entero no negativo."""
    try:
        return max(0, int(amount or 0))
    except (TypeError, ValueError):
        return 0
