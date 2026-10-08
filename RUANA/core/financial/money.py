"""Operaciones monetarias en céntimos enteros (FASE 14).

Todo el cálculo financiero interno usa enteros; la conversión a euros (REAL en BD)
solo ocurre en el borde de persistencia legacy.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Tuple, Union

COMISION_RUANA_PCT = 5
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


def comision_ruana_cents(importe_bruto_cents: int, porcentaje: int | None = None) -> int:
    """Comisión vigente en céntimos. `porcentaje` solo si el encargo ya trae otra tasa."""
    if importe_bruto_cents <= 0:
        return 0
    pct = COMISION_RUANA_PCT if porcentaje is None else int(porcentaje)
    if pct < 0:
        pct = 0
    return (int(importe_bruto_cents) * pct) // 100


def neto_profesional_cents(importe_bruto_cents: int, porcentaje: int | None = None) -> int:
    bruto = max(0, int(importe_bruto_cents))
    return bruto - comision_ruana_cents(bruto, porcentaje)


def calcular_desglose_stripe_cents(
    importe_bruto_cents: int, porcentaje: int | None = None
) -> Tuple[int, int, int, float]:
    """
    Reparto vigente: 95 % profesional / 5 % RUANA, en céntimos enteros.
    Si `porcentaje` viene del registro, se usa esa tasa y no la vigente.

    Returns:
        (bruto_cents, apoyo_cents, neto_cents, comision_porcentaje_legacy)
    """
    bruto = max(0, int(importe_bruto_cents))
    pct = COMISION_RUANA_PCT if porcentaje is None else int(porcentaje)
    apoyo = comision_ruana_cents(bruto, pct)
    neto = bruto - apoyo
    comision_pct = pct / CENTIMOS_POR_EURO
    return bruto, apoyo, neto, comision_pct


def porcentaje_apoyo_congelado(contacto: Any) -> float | None:
    """Porcentaje 0–100 ya guardado en el encargo.

    None si todavía no hay apoyo: el default de columna no cuenta como tasa cerrada.
    """
    if not contacto or not hasattr(contacto, "get"):
        return None
    apoyo = contacto.get("apoyo_ruana")
    if apoyo is None:
        apoyo = contacto.get("comision")
    if apoyo is None:
        return None
    bruto = contacto.get("importe_final")
    if bruto is None:
        bruto = contacto.get("importe_acordado")
    try:
        apoyo_f = float(apoyo)
        bruto_f = float(bruto) if bruto is not None else 0.0
    except (TypeError, ValueError):
        return None
    if bruto_f > 0 and apoyo_f >= 0:
        return round(apoyo_f * 100.0 / bruto_f, 4)
    pct = contacto.get("comision_porcentaje")
    if pct is None:
        return None
    try:
        val = float(pct)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    return round(val * 100.0, 4) if val <= 1 else round(val, 4)


def desglose_congelado_cents(
    contacto: Any, importe_bruto_cents: int
) -> Tuple[int, int, int, float] | None:
    """Reparto ya persistido. None si el encargo aún no tiene apoyo guardado."""
    if not contacto or not hasattr(contacto, "get"):
        return None
    apoyo = contacto.get("apoyo_ruana")
    if apoyo is None:
        apoyo = contacto.get("comision")
    if apoyo is None:
        return None
    bruto = max(0, int(importe_bruto_cents))
    apoyo_c = importe_bd_a_cents(apoyo)
    neto_raw = contacto.get("importe_neto_profesional")
    if neto_raw is not None:
        neto_c = importe_bd_a_cents(neto_raw)
    else:
        neto_c = max(0, bruto - apoyo_c)
    # La fracción sale del apoyo guardado, no del default de columna.
    if bruto > 0:
        comision_pct = round(apoyo_c / bruto, 4)
    else:
        comision_pct = 0.0
        pct_raw = contacto.get("comision_porcentaje")
        if pct_raw is not None:
            try:
                val = float(pct_raw)
                if val > 0:
                    comision_pct = val if val <= 1 else val / 100.0
            except (TypeError, ValueError):
                comision_pct = 0.0
    return bruto, apoyo_c, neto_c, comision_pct


def stripe_amount_a_cents(amount: Any) -> int:
    """Importe Stripe API (ya en céntimos) como entero no negativo."""
    try:
        return max(0, int(amount or 0))
    except (TypeError, ValueError):
        return 0
