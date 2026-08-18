"""Servicio de reconciliación financiera RUANA ↔ Stripe (FASE 02)."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from core.financial.discrepancia import TipoDiscrepancia
from core.financial.estados import EstadoFinanciero
from core.repositories.financial_reconciliation_repo import FinancialReconciliationRepo

_repo = FinancialReconciliationRepo()


def _importe_contacto(contacto: Dict[str, Any]) -> float:
    val = contacto.get("importe_acordado")
    if val is None:
        val = contacto.get("importe_final")
    return round(float(val or 0), 2)


def _row_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return dict(row)
    return {}


def registrar_discrepancia(
    db,
    contacto_id: int,
    tipo: TipoDiscrepancia,
    *,
    stripe_payment_intent_id: str = "",
    stripe_transfer_id: str = "",
    ruana_estado: str = "",
    stripe_estado: str = "",
    importe_ruana: Optional[float] = None,
    importe_stripe: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    alerta_admin: bool = True,
) -> Dict[str, Any]:
    """Registra discrepancia sin duplicar abiertas del mismo tipo."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            disc_id = _repo.insertar_discrepancia(
                cursor,
                contacto_id,
                tipo.value,
                stripe_payment_intent_id=stripe_payment_intent_id,
                stripe_transfer_id=stripe_transfer_id,
                ruana_estado=ruana_estado,
                stripe_estado=stripe_estado,
                importe_ruana=importe_ruana,
                importe_stripe=importe_stripe,
                metadata=metadata,
            )
            if disc_id and alerta_admin:
                db.registrar_evento_sistema(
                    "reconciliacion_discrepancia",
                    f"Discrepancia {tipo.value} en contacto #{contacto_id}",
                    actor_tipo="sistema",
                    metadata={
                        "contacto_id": contacto_id,
                        "tipo": tipo.value,
                        "discrepancia_id": disc_id,
                    },
                )
            conn.commit()
            return {
                "status": "success" if disc_id else "ignored",
                "discrepancia_id": disc_id,
                "duplicado": disc_id is None,
            }
        finally:
            if conn:
                conn.close()


def reconciliar_contacto(
    db,
    contacto_id: int,
    *,
    stripe_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compara estado RUANA vs snapshot Stripe.

    stripe_snapshot opcional: {
        payment_intent: {id, amount, currency, status},
        transfer: {id, amount, currency, status},
    }
    No modifica dinero; solo detecta y registra discrepancias.
    """
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, estado_financiero, estado_transferencia,
                       stripe_payment_intent_id, stripe_transfer_id,
                       importe_acordado, importe_final, importe_neto_profesional,
                       modo_pago, estado_pago
                FROM contactos_ruana WHERE id = ?
                """,
                (contacto_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            if contacto.get("modo_pago") != "stripe":
                return {"status": "ignored", "message": "No es contacto Stripe"}

            discrepancias: List[Dict[str, Any]] = []
            importe_ruana = _importe_contacto(contacto)
            ruana_estado = (contacto.get("estado_financiero") or "").strip()
            pi_ruana = (contacto.get("stripe_payment_intent_id") or "").strip()
            tr_ruana = (contacto.get("stripe_transfer_id") or "").strip()

            snap = stripe_snapshot or {}
            pi_snap = snap.get("payment_intent") or {}
            tr_snap = snap.get("transfer") or {}

            pi_status = (pi_snap.get("status") or "").strip().lower()
            pi_id = (pi_snap.get("id") or "").strip()
            pi_amount = pi_snap.get("amount")
            pi_currency = (pi_snap.get("currency") or "eur").strip().lower()

            tr_status = (tr_snap.get("status") or tr_snap.get("object") or "").strip().lower()
            tr_id = (tr_snap.get("id") or "").strip()
            tr_amount = tr_snap.get("amount")

            pagado_ruana = ruana_estado in (
                EstadoFinanciero.PAGO_CONFIRMADO.value,
                EstadoFinanciero.TRABAJO_EN_CURSO.value,
                EstadoFinanciero.ESPERANDO_CONFIRMACION.value,
                EstadoFinanciero.LIBERACION_AUTORIZADA.value,
                EstadoFinanciero.TRANSFERENCIA_PENDIENTE.value,
                EstadoFinanciero.TRANSFERENCIA_ENVIADA.value,
                EstadoFinanciero.TRANSFERIDO.value,
            ) or (contacto.get("estado_pago") or "") in ("cobro_confirmado", "transferido")

            pagado_stripe = pi_status in ("succeeded", "paid")

            if pagado_ruana and pi_snap and not pagado_stripe:
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.PAYMENT_MISSING_STRIPE,
                    pi_ruana, tr_ruana, ruana_estado, pi_status,
                    importe_ruana, _cents_to_eur(pi_amount),
                )
                if r:
                    discrepancias.append(r)
            if pagado_stripe and not pagado_ruana:
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.PAYMENT_MISSING_RUANA,
                    pi_id or pi_ruana, tr_ruana, ruana_estado, pi_status,
                    importe_ruana, _cents_to_eur(pi_amount),
                )
                if r:
                    discrepancias.append(r)

            if pi_amount is not None and importe_ruana > 0:
                stripe_eur = _cents_to_eur(pi_amount)
                if abs(importe_ruana - stripe_eur) > 0.01:
                    r = _registrar_en_cursor(
                        cursor, contacto_id, TipoDiscrepancia.AMOUNT_MISMATCH,
                        pi_ruana, tr_ruana, ruana_estado, pi_status,
                        importe_ruana, stripe_eur,
                    )
                    if r:
                        discrepancias.append(r)

            if pi_currency and pi_currency != "eur":
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.CURRENCY_MISMATCH,
                    pi_ruana, tr_ruana, ruana_estado, pi_currency,
                    importe_ruana, None,
                )
                if r:
                    discrepancias.append(r)

            if pi_id and tr_ruana and tr_id != tr_ruana:
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.TRANSFER_ID_MISMATCH,
                    pi_ruana, tr_ruana, ruana_estado, tr_id,
                    importe_ruana, _cents_to_eur(tr_amount),
                )
                if r:
                    discrepancias.append(r)

            if pi_id and pi_ruana and pi_id != pi_ruana:
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.PAYMENT_INTENT_MISMATCH,
                    pi_ruana, tr_ruana, ruana_estado, pi_id,
                    importe_ruana, _cents_to_eur(pi_amount),
                )
                if r:
                    discrepancias.append(r)

            transferido_ruana = ruana_estado == EstadoFinanciero.TRANSFERIDO.value
            if transferido_ruana and "transfer" in snap and not tr_id:
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.TRANSFER_MISSING_STRIPE,
                    pi_ruana, tr_ruana, ruana_estado, tr_status,
                    importe_ruana, _cents_to_eur(tr_amount),
                )
                if r:
                    discrepancias.append(r)

            if tr_id and not transferido_ruana and tr_status not in ("", "failed"):
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.TRANSFER_MISSING_RUANA,
                    pi_ruana, tr_id, ruana_estado, tr_status,
                    importe_ruana, _cents_to_eur(tr_amount),
                )
                if r:
                    discrepancias.append(r)

            if transferido_ruana and tr_status == "failed":
                r = _registrar_en_cursor(
                    cursor, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
                    pi_ruana, tr_ruana, ruana_estado, tr_status,
                    importe_ruana, _cents_to_eur(tr_amount),
                    metadata={"nota": "RUANA TRANSFERIDO pero Stripe failed — requiere revisión manual"},
                )
                if r:
                    discrepancias.append(r)

            conn.commit()
            return {
                "status": "success",
                "contacto_id": contacto_id,
                "discrepancias_nuevas": len(discrepancias),
                "discrepancias": discrepancias,
            }
        finally:
            if conn:
                conn.close()


def ejecutar_reconciliacion_lote(
    db,
    limit: int = 100,
    stripe_fetcher=None,
) -> Dict[str, Any]:
    """Ejecuta reconciliación sobre un lote de contactos Stripe. Idempotente."""
    procesados = 0
    discrepancias_total = 0
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            filas = _repo.listar_contactos_stripe(cursor, limit)
            conn.close()
        finally:
            if conn:
                conn.close()

    for row in filas:
        contacto = _row_dict(row)
        cid = int(contacto["id"])
        snap = None
        if stripe_fetcher:
            snap = stripe_fetcher(contacto)
        res = reconciliar_contacto(db, cid, stripe_snapshot=snap)
        if res.get("status") == "success":
            procesados += 1
            discrepancias_total += res.get("discrepancias_nuevas", 0)

    return {
        "status": "success",
        "procesados": procesados,
        "discrepancias_nuevas": discrepancias_total,
    }


def _registrar_en_cursor(
    cursor,
    contacto_id: int,
    tipo: TipoDiscrepancia,
    pi_id: str,
    tr_id: str,
    ruana_estado: str,
    stripe_estado: str,
    importe_ruana: Optional[float],
    importe_stripe: Optional[float],
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    disc_id = _repo.insertar_discrepancia(
        cursor,
        contacto_id,
        tipo.value,
        stripe_payment_intent_id=pi_id,
        stripe_transfer_id=tr_id,
        ruana_estado=ruana_estado,
        stripe_estado=stripe_estado,
        importe_ruana=importe_ruana,
        importe_stripe=importe_stripe,
        metadata=metadata,
    )
    if not disc_id:
        return None
    return {"id": disc_id, "tipo": tipo.value}


def _cents_to_eur(amount) -> Optional[float]:
    if amount is None:
        return None
    return round(float(amount) / 100.0, 2)
