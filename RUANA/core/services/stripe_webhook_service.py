"""Procesamiento robusto de webhooks Stripe (FASE 02)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional, Tuple

from core import stripe_client
from core.financial.discrepancia import TipoDiscrepancia
from core.financial.estados import EstadoFinanciero, EstadoTransferencia
from core.financial.state_machine import FinancialStateMachine
from core.repositories.financial_transaction_repo import FinancialTransactionRepo
from core.repositories.stripe_webhook_repo import StripeWebhookRepo
from core.services import financial_reconciliation_service as reconciliation
from core.services import financial_transaction_service as fts
from core.services import pago_service

_wh_repo = StripeWebhookRepo()
_fin_repo = FinancialTransactionRepo()
_sm = FinancialStateMachine()

# Estados financieros que implican pago ya confirmado (no retroceder a PAGO_FALLIDO)
_ESTADOS_POST_PAGO = frozenset({
    EstadoFinanciero.PAGO_CONFIRMADO,
    EstadoFinanciero.TRABAJO_EN_CURSO,
    EstadoFinanciero.TRABAJO_ENTREGADO,
    EstadoFinanciero.ESPERANDO_CONFIRMACION,
    EstadoFinanciero.LIBERACION_AUTORIZADA,
    EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
    EstadoFinanciero.TRANSFERENCIA_ENVIADA,
    EstadoFinanciero.TRANSFERIDO,
    EstadoFinanciero.REEMBOLSO_PENDIENTE,
    EstadoFinanciero.REEMBOLSADO,
    EstadoFinanciero.DISPUTA_STRIPE,
})

_ESTADOS_TERMINALES_TRANSFER = frozenset({
    EstadoFinanciero.TRANSFERIDO,
    EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
    EstadoFinanciero.REEMBOLSADO,
})


def procesar_webhook(db, payload: bytes, sig_header: str) -> Dict[str, Any]:
    """Punto de entrada: valida firma, reclama evento atómicamente y despacha."""
    try:
        event = stripe_client.construct_webhook_event(payload, sig_header)
    except Exception as e:
        _log_incidente_firma(db, str(e))
        return {"status": "error", "message": f"firma webhook inválida: {e}"}

    event_id, event_type, obj = _extraer_evento(event)
    if not event_id or not event_type:
        return {"status": "error", "message": "evento incompleto"}

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            claim = _wh_repo.reclamar_evento(cursor, event_id, event_type)
            if claim == "duplicate_ok":
                conn.commit()
                conn.close()
                return {"status": "success", "message": "evento ya procesado", "duplicate": True}
            if claim == "duplicate_processing":
                conn.commit()
                conn.close()
                return {"status": "success", "message": "evento en procesamiento", "duplicate": True}
            conn.commit()
        finally:
            if conn:
                conn.close()

    contacto_id: Optional[int] = None
    estado_anterior = ""
    estado_nuevo = ""
    object_id = _object_id(obj)
    resultado = "ignorado"

    try:
        handler = _HANDLERS.get(event_type, _handle_desconocido)
        contacto_id, resultado, estado_anterior, estado_nuevo = handler(db, obj, event_id)
    except Exception as e:
        with db._lock:
            conn = db._connect()
            cursor = conn.cursor()
            _wh_repo.marcar_evento_fallido(cursor, event_id, str(e))
            conn.commit()
            conn.close()
        return {"status": "error", "message": str(e), "retry": True}

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            _wh_repo.finalizar_evento(
                cursor,
                event_id,
                resultado,
                contacto_id=contacto_id,
                object_id=object_id,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_nuevo,
            )
            if contacto_id and estado_anterior != estado_nuevo:
                _wh_repo.audit_webhook(
                    db,
                    cursor,
                    contacto_id,
                    "stripe_webhook_procesado",
                    {
                        "event_id": event_id,
                        "event_type": event_type,
                        "object_id": object_id,
                        "estado_anterior": estado_anterior,
                        "estado_nuevo": estado_nuevo,
                        "resultado": resultado,
                    },
                )
            conn.commit()
        finally:
            if conn:
                conn.close()

    return {
        "status": "success",
        "event_type": event_type,
        "resultado": resultado,
        "contacto_id": contacto_id,
    }


def _extraer_evento(event) -> Tuple[str, str, Any]:
    event_id = getattr(event, "id", None) or (event.get("id") if isinstance(event, dict) else None)
    event_type = getattr(event, "type", None) or (event.get("type") if isinstance(event, dict) else None)
    data_obj = getattr(event, "data", None) or (event.get("data") if isinstance(event, dict) else {})
    obj = getattr(data_obj, "object", None) if data_obj is not None else None
    if obj is None and isinstance(data_obj, dict):
        obj = data_obj.get("object")
    return str(event_id or ""), str(event_type or ""), obj


def _object_id(obj) -> str:
    oid = getattr(obj, "id", None) or (obj.get("id") if isinstance(obj, dict) else None)
    return str(oid or "")


def _metadata(obj) -> Dict[str, Any]:
    meta = getattr(obj, "metadata", None) or (obj.get("metadata") if isinstance(obj, dict) else {})
    return dict(meta or {})


def _get(obj, key: str, default=None):
    val = getattr(obj, key, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _contacto_id_desde_metadata(obj) -> Optional[int]:
    meta = _metadata(obj)
    raw = meta.get("contacto_id")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return None


def _estados_contacto(db, contacto_id: int) -> Tuple[str, str]:
    estado = fts.obtener_estado_financiero(db, contacto_id)
    anterior = estado.value if estado else ""
    return anterior, anterior


def _transicion_si_valida(
    db, contacto_id: int, objetivo: EstadoFinanciero, **kwargs
) -> Tuple[str, str, str]:
    anterior = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = anterior.value if anterior else ""
    res = fts.transicionar(db, contacto_id, objetivo, actor_tipo="stripe_webhook", **kwargs)
    if res.get("status") == "success":
        return ant_val, res.get("estado_nuevo", objetivo.value), "ok"
    if anterior == objetivo:
        return ant_val, ant_val, "idempotent"
    return ant_val, ant_val, res.get("message", "transition_skipped")


def _actualizar_estado_transferencia(
    db, contacto_id: int, estado_transferencia: EstadoTransferencia
) -> None:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _fin_repo.actualizar_solo_estado_transferencia(
            cursor, contacto_id, estado_transferencia.value
        )
        conn.commit()
        conn.close()


def _handle_checkout_session_completed(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    payment_status = _get(obj, "payment_status")
    if payment_status != "paid":
        return None, "ignored_unpaid", "", ""

    contacto_id = _contacto_id_desde_metadata(obj)
    session_id = _object_id(obj)
    payment_intent_id = str(_get(obj, "payment_intent") or "")
    if not contacto_id or not payment_intent_id:
        return None, "missing_metadata", "", ""

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        if not _wh_repo.select_contacto_por_metadata(cursor, contacto_id):
            conn.close()
            return None, "contacto_invalido", "", ""
        _wh_repo.actualizar_checkout_session(cursor, contacto_id, session_id, payment_intent_id)
        conn.commit()
        conn.close()

    row = _fin_repo_contacto(db, contacto_id)
    if row and (row.get("stripe_payment_intent_id") or "").strip() == payment_intent_id:
        estado = fts.obtener_estado_financiero(db, contacto_id)
        if estado in _ESTADOS_POST_PAGO:
            return contacto_id, "already_confirmed", estado.value if estado else "", estado.value if estado else ""

    ant, nuevo, res = _procesar_cobro(db, contacto_id, payment_intent_id, event_id)
    return contacto_id, res, ant, nuevo


def _handle_payment_intent_succeeded(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    meta = _metadata(obj)
    if meta.get("tipo") != "encargo_ruana":
        return None, "ignored_tipo", "", ""
    contacto_id = _contacto_id_desde_metadata(obj)
    payment_intent_id = _object_id(obj)
    if not contacto_id or not payment_intent_id:
        return None, "missing_metadata", "", ""

    row = _fin_repo_contacto(db, contacto_id)
    if row and (row.get("stripe_payment_intent_id") or "").strip() == payment_intent_id:
        estado = fts.obtener_estado_financiero(db, contacto_id)
        if estado in _ESTADOS_POST_PAGO:
            return contacto_id, "already_confirmed", estado.value if estado else "", estado.value if estado else ""

    ant, nuevo, res = _procesar_cobro(db, contacto_id, payment_intent_id, event_id)
    return contacto_id, res, ant, nuevo


def _procesar_cobro(
    db, contacto_id: int, payment_intent_id: str, event_id: str
) -> Tuple[str, str, str]:
    ant_antes = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = ant_antes.value if ant_antes else ""
    res = pago_service._procesar_pago_confirmado(db, contacto_id, payment_intent_id)
    status = res.get("status", "error")
    if status == "success":
        fts.sincronizar_tras_cobro_confirmado(db, contacto_id, payment_intent_id)
    elif status == "ignored":
        fts.sincronizar_tras_cobro_confirmado(db, contacto_id, payment_intent_id)
    estado_despues = fts.obtener_estado_financiero(db, contacto_id)
    nuevo_val = estado_despues.value if estado_despues else ant_val
    return ant_val, nuevo_val, status


def _handle_payment_intent_payment_failed(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    contacto_id = _contacto_id_desde_metadata(obj)
    if not contacto_id:
        pi_id = _object_id(obj)
        with db._lock:
            conn = db._connect()
            cursor = conn.cursor()
            row = _wh_repo.select_contacto_por_payment_intent(cursor, pi_id)
            conn.close()
        if row:
            contacto_id = int(row[0] if not hasattr(row, "keys") else row["id"])
    if not contacto_id:
        return None, "contacto_no_encontrado", "", ""

    estado = fts.obtener_estado_financiero(db, contacto_id)
    if estado in _ESTADOS_POST_PAGO:
        return contacto_id, "ignored_post_pago", estado.value, estado.value

    ant, nuevo, res = _transicion_si_valida(
        db, contacto_id, EstadoFinanciero.PAGO_FALLIDO,
        motivo="payment_intent.payment_failed", stripe_ref=event_id,
    )
    return contacto_id, res, ant, nuevo


def _handle_checkout_session_expired(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    contacto_id = _contacto_id_desde_metadata(obj)
    if not contacto_id:
        return None, "ignored", "", ""
    from core.repositories.pago_repo import PagoRepo
    repo = PagoRepo()
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        repo.reset_checkout_expirado(cursor, contacto_id)
        conn.commit()
        conn.close()
    return contacto_id, "ok", "", ""


def _handle_account_updated(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    account_id = _object_id(obj)
    charges = bool(_get(obj, "charges_enabled", False))
    payouts = bool(_get(obj, "payouts_enabled", False))
    details = bool(_get(obj, "details_submitted", False))
    if account_id:
        with db._lock:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE aliados
                SET stripe_charges_enabled = ?, stripe_payouts_enabled = ?,
                    stripe_onboarding_completo = ?,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE stripe_account_id = ?
                """,
                (1 if charges else 0, 1 if payouts else 0, 1 if details else 0, account_id),
            )
            conn.commit()
            conn.close()
    return None, "ok", "", ""


def _resolver_contacto_transfer(db, obj) -> Optional[int]:
    contacto_id = _contacto_id_desde_metadata(obj)
    if contacto_id:
        return contacto_id
    transfer_id = _object_id(obj)
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        row = _wh_repo.select_contacto_por_transfer_id(cursor, transfer_id)
        conn.close()
    if row:
        return int(row[0] if not hasattr(row, "keys") else row["id"])
    return None


def _handle_transfer_created(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    contacto_id = _resolver_contacto_transfer(db, obj)
    transfer_id = _object_id(obj)
    if not contacto_id:
        return None, "contacto_no_encontrado", "", ""

    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _wh_repo.actualizar_stripe_transfer_id(cursor, contacto_id, transfer_id)
        conn.commit()
        conn.close()

    if estado == EstadoFinanciero.TRANSFERIDO:
        _actualizar_estado_transferencia(db, contacto_id, EstadoTransferencia.COMPLETADA)
        return contacto_id, "idempotent", ant_val, ant_val

    if estado in _ESTADOS_TERMINALES_TRANSFER:
        return contacto_id, "idempotent", ant_val, ant_val

    nuevo_val = ant_val
    resultado = "ok"

    if estado in (
        EstadoFinanciero.LIBERACION_AUTORIZADA,
        EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
        None,
    ):
        if estado == EstadoFinanciero.LIBERACION_AUTORIZADA:
            _, nuevo_val, resultado = _transicion_si_valida(
                db, contacto_id, EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
                motivo="transfer.created", stripe_ref=transfer_id,
            )
        if fts.obtener_estado_financiero(db, contacto_id) in (
            EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
            EstadoFinanciero.LIBERACION_AUTORIZADA,
            None,
        ):
            _, nuevo_val, resultado = _transicion_si_valida(
                db, contacto_id, EstadoFinanciero.TRANSFERENCIA_ENVIADA,
                motivo="transfer.created", stripe_ref=transfer_id,
            )

    _actualizar_estado_transferencia(db, contacto_id, EstadoTransferencia.ENVIADA)
    estado_final = fts.obtener_estado_financiero(db, contacto_id)
    return contacto_id, resultado, ant_val, estado_final.value if estado_final else nuevo_val


def _handle_transfer_paid(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    """transfer.paid — confirma transferencia completada en Stripe."""
    from core.services import financial_transfer_service as transfer_svc

    contacto_id = _resolver_contacto_transfer(db, obj)
    transfer_id = _object_id(obj)
    if not contacto_id:
        return None, "contacto_no_encontrado", "", ""

    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""

    if estado == EstadoFinanciero.TRANSFERIDO:
        _actualizar_estado_transferencia(db, contacto_id, EstadoTransferencia.COMPLETADA)
        return contacto_id, "idempotent", ant_val, ant_val

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _wh_repo.actualizar_stripe_transfer_id(cursor, contacto_id, transfer_id)
        conn.commit()
        conn.close()

    fin = transfer_svc.finalizar_transferencia_completada(
        db, contacto_id, transfer_id, origen="stripe_webhook"
    )
    if fin.get("status") == "success":
        nuevo = fin.get("estado_financiero", EstadoFinanciero.TRANSFERIDO.value)
        return contacto_id, "ok" if not fin.get("idempotent") else "idempotent", ant_val, nuevo

    est_final = fts.obtener_estado_financiero(db, contacto_id)
    nuevo_val = est_final.value if est_final else ant_val
    return contacto_id, fin.get("message", "transition_skipped"), ant_val, nuevo_val


def _handle_transfer_failed(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    contacto_id = _resolver_contacto_transfer(db, obj)
    transfer_id = _object_id(obj)
    if not contacto_id:
        return None, "contacto_no_encontrado", "", ""

    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""

    if estado in _ESTADOS_TERMINALES_TRANSFER:
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
            stripe_transfer_id=transfer_id,
            ruana_estado=ant_val,
            stripe_estado="failed",
            metadata={"event_id": event_id, "nota": "transfer.failed tras estado terminal"},
        )
        return contacto_id, "discrepancia_registrada", ant_val, ant_val

    _actualizar_estado_transferencia(db, contacto_id, EstadoTransferencia.FALLIDA)
    _, nuevo_val, res = _transicion_si_valida(
        db, contacto_id, EstadoFinanciero.TRANSFERENCIA_FALLIDA,
        motivo="transfer.failed", stripe_ref=transfer_id,
    )
    db.registrar_evento_sistema(
        "stripe_transfer_fallida",
        f"Transferencia Stripe fallida en contacto #{contacto_id}",
        actor_tipo="sistema",
        metadata={"contacto_id": contacto_id, "transfer_id": transfer_id, "event_id": event_id},
    )
    return contacto_id, res, ant_val, nuevo_val


def _handle_charge_refunded(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    charge_id = _object_id(obj)
    payment_intent_id = str(_get(obj, "payment_intent") or "")
    amount_refunded = _get(obj, "amount_refunded") or _get(obj, "amount") or 0
    currency = str(_get(obj, "currency") or "eur").lower()
    amount_eur = round(float(amount_refunded) / 100.0, 2)

    contacto_id = None
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        if payment_intent_id:
            row = _wh_repo.select_contacto_por_payment_intent(cursor, payment_intent_id)
            if row:
                contacto_id = int(row[0] if not hasattr(row, "keys") else row["id"])
        conn.close()

    if not contacto_id:
        return None, "contacto_no_encontrado", "", ""

    row = _fin_repo_contacto(db, contacto_id)
    importe_bruto = float(row.get("importe_acordado") or row.get("importe_final") or 0)
    es_total = amount_eur >= importe_bruto - 0.01 if importe_bruto > 0 else False
    refund_id = f"re_{charge_id}_{event_id}"[:80]

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _wh_repo.actualizar_stripe_charge_id(cursor, contacto_id, charge_id)
        inserted = _wh_repo.insertar_refund(
            cursor, contacto_id, refund_id, charge_id,
            amount_eur, currency, event_id, es_total,
        )
        total_reembolsado = _wh_repo.sumar_reembolsos_contacto(cursor, contacto_id)
        conn.commit()
        conn.close()

    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""

    if inserted:
        objetivo = EstadoFinanciero.REEMBOLSADO if es_total else EstadoFinanciero.REEMBOLSO_PENDIENTE
        if estado and estado not in (EstadoFinanciero.REEMBOLSADO, EstadoFinanciero.REEMBOLSO_PENDIENTE):
            if _sm.puede_transicionar(estado, EstadoFinanciero.REEMBOLSO_PENDIENTE):
                _, nuevo_val, res = _transicion_si_valida(
                    db, contacto_id, EstadoFinanciero.REEMBOLSO_PENDIENTE,
                    motivo=f"charge.refunded parcial={not es_total} total={total_reembolsado}",
                    stripe_ref=event_id,
                )
                if es_total and _sm.puede_transicionar(
                    fts.obtener_estado_financiero(db, contacto_id) or estado,
                    EstadoFinanciero.REEMBOLSADO,
                ):
                    _, nuevo_val, res = _transicion_si_valida(
                        db, contacto_id, EstadoFinanciero.REEMBOLSADO,
                        motivo="charge.refunded total", stripe_ref=event_id,
                    )
                return contacto_id, res, ant_val, nuevo_val

    return contacto_id, "registrado" if inserted else "idempotent", ant_val, ant_val


def _handle_charge_dispute_created(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    dispute_id = _object_id(obj)
    charge_id = str(_get(obj, "charge") or "")
    amount = _get(obj, "amount") or 0
    currency = str(_get(obj, "currency") or "eur").lower()
    reason = str(_get(obj, "reason") or "")
    status = str(_get(obj, "status") or "needs_response")
    evidence = _get(obj, "evidence_details") or {}
    due_by = None
    if isinstance(evidence, dict):
        due_by = evidence.get("due_by")
    elif hasattr(evidence, "due_by"):
        due_by = evidence.due_by

    payment_intent_id = str(_get(obj, "payment_intent") or "")
    contacto_id = None
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        if payment_intent_id:
            row = _wh_repo.select_contacto_por_payment_intent(cursor, payment_intent_id)
            if row:
                contacto_id = int(row[0] if not hasattr(row, "keys") else row["id"])
        conn.close()

    if not contacto_id:
        return None, "contacto_no_encontrado", "", ""

    amount_eur = round(float(amount) / 100.0, 2)
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        inserted = _wh_repo.insertar_disputa(
            cursor, contacto_id, dispute_id, charge_id,
            amount_eur, currency, reason, status,
            str(due_by) if due_by else None, event_id,
        )
        _wh_repo.actualizar_contacto_disputa(
            cursor, contacto_id, dispute_id, charge_id, amount_eur, reason, status,
        )
        conn.commit()
        conn.close()

    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""
    _, nuevo_val, res = _transicion_si_valida(
        db, contacto_id, EstadoFinanciero.DISPUTA_STRIPE,
        motivo=f"charge.dispute.created reason={reason}", stripe_ref=dispute_id,
    )
    db.registrar_evento_sistema(
        "stripe_disputa_creada",
        f"Disputa Stripe en contacto #{contacto_id}",
        actor_tipo="sistema",
        metadata={"contacto_id": contacto_id, "dispute_id": dispute_id, "event_id": event_id},
    )
    return contacto_id, res if inserted else "idempotent", ant_val, nuevo_val


def _handle_desconocido(
    db, obj, event_id: str
) -> Tuple[Optional[int], str, str, str]:
    return None, "ignored_unknown", "", ""


_HANDLERS = {
    "checkout.session.completed": _handle_checkout_session_completed,
    "payment_intent.succeeded": _handle_payment_intent_succeeded,
    "payment_intent.payment_failed": _handle_payment_intent_payment_failed,
    "checkout.session.expired": _handle_checkout_session_expired,
    "account.updated": _handle_account_updated,
    "transfer.created": _handle_transfer_created,
    "transfer.paid": _handle_transfer_paid,
    "transfer.failed": _handle_transfer_failed,
    "charge.refunded": _handle_charge_refunded,
    "charge.dispute.created": _handle_charge_dispute_created,
}


def _fin_repo_contacto(db, contacto_id: int) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = _fin_repo.select_contacto_financiero(cursor, contacto_id)
        conn.close()
    return dict(row) if row else {}


def _log_incidente_firma(db, mensaje: str) -> None:
    try:
        db.registrar_evento_sistema(
            "stripe_webhook_firma_invalida",
            mensaje[:500],
            actor_tipo="sistema",
        )
    except Exception:
        pass
