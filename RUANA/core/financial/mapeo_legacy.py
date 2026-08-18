"""Mapeo entre estados legacy (estado_pago) y estados financieros canónicos."""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.financial.estados import EstadoFinanciero


def inferir_estado_financiero_desde_legacy(contacto: Dict[str, Any]) -> EstadoFinanciero:
    """
    Infiere el estado financiero canónico desde datos legacy.

    No inventa TRANSFERIDO sin evidencia (stripe_transfer_id o estado_pago=transferido).
    Si no hay información suficiente → MIGRACION_PENDIENTE.
    """
    modo = (contacto.get("modo_pago") or "manual").strip().lower()
    estado_pago = (contacto.get("estado_pago") or "no_generado").strip().lower()
    estado_servicio = (contacto.get("estado") or "").strip().lower()
    transfer_id = (contacto.get("stripe_transfer_id") or "").strip()
    payment_intent = (contacto.get("stripe_payment_intent_id") or "").strip()

    if modo == "stripe":
        return _mapear_stripe(estado_pago, estado_servicio, transfer_id, payment_intent, contacto)
    return _mapear_manual(estado_pago, estado_servicio, contacto)


def estado_pago_legacy_desde_financiero(
    estado: EstadoFinanciero, modo_pago: str = "stripe"
) -> Optional[str]:
    """Mapeo inverso parcial (solo donde existe equivalente legacy)."""
    modo = (modo_pago or "manual").strip().lower()
    if modo == "stripe":
        return _MAPEO_INVERSO_STRIPE.get(estado)
    return _MAPEO_INVERSO_MANUAL.get(estado)


def _mapear_stripe(
    estado_pago: str,
    estado_servicio: str,
    transfer_id: str,
    payment_intent: str,
    contacto: Dict[str, Any],
) -> EstadoFinanciero:
    if transfer_id or estado_pago == "transferido":
        return EstadoFinanciero.TRANSFERIDO
    if estado_pago == "revision_admin":
        return EstadoFinanciero.CONFLICTO_ABIERTO
    if estado_pago in ("esperando_cobro_cliente", "checkout_activo"):
        return EstadoFinanciero.PAGO_PENDIENTE
    if estado_pago == "cobro_confirmado" or payment_intent:
        if contacto.get("fecha_confirmacion_trabajo"):
            return EstadoFinanciero.LIBERACION_AUTORIZADA
        return EstadoFinanciero.ESPERANDO_CONFIRMACION
    if estado_servicio == "pendiente_de_pago" and not estado_pago:
        return EstadoFinanciero.PAGO_PENDIENTE
    if estado_pago in ("no_generado", ""):
        return EstadoFinanciero.PAGO_NO_INICIADO
    return EstadoFinanciero.MIGRACION_PENDIENTE


def _mapear_manual(estado_pago: str, estado_servicio: str, contacto: Dict[str, Any]) -> EstadoFinanciero:
    if estado_pago in ("no_generado", ""):
        return EstadoFinanciero.PAGO_NO_INICIADO
    if estado_pago == "pendiente_pago":
        return EstadoFinanciero.PAGO_CONFIRMADO
    if estado_pago == "en_revision":
        return EstadoFinanciero.PAGO_CONFIRMADO
    if estado_pago == "pagado":
        return EstadoFinanciero.PAGO_CONFIRMADO
    if estado_servicio == "importe_en_disputa":
        return EstadoFinanciero.CONFLICTO_ABIERTO
    return EstadoFinanciero.MIGRACION_PENDIENTE


_MAPEO_INVERSO_STRIPE = {
    EstadoFinanciero.PAGO_NO_INICIADO: "no_generado",
    EstadoFinanciero.PAGO_PENDIENTE: "esperando_cobro_cliente",
    EstadoFinanciero.PAGO_CONFIRMADO: "cobro_confirmado",
    EstadoFinanciero.ESPERANDO_CONFIRMACION: "cobro_confirmado",
    EstadoFinanciero.TRABAJO_EN_CURSO: "cobro_confirmado",
    EstadoFinanciero.TRANSFERIDO: "transferido",
    EstadoFinanciero.CONFLICTO_ABIERTO: "revision_admin",
}

_MAPEO_INVERSO_MANUAL = {
    EstadoFinanciero.PAGO_NO_INICIADO: "no_generado",
    EstadoFinanciero.PAGO_CONFIRMADO: "pendiente_pago",
    EstadoFinanciero.CONFLICTO_ABIERTO: "pendiente_pago",
}
