"""Servicio de reembolsos Stripe blindados (FASE 05)."""
from __future__ import annotations

import sqlite3
import threading
from typing import Any, Dict, Optional

from core import stripe_client
from core.financial.conflict_estados import EstadoConflicto, ResolucionConflicto, normalizar_estado_conflicto
from core.financial.estados import EstadoFinanciero
from core.financial.refund_comision import calcular_impacto_comision_refund
from core.financial.refund_estados import CausaReembolso, EstadoRefund
from core.financial.money import importe_bd_a_cents
from core.refund_authorization import REFUND_EXECUTE
from core.repositories.financial_conflict_repo import FinancialConflictRepo
from core.repositories.financial_refund_repo import FinancialRefundRepo
from core.repositories.financial_transaction_repo import FinancialTransactionRepo
from core.repositories.financial_transfer_repo import FinancialTransferRepo
from core.repositories.pago_repo import PagoRepo
from core.services import financial_conflict_service as fcs
from core.services import financial_transaction_service as fts

_pago_repo = PagoRepo()
_fin_repo = FinancialTransactionRepo()
_transfer_repo = FinancialTransferRepo()
_conflict_repo = FinancialConflictRepo()
_refund_repo = FinancialRefundRepo()

IDEMPOTENCY_PREFIX = "refund-contacto-"

_ESTADOS_TRANSFER_BLOQUEAN = frozenset({
    EstadoFinanciero.TRANSFERENCIA_ENVIADA,
    EstadoFinanciero.TRANSFERIDO,
    EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
})

_contacto_refund_locks: Dict[int, threading.Lock] = {}
_contacto_refund_locks_guard = threading.Lock()


def _lock_por_contacto(contacto_id: int) -> threading.Lock:
    with _contacto_refund_locks_guard:
        if contacto_id not in _contacto_refund_locks:
            _contacto_refund_locks[contacto_id] = threading.Lock()
        return _contacto_refund_locks[contacto_id]


def _importe_bruto_cents(contacto: Dict[str, Any]) -> int:
    return importe_bd_a_cents(contacto.get("importe_acordado") or contacto.get("importe_final"))


def _resolver_causa_desde_conflicto(conflicto: Dict[str, Any], causa_explicita: str = "") -> CausaReembolso:
    if causa_explicita:
        try:
            return CausaReembolso(causa_explicita.strip().upper())
        except ValueError:
            pass
    resolucion = (conflicto.get("resolucion") or "").strip()
    if resolucion == ResolucionConflicto.REEMBOLSAR_TOTAL.value:
        return CausaReembolso.SERVICIO_NO_INICIADO
    if resolucion == ResolucionConflicto.REEMBOLSAR_PARCIAL.value:
        return CausaReembolso.SERVICIO_PARCIAL
    return CausaReembolso.INDETERMINADO


def calcular_importe_disponible_refund_cents(db, contacto_id: int) -> Dict[str, Any]:
    from core.services import financial_dispute_service as fds

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if fds.tiene_disputa_bloqueante(db, contacto_id, cursor=cursor):
                return {
                    "status": "error",
                    "message": "Disputa Stripe abierta",
                    "bloqueo": "disputa_stripe",
                    "importe_disponible_refund_cents": 0,
                }
            row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row) if hasattr(row, "keys") else {}
            cobrado = _importe_bruto_cents(contacto)
            confirmados = _refund_repo.sum_confirmados_contacto(cursor, contacto_id)
            pendientes = _refund_repo.sum_pendientes_contacto(cursor, contacto_id)
            disponible = max(0, cobrado - confirmados - pendientes)
            return {
                "status": "success",
                "importe_cobrado_cents": cobrado,
                "importe_reembolsado_cents": confirmados,
                "importe_pendiente_cents": pendientes,
                "importe_disponible_refund_cents": disponible,
            }
        finally:
            conn.close()


def ejecutar_reembolso_desde_conflicto(
    db,
    conflicto_id: int,
    *,
    actor: str,
    idempotency_key: str,
    permiso_usado: str = REFUND_EXECUTE,
    causa_ruana: str = "",
    parte_ejecutada_cents: int = 0,
    conservar_comision_total: bool = False,
    approval_id: Optional[int] = None,
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            conflicto = _conflict_repo.select_por_id(cursor, conflicto_id)
            if not conflicto:
                return {"status": "error", "message": "Conflicto no encontrado"}
            ec = normalizar_estado_conflicto(
                conflicto.get("estado_conflicto"), conflicto.get("estado"),
            )
            if ec not in (EstadoConflicto.RESUELTO, EstadoConflicto.CERRADO):
                return {"status": "error", "message": "Conflicto no resuelto", "bloqueo": "conflicto_abierto"}
            resolucion = (conflicto.get("resolucion") or "").strip()
            if resolucion not in (
                ResolucionConflicto.REEMBOLSAR_TOTAL.value,
                ResolucionConflicto.REEMBOLSAR_PARCIAL.value,
            ):
                return {"status": "error", "message": "Resolución no permite reembolso"}
            importe = int(conflicto.get("importe_reembolsar_cents") or 0)
            if importe <= 0 and resolucion == ResolucionConflicto.REEMBOLSAR_PARCIAL.value:
                return {"status": "error", "message": "importe_reembolsar_cents inválido"}
            if resolucion == ResolucionConflicto.REEMBOLSAR_TOTAL.value and importe <= 0:
                contacto_id = int(conflicto["trabajo_id"])
                row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
                importe = _importe_bruto_cents(dict(row) if row else {})
            causa = _resolver_causa_desde_conflicto(conflicto, causa_ruana)
            contacto_id = int(conflicto["trabajo_id"])
        finally:
            conn.close()

    return ejecutar_reembolso(
        db,
        contacto_id,
        importe_solicitado_cents=importe,
        actor=actor,
        idempotency_key=idempotency_key,
        permiso_usado=permiso_usado,
        causa_ruana=causa.value,
        conflicto_id=conflicto_id,
        parte_ejecutada_cents=parte_ejecutada_cents,
        conservar_comision_total=conservar_comision_total,
        approval_id=approval_id,
    )


def ejecutar_reembolso(
    db,
    contacto_id: int,
    *,
    importe_solicitado_cents: int,
    actor: str,
    idempotency_key: str,
    permiso_usado: str = REFUND_EXECUTE,
    causa_ruana: str,
    conflicto_id: Optional[int] = None,
    parte_ejecutada_cents: int = 0,
    conservar_comision_total: bool = False,
    motivo_stripe: str = "requested_by_customer",
    approval_id: Optional[int] = None,
) -> Dict[str, Any]:
    if importe_solicitado_cents <= 0:
        return {"status": "error", "message": "importe_solicitado_cents debe ser > 0"}
    try:
        causa = CausaReembolso(causa_ruana.strip().upper())
    except ValueError:
        return {"status": "error", "message": f"causa_ruana inválida: {causa_ruana}"}
    if not CausaReembolso.permite_ejecucion(causa):
        return {"status": "error", "message": "causa indeterminada: fondos bloqueados", "bloqueo": "causa_indeterminada"}

    from core.services import financial_action_approval_service as faas
    import os
    require_approval = os.environ.get("RUANA_FINANCIAL_REQUIRE_APPROVAL", "1").strip().lower() not in ("0", "false", "no")
    if require_approval:
        if not approval_id:
            return {
                "status": "error",
                "message": "approval_id obligatorio cuando RUANA_FINANCIAL_REQUIRE_APPROVAL=1",
            }
        chk = faas.consumir_aprobacion_para_ejecucion(
            db, int(approval_id),
            actor=actor,
            action_type=faas.ACTION_REFUND_EXECUTE,
            contacto_id=contacto_id,
            importe_cents=importe_solicitado_cents,
            currency="eur",
        )
        if chk.get("status") != "success":
            return chk

    with _lock_por_contacto(contacto_id):
        return _ejecutar_reembolso_locked(
            db,
            contacto_id,
            importe_solicitado_cents=importe_solicitado_cents,
            actor=actor,
            idempotency_key=idempotency_key,
            permiso_usado=permiso_usado,
            causa=causa,
            conflicto_id=conflicto_id,
            parte_ejecutada_cents=parte_ejecutada_cents,
            conservar_comision_total=conservar_comision_total,
            motivo_stripe=motivo_stripe,
        )


def _ejecutar_reembolso_locked(
    db,
    contacto_id: int,
    *,
    importe_solicitado_cents: int,
    actor: str,
    idempotency_key: str,
    permiso_usado: str,
    causa: CausaReembolso,
    conflicto_id: Optional[int],
    parte_ejecutada_cents: int,
    conservar_comision_total: bool,
    motivo_stripe: str,
) -> Dict[str, Any]:
    key_ruana = f"{IDEMPOTENCY_PREFIX}{contacto_id}-{idempotency_key}"
    stripe_idem = key_ruana
    retry_refund_id: Optional[int] = None

    # Comprobar idempotencia antes de validar disponible
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            previo = _refund_repo.select_por_idempotency_key(cursor, key_ruana)
            if previo:
                estado_ex = (previo.get("estado") or "").upper()
                if estado_ex in (
                    EstadoRefund.SUCCEEDED.value,
                    EstadoRefund.PENDING_RECONCILIATION.value,
                    EstadoRefund.STRIPE_PROCESSING.value,
                ):
                    return {
                        "status": "success", "idempotent": True,
                        "refund_id": previo.get("id"),
                        "estado": estado_ex,
                        "stripe_refund_id": previo.get("stripe_refund_id"),
                    }
                if estado_ex in (EstadoRefund.FAILED.value, EstadoRefund.REQUESTED.value):
                    retry_refund_id = int(previo["id"])
                    if estado_ex == EstadoRefund.FAILED.value:
                        cursor.execute(
                            """
                            UPDATE financial_refunds
                            SET estado = 'REQUESTED', error_stripe = NULL, actualizado_en = CURRENT_TIMESTAMP
                            WHERE id = ? AND estado = 'FAILED'
                            """,
                            (retry_refund_id,),
                        )
                        conn.commit()
        finally:
            conn.close()

    # Fase 1: validar y crear REQUESTED (transacción corta)
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            bloquea, motivo_bloqueo = fcs.bloquea_operaciones_financieras(db, contacto_id, cursor=cursor)
            if bloquea and conflicto_id is None:
                return {"status": "error", "message": "Conflicto abierto bloquea refund", "bloqueo": motivo_bloqueo}

            if conflicto_id:
                conflicto = _conflict_repo.select_por_id(cursor, conflicto_id)
                if not conflicto:
                    return {"status": "error", "message": "Conflicto no encontrado"}
                ec = normalizar_estado_conflicto(
                    conflicto.get("estado_conflicto"), conflicto.get("estado"),
                )
                if ec not in (EstadoConflicto.RESUELTO, EstadoConflicto.CERRADO):
                    return {"status": "error", "message": "Conflicto no resuelto", "bloqueo": "conflicto_abierto"}

            fin = _fin_repo.select_contacto_financiero(cursor, contacto_id)
            if fin:
                d = dict(fin) if hasattr(fin, "keys") else {}
                ef = (d.get("estado_financiero") or "").strip().upper()
                if ef == EstadoFinanciero.DISPUTA_STRIPE.value:
                    return {"status": "error", "message": "Disputa Stripe abierta", "bloqueo": "disputa_stripe"}
                try:
                    estado_fin = EstadoFinanciero(ef) if ef else None
                except ValueError:
                    estado_fin = None
                if estado_fin in _ESTADOS_TRANSFER_BLOQUEAN:
                    return {
                        "status": "error",
                        "message": "Transferencia incompatible: acción administrativa pendiente",
                        "bloqueo": "transferencia_incompatible",
                        "accion_pendiente": True,
                    }

            row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            cobrado = _importe_bruto_cents(contacto)
            if importe_solicitado_cents > cobrado:
                return {"status": "error", "message": "importe supera cobrado"}

            exclude_id = retry_refund_id
            confirmados = _refund_repo.sum_confirmados_contacto(
                cursor, contacto_id, exclude_refund_id=exclude_id,
            )
            pendientes = _refund_repo.sum_pendientes_contacto(
                cursor, contacto_id, exclude_refund_id=exclude_id,
            )
            disponible = cobrado - confirmados - pendientes
            if importe_solicitado_cents > disponible:
                return {"status": "error", "message": "importe supera disponible para refund"}

            impacto, err_com = calcular_impacto_comision_refund(
                importe_bruto_cents=cobrado,
                causa=causa,
                parte_ejecutada_cents=parte_ejecutada_cents,
                conservar_comision_total=conservar_comision_total,
            )
            if err_com:
                return {"status": "error", "message": err_com}

            pi = str(contacto.get("stripe_payment_intent_id") or "")
            charge_id = str(contacto.get("stripe_charge_id") or "")

            claim, refund_row = _refund_repo.reclamar_refund(
                cursor,
                contacto_id=contacto_id,
                idempotency_key=key_ruana,
                importe_solicitado_cents=importe_solicitado_cents,
                moneda="eur",
                causa_ruana=causa.value,
                actor_codigo=actor,
                permiso_usado=permiso_usado,
                payment_intent_id=pi,
                charge_id=charge_id,
                conflicto_id=conflicto_id,
                comision_total_cents=impacto.comision_total_cents,
                comision_conservada_cents=impacto.comision_conservada_cents,
                comision_devuelta_cents=impacto.comision_devuelta_cents,
                parte_ejecutada_cents=impacto.parte_ejecutada_cents,
                parte_no_ejecutada_cents=impacto.parte_no_ejecutada_cents,
                motivo_stripe=motivo_stripe,
                metadata={"idempotency_key_admin": idempotency_key},
            )
            refund_id = int((refund_row or {}).get("id") or 0)
            if claim == "existing" and refund_row:
                estado_ex = (refund_row.get("estado") or "").upper()
                if estado_ex in (EstadoRefund.SUCCEEDED.value, EstadoRefund.PENDING_RECONCILIATION.value):
                    return {
                        "status": "success", "idempotent": True,
                        "refund_id": refund_id, "estado": estado_ex,
                        "stripe_refund_id": refund_row.get("stripe_refund_id"),
                    }
                if estado_ex == EstadoRefund.FAILED.value and refund_id != retry_refund_id:
                    return {"status": "error", "message": refund_row.get("error_stripe") or "refund fallido previo"}

            if not _refund_repo.intentar_stripe_processing(cursor, refund_id):
                conn.commit()
                existing = _refund_repo.select_por_id(cursor, refund_id)
                return {
                    "status": "success", "idempotent": True,
                    "refund_id": refund_id, "estado": (existing or {}).get("estado"),
                }

            _refund_repo.registrar_intento(
                cursor, refund_id, "stripe_create", actor, "en_proceso",
                {"permiso_usado": permiso_usado, "causa": causa.value},
            )
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()

    # Fase 2: llamada Stripe (sin transacción DB abierta)
    try:
        stripe_resp = stripe_client.create_refund(
            amount_cents=importe_solicitado_cents,
            payment_intent_id=pi or None,
            charge_id=charge_id or None,
            reason=motivo_stripe,
            idempotency_key=stripe_idem,
            metadata={"contacto_id": str(contacto_id), "financial_refund_id": str(refund_id)},
        )
        stripe_refund_id = str(stripe_resp.get("id") or "")
        stripe_status = str(stripe_resp.get("status") or "").lower()
        amount_conf = int(stripe_resp.get("amount") or importe_solicitado_cents)
        estado_final = (
            EstadoRefund.SUCCEEDED.value if stripe_status == "succeeded"
            else EstadoRefund.PENDING_RECONCILIATION.value
        )
        err_msg = ""
    except Exception as e:
        stripe_refund_id = ""
        stripe_status = "failed"
        amount_conf = 0
        estado_final = EstadoRefund.FAILED.value
        err_msg = str(e)

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if estado_final == EstadoRefund.FAILED.value:
                _refund_repo.marcar_stripe_resultado(
                    cursor, refund_id,
                    stripe_refund_id="", estado=estado_final, error_stripe=err_msg,
                )
                _refund_repo.registrar_intento(cursor, refund_id, "stripe_create", actor, "failed", {"error": err_msg})
                conn.commit()
                return {"status": "error", "message": err_msg, "refund_id": refund_id, "estado": estado_final}

            _refund_repo.marcar_stripe_resultado(
                cursor, refund_id,
                stripe_refund_id=stripe_refund_id,
                estado=estado_final,
                importe_confirmado_cents=amount_conf if stripe_status == "succeeded" else 0,
            )
            _refund_repo.registrar_intento(
                cursor, refund_id, "stripe_create", actor, "ok",
                {"stripe_refund_id": stripe_refund_id, "status": stripe_status},
            )
            if stripe_status == "succeeded":
                estado_fin = fts.obtener_estado_financiero(db, contacto_id)
                if estado_fin and estado_fin not in (EstadoFinanciero.REEMBOLSADO,):
                    es_total = amount_conf >= cobrado
                    objetivo = EstadoFinanciero.REEMBOLSADO if es_total else EstadoFinanciero.REEMBOLSO_PENDIENTE
                    try:
                        fts.transicionar(db, contacto_id, objetivo, actor_tipo="refund", actor_codigo=actor,
                                         motivo=f"refund {stripe_refund_id}")
                    except Exception:
                        pass
            conn.commit()
            if stripe_status == "succeeded":
                from core.services.financial_ledger_hooks import on_refund_succeeded
                on_refund_succeeded(
                    db,
                    contacto_id=contacto_id,
                    refund_id=stripe_refund_id,
                    importe_cents=amount_conf,
                    comision_devuelta_cents=int(impacto.comision_devuelta_cents or 0),
                    idempotency_key=stripe_idem,
                )
            return {
                "status": "success",
                "refund_id": refund_id,
                "stripe_refund_id": stripe_refund_id,
                "estado": estado_final,
                "importe_confirmado_cents": amount_conf,
                "comision": {
                    "total": impacto.comision_total_cents,
                    "conservada": impacto.comision_conservada_cents,
                    "devuelta": impacto.comision_devuelta_cents,
                },
            }
        finally:
            conn.close()


def procesar_webhook_refund(
    db,
    *,
    stripe_refund_id: str,
    amount_cents: int,
    status: str,
    charge_id: str = "",
    payment_intent_id: str = "",
    event_id: str = "",
) -> Dict[str, Any]:
    """Actualiza financial_refunds desde webhook (no crea nuevo refund)."""
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _refund_repo.select_por_stripe_refund_id(cursor, stripe_refund_id)
            if not row and payment_intent_id:
                cursor.execute(
                    """
                    SELECT * FROM financial_refunds
                    WHERE payment_intent_id = ? AND stripe_refund_id IS NULL
                    ORDER BY id DESC LIMIT 1
                    """,
                    (payment_intent_id,),
                )
                r = cursor.fetchone()
                row = _refund_repo._row_dict(r, cursor) if r else None
            if not row:
                return {"status": "error", "message": "refund RUANA no encontrado", "missing_ruana": True}

            refund_id = int(row["id"])
            solicitado = int(row.get("importe_solicitado_cents") or 0)
            if amount_cents and solicitado and amount_cents != solicitado:
                return {
                    "status": "error", "message": "importe webhook diferente",
                    "discrepancia": "REFUND_AMOUNT_MISMATCH", "refund_id": refund_id,
                }

            estado = (
                EstadoRefund.SUCCEEDED.value if status == "succeeded"
                else EstadoRefund.FAILED.value if status == "failed"
                else EstadoRefund.PENDING_RECONCILIATION.value
            )
            _refund_repo.marcar_stripe_resultado(
                cursor, refund_id,
                stripe_refund_id=stripe_refund_id,
                estado=estado,
                importe_confirmado_cents=amount_cents,
            )
            _refund_repo.registrar_intento(
                cursor, refund_id, "webhook", "sistema", "ok",
                {"event_id": event_id, "status": status},
            )
            conn.commit()
            return {"status": "success", "refund_id": refund_id, "estado": estado}
        finally:
            conn.close()
