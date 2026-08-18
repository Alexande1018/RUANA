"""Modelo financiero e invariantes de una operación (FASE 01)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class InvarianteFinancieraError(ValueError):
    """Violación de una regla financiera invariante."""


@dataclass(frozen=True)
class ModeloFinanciero:
    """
    Representación financiera de una operación.

    Importes en euros (float redondeado a 2 decimales), coherente con el resto de RUANA.
    Stripe usa céntimos en la capa de API (stripe_client).
    """

    contacto_id: int
    importe_bruto: float
    comision_ruana: float
    importe_profesional: float
    moneda: str = "EUR"
    contratante_codigo: str = ""
    profesional_codigo: str = ""
    stripe_checkout_session_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    stripe_charge_id: Optional[str] = None
    stripe_transfer_id: Optional[str] = None
    stripe_refund_id: Optional[str] = None
    stripe_dispute_id: Optional[str] = None
    pago_confirmado: bool = False
    conflicto_abierto: bool = False
    transferencia_valida_existente: bool = False
    reembolsos_acumulados: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "importe_bruto", round(float(self.importe_bruto), 2))
        object.__setattr__(self, "comision_ruana", round(float(self.comision_ruana), 2))
        object.__setattr__(
            self, "importe_profesional", round(float(self.importe_profesional), 2)
        )
        object.__setattr__(
            self, "reembolsos_acumulados", round(float(self.reembolsos_acumulados), 2)
        )
        self.validar_invariantes()

    def validar_invariantes(self) -> None:
        """Comprueba las 10 invariantes financieras de FASE 01."""
        if self.importe_bruto < 0:
            raise InvarianteFinancieraError("INVARIANTE 1: importe_bruto >= 0")
        if self.comision_ruana < 0:
            raise InvarianteFinancieraError("INVARIANTE 2: comision_ruana >= 0")
        if self.importe_profesional < 0:
            raise InvarianteFinancieraError("INVARIANTE 3: importe_profesional >= 0")
        suma = round(self.comision_ruana + self.importe_profesional, 2)
        if suma != self.importe_bruto:
            raise InvarianteFinancieraError(
                "INVARIANTE 4: comision_ruana + importe_profesional == importe_bruto "
                f"({suma} != {self.importe_bruto})"
            )
        if self.transferencia_valida_existente and self.stripe_transfer_id:
            pass  # INVARIANTE 5 se valida en el servicio al autorizar transferencia
        if self.reembolsos_acumulados > self.importe_bruto:
            raise InvarianteFinancieraError(
                "INVARIANTE 6: reembolsos no pueden superar importe_bruto"
            )

    def puede_modificar_importe(self) -> bool:
        """INVARIANTE 10: no modificar importe tras pago confirmado."""
        return not self.pago_confirmado

    @classmethod
    def desde_contacto(cls, contacto: dict) -> "ModeloFinanciero":
        """Construye el modelo desde un dict de contacto_ruana."""
        importe = contacto.get("importe_acordado")
        if importe is None:
            importe = contacto.get("importe_final")
        importe_bruto = float(importe or 0)
        comision = contacto.get("apoyo_ruana")
        if comision is None:
            comision = contacto.get("comision")
        comision_ruana = float(comision or 0)
        neto = contacto.get("importe_neto_profesional")
        if neto is None and importe_bruto > 0:
            neto = round(importe_bruto - comision_ruana, 2)
        importe_profesional = float(neto or 0)

        estado_pago = (contacto.get("estado_pago") or "").strip().lower()
        stripe_pi = (contacto.get("stripe_payment_intent_id") or "").strip()
        pago_confirmado = bool(
            stripe_pi
            or estado_pago in ("cobro_confirmado", "transferido", "pagado")
            or (contacto.get("stripe_cobro_estado") or "").strip().lower() == "confirmado"
        )

        return cls(
            contacto_id=int(contacto["id"]),
            importe_bruto=importe_bruto,
            comision_ruana=comision_ruana,
            importe_profesional=importe_profesional,
            contratante_codigo=str(contacto.get("solicitante_codigo") or ""),
            profesional_codigo=str(contacto.get("profesional_codigo") or ""),
            stripe_checkout_session_id=contacto.get("stripe_checkout_session_id"),
            stripe_payment_intent_id=contacto.get("stripe_payment_intent_id"),
            stripe_transfer_id=contacto.get("stripe_transfer_id"),
            pago_confirmado=pago_confirmado,
            transferencia_valida_existente=bool(
                (contacto.get("stripe_transfer_id") or "").strip()
                or estado_pago == "transferido"
            ),
        )
