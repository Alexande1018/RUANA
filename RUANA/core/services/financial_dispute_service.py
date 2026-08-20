"""Servicio de disputas Stripe formales (FASE 06)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from core import stripe_client
from core.dispute_authorization import (
    DISPUTE_ADD_EVIDENCE,
    DISPUTE_INVESTIGATE,
    DISPUTE_SUBMIT_EVIDENCE,
)
from core.financial.discrepancia import TipoDiscrepancia
from core.financial.money import importe_bd_a_cents
from core.financial.dispute_estados import (
    EstadoDisputa,
    TipoEvidenciaDisputa,
    mapear_estado_stripe,
    puede_transicionar,
)
from core.financial.dispute_reconciliation import (
    DecisionReconciliacionDispute,
    evaluar_reconciliacion_dispute,
    extraer_snapshot_dispute_stripe,
)
from core.financial.estados import EstadoFinanciero
from core.financial.state_machine import FinancialStateMachine
from core.repositories.financial_dispute_repo import FinancialDisputeRepo
from core.repositories.financial_refund_repo import FinancialRefundRepo
from core.repositories.financial_transaction_repo import FinancialTransactionRepo
from core.repositories.stripe_webhook_repo import StripeWebhookRepo
from core.services import financial_reconciliation_service as reconciliation
from core.services import financial_transaction_service as fts

_dispute_repo = FinancialDisputeRepo()
_fin_repo = FinancialTransactionRepo()
_refund_repo = FinancialRefundRepo()
_wh_repo = StripeWebhookRepo()
_sm = FinancialStateMachine()

_dispute_locks: Dict[int, threading.Lock] = {}
_dispute_locks_guard = threading.Lock()

_ESTADOS_HISTORICOS_PRESERVAR = frozenset({
    EstadoFinanciero.TRANSFERIDO,
    EstadoFinanciero.TRANSFERENCIA_ENVIADA,
    EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
})


def _lock_por_contacto(contacto_id: int) -> threading.Lock:
    with _dispute_locks_guard:
        if contacto_id not in _dispute_locks:
            _dispute_locks[contacto_id] = threading.Lock()
        return _dispute_locks[contacto_id]


def tiene_disputa_bloqueante(db, contacto_id: int, cursor=None) -> bool:
    if cursor is not None:
        if _dispute_repo.tiene_disputa_bloqueante(cursor, contacto_id):
            return True
        fin = _fin_repo.select_contacto_financiero(cursor, contacto_id)
        if fin:
            d = dict(fin) if hasattr(fin, "keys") else {}
            ef = (d.get("estado_financiero") or "").strip().upper()
            if ef == EstadoFinanciero.DISPUTA_STRIPE.value:
                return True
        return False
    with db._lock:
        conn = db._connect()
        try:
            cur = conn.cursor()
            return tiene_disputa_bloqueante(db, contacto_id, cursor=cur)
        finally:
            conn.close()


def bloquea_operaciones(db, contacto_id: int, cursor=None) -> Tuple[bool, str]:
    if tiene_disputa_bloqueante(db, contacto_id, cursor=cursor):
        return True, "disputa_stripe_abierta"
    return False, ""


def _extraer_snapshot(obj: Any) -> Dict[str, Any]:
    snap = extraer_snapshot_dispute_stripe(obj)
    evidence = _get(obj, "evidence_details") or {}
    if isinstance(evidence, dict):
        snap["has_evidence"] = bool(evidence.get("has_evidence"))
        snap["submission_count"] = int(evidence.get("submission_count") or 0)
    return snap


def _get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    val = getattr(obj, key, None)
    return val if val is not None else default


def _funds_from_balance(obj: Any) -> Tuple[int, int]:
  withdrawn = 0
  reinstated = 0
  for key in ("balance_transactions",):
      txs = _get(obj, key) or []
      if not isinstance(txs, list):
          continue
      for tx in txs:
          amount = int(_get(tx, "amount") or 0)
          if amount < 0:
              withdrawn += abs(amount)
          elif amount > 0:
              reinstated += amount
  return withdrawn, reinstated


def procesar_webhook_dispute(
    db,
    obj: Any,
    *,
    event_type: str,
    event_id: str = "",
) -> Dict[str, Any]:
    """Punto único para charge.dispute.created|updated|closed."""
    snap = _extraer_snapshot(obj)
    stripe_dispute_id = snap.get("id") or ""
    if not stripe_dispute_id:
        return {"status": "error", "message": "stripe_dispute_id vacío"}

    payment_intent_id = snap.get("payment_intent") or ""
    charge_id = snap.get("charge") or ""
    contacto_id = _resolver_contacto(db, payment_intent_id, charge_id)
    if not contacto_id:
        return {"status": "error", "message": "contacto_no_encontrado", "missing_contacto": True}

    with _lock_por_contacto(contacto_id):
        if event_type == "charge.dispute.created":
            return _procesar_created(db, contacto_id, obj, snap, event_id)
        if event_type == "charge.dispute.updated":
            return _procesar_updated(db, contacto_id, obj, snap, event_id)
        if event_type == "charge.dispute.closed":
            return _procesar_closed(db, contacto_id, obj, snap, event_id)
        return {"status": "error", "message": f"evento no soportado: {event_type}"}


def _resolver_contacto(db, payment_intent_id: str, charge_id: str) -> Optional[int]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if payment_intent_id:
                row = _wh_repo.select_contacto_por_payment_intent(cursor, payment_intent_id)
                if row:
                    return int(row[0] if not hasattr(row, "keys") else row["id"])
            if charge_id:
                cursor.execute(
                    "SELECT id FROM contactos_ruana WHERE stripe_charge_id = ? LIMIT 1",
                    (charge_id,),
                )
                r = cursor.fetchone()
                if r:
                    return int(r[0] if not hasattr(r, "keys") else r["id"])
        finally:
            conn.close()
    return None


def _procesar_created(
    db, contacto_id: int, obj: Any, snap: Dict[str, Any], event_id: str,
) -> Dict[str, Any]:
    stripe_dispute_id = snap["id"]
    key = f"dispute-{contacto_id}-{stripe_dispute_id}"
    amount_cents = int(snap.get("amount") or 0)
    due_raw = snap.get("evidence_due_by")
    due_str = str(due_raw) if due_raw else None

    estado_fin = fts.obtener_estado_financiero(db, contacto_id)
    historico = estado_fin.value if estado_fin in _ESTADOS_HISTORICOS_PRESERVAR else ""

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            claim, row = _dispute_repo.reclamar_disputa(
                cursor,
                contacto_id=contacto_id,
                stripe_dispute_id=stripe_dispute_id,
                charge_id=snap.get("charge") or "",
                payment_intent_id=snap.get("payment_intent") or "",
                amount_cents=amount_cents,
                currency=snap.get("currency") or "eur",
                reason=snap.get("reason") or "",
                status_stripe=snap.get("status") or "needs_response",
                evidence_due_by=due_str,
                network_reason_code=snap.get("network_reason_code") or "",
                balance_transaction_id=snap.get("balance_transaction") or "",
                idempotency_key=key,
                estado_financiero_historico=historico,
                metadata={"event_id": event_id, "event_type": "charge.dispute.created"},
            )
            dispute_id = int((row or {}).get("id") or 0)
            if claim == "existing":
                _dispute_repo.registrar_intento(
                    cursor, dispute_id, "webhook_created", "sistema", "idempotent",
                    metadata={"event_id": event_id},
                )
                conn.commit()
                return {"status": "success", "idempotent": True, "dispute_id": dispute_id, "contacto_id": contacto_id}

            amount_eur = round(amount_cents / 100.0, 2)
            _wh_repo.insertar_disputa(
                cursor, contacto_id, stripe_dispute_id, snap.get("charge") or "",
                amount_eur, snap.get("currency") or "eur", snap.get("reason") or "",
                snap.get("status") or "needs_response", due_str, event_id,
            )
            _wh_repo.actualizar_contacto_disputa(
                cursor, contacto_id, stripe_dispute_id, snap.get("charge") or "",
                amount_eur, snap.get("reason") or "", snap.get("status") or "",
            )
            _dispute_repo.vincular_stripe_disputes_audit(cursor, stripe_dispute_id, dispute_id)
            _dispute_repo.registrar_intento(
                cursor, dispute_id, "webhook_created", "sistema", "ok",
                metadata={"event_id": event_id},
            )
            conn.commit()
        finally:
            conn.close()

    from core.services.financial_ledger_hooks import on_disputa_creada
    on_disputa_creada(
        db,
        contacto_id=contacto_id,
        dispute_id=stripe_dispute_id,
        importe_cents=amount_cents,
        event_id=event_id,
    )

    alerta_transfer = estado_fin in (
        EstadoFinanciero.TRANSFERENCIA_ENVIADA,
        EstadoFinanciero.TRANSFERIDO,
        EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
    )
    refund_previo = _tiene_refund_previo(db, contacto_id)

    if historico:
        _alerta_critica(
            db, contacto_id, dispute_id,
            f"Disputa Stripe tras {historico}: fondos en riesgo, historia preservada",
            metadata={"estado_historico": historico, "stripe_dispute_id": stripe_dispute_id},
        )
    elif alerta_transfer:
        _alerta_critica(
            db, contacto_id, dispute_id,
            "Disputa Stripe durante transferencia en curso",
            metadata={"estado_financiero": estado_fin.value if estado_fin else ""},
        )
    if refund_previo:
        _alerta_critica(
            db, contacto_id, dispute_id,
            "Disputa Stripe con refund previo ejecutado — reconciliar manualmente",
            metadata={"refund_previo": True},
        )

    if not historico and estado_fin and _sm.puede_transicionar(estado_fin, EstadoFinanciero.DISPUTA_STRIPE):
        fts.transicionar(
            db, contacto_id, EstadoFinanciero.DISPUTA_STRIPE,
            actor_tipo="webhook", actor_codigo="sistema",
            motivo=f"charge.dispute.created {stripe_dispute_id}",
        )

    db.registrar_evento_sistema(
        "stripe_disputa_creada",
        f"Disputa Stripe #{dispute_id} en contacto #{contacto_id}",
        actor_tipo="sistema",
        metadata={"contacto_id": contacto_id, "dispute_id": dispute_id, "event_id": event_id},
    )
    return {
        "status": "success", "dispute_id": dispute_id, "contacto_id": contacto_id,
        "historico_preservado": bool(historico),
    }


def _procesar_updated(
    db, contacto_id: int, obj: Any, snap: Dict[str, Any], event_id: str,
) -> Dict[str, Any]:
    stripe_dispute_id = snap["id"]
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _dispute_repo.select_por_stripe_dispute_id(cursor, stripe_dispute_id)
            if not row:
                conn.commit()
                return {"status": "error", "message": "dispute RUANA no encontrada", "missing_ruana": True}
            dispute_id = int(row["id"])
            due_raw = snap.get("evidence_due_by")
            _dispute_repo.actualizar_snapshot_stripe(
                cursor, dispute_id,
                status_stripe=snap.get("status") or "",
                reason=snap.get("reason") or "",
                evidence_due_by=str(due_raw) if due_raw else None,
                has_evidence=bool(snap.get("has_evidence")),
                evidence_submitted=int(snap.get("submission_count") or 0) > 0,
                network_reason_code=snap.get("network_reason_code") or "",
                balance_transaction_id=snap.get("balance_transaction") or "",
            )
            estado_sugerido = mapear_estado_stripe(snap.get("status") or "")
            if estado_sugerido:
                actual = EstadoDisputa((row.get("estado_interno") or "ABIERTO").upper())
                if puede_transicionar(actual, estado_sugerido):
                    _dispute_repo.transicionar_estado(cursor, dispute_id, estado_nuevo=estado_sugerido.value)
            _dispute_repo.registrar_intento(
                cursor, dispute_id, "webhook_updated", "sistema", "ok",
                metadata={"event_id": event_id},
            )
            conn.commit()
        finally:
            conn.close()

    cobrado = _importe_cobrado_cents(db, contacto_id)
    decision, motivo = evaluar_reconciliacion_dispute(
        financial_dispute=row, stripe_snapshot=snap, importe_cobrado_cents=cobrado,
    )
    if decision == DecisionReconciliacionDispute.MISMATCH:
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.DISPUTE_AMOUNT_MISMATCH,
            stripe_payment_intent_id=snap.get("payment_intent") or "",
            metadata={"motivo": motivo, "stripe_dispute_id": stripe_dispute_id},
        )
        return {"status": "error", "discrepancia": motivo, "dispute_id": dispute_id}

    return {"status": "success", "dispute_id": dispute_id, "contacto_id": contacto_id}


def _procesar_closed(
    db, contacto_id: int, obj: Any, snap: Dict[str, Any], event_id: str,
) -> Dict[str, Any]:
    stripe_dispute_id = snap["id"]
    status = (snap.get("status") or "").lower()
    withdrawn, reinstated = _funds_from_balance(obj)

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _dispute_repo.select_por_stripe_dispute_id(cursor, stripe_dispute_id)
            if not row:
                return {"status": "error", "message": "dispute RUANA no encontrada", "missing_ruana": True}
            dispute_id = int(row["id"])
            if status == "won":
                estado_final = EstadoDisputa.GANADA.value
                resolution = "won"
            elif status == "lost":
                estado_final = EstadoDisputa.PERDIDA.value
                resolution = "lost"
            else:
                estado_final = EstadoDisputa.CERRADA.value
                resolution = status or "closed"

            _dispute_repo.actualizar_snapshot_stripe(
                cursor, dispute_id,
                status_stripe=status,
                funds_withdrawn_cents=withdrawn,
                funds_reinstated_cents=reinstated,
            )
            _dispute_repo.cerrar_disputa(
                cursor, dispute_id,
                estado_interno=estado_final,
                resolution=resolution,
                resolution_reason=status,
                bloqueo_financiero=False,
            )
            _dispute_repo.registrar_intento(
                cursor, dispute_id, "webhook_closed", "sistema", "ok",
                metadata={"event_id": event_id, "status": status},
            )
            conn.commit()
        finally:
            conn.close()

    from core.services.financial_ledger_hooks import on_disputa_cerrada
    on_disputa_cerrada(
        db,
        contacto_id=contacto_id,
        dispute_id=stripe_dispute_id,
        status=status,
        importe_perdido_cents=withdrawn if status == "lost" else 0,
        importe_reinstated_cents=reinstated if status == "won" else 0,
        event_id=event_id,
    )

    if status == "lost":
        _alerta_critica(
            db, contacto_id, dispute_id,
            "Disputa Stripe perdida — revisión administrativa requerida",
            metadata={"stripe_dispute_id": stripe_dispute_id},
        )

    return {
        "status": "success", "dispute_id": dispute_id, "contacto_id": contacto_id,
        "estado_final": estado_final, "resolution": resolution,
    }


def transicionar_estado_interno(
    db,
    dispute_id: int,
    *,
    estado_nuevo: str,
    actor: str,
    permiso_usado: str = DISPUTE_INVESTIGATE,
) -> Dict[str, Any]:
    try:
        destino = EstadoDisputa(estado_nuevo.strip().upper())
    except ValueError:
        return {"status": "error", "message": f"estado inválido: {estado_nuevo}"}

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _dispute_repo.select_por_id(cursor, dispute_id)
            if not row:
                return {"status": "error", "message": "Disputa no encontrada"}
            actual = EstadoDisputa((row.get("estado_interno") or "ABIERTO").upper())
            if not puede_transicionar(actual, destino):
                return {"status": "error", "message": f"transición no permitida: {actual.value} → {destino.value}"}
            if not _dispute_repo.transicionar_estado(
                cursor, dispute_id, estado_nuevo=destino.value, estado_actual_esperado=actual.value,
            ):
                return {"status": "error", "message": "concurrencia en transición"}
            _dispute_repo.registrar_intento(
                cursor, dispute_id, "transicion", actor, "ok",
                permiso_usado=permiso_usado,
                metadata={"desde": actual.value, "hasta": destino.value},
            )
            conn.commit()
            return {"status": "success", "estado_interno": destino.value}
        finally:
            conn.close()


def agregar_evidencia(
    db,
    dispute_id: int,
    *,
    tipo: str,
    referencia: str,
    actor: str,
    permiso_usado: str = DISPUTE_ADD_EVIDENCE,
    metadata: Optional[Dict] = None,
) -> Dict[str, Any]:
    try:
        TipoEvidenciaDisputa(tipo.strip().lower())
    except ValueError:
        return {"status": "error", "message": f"tipo evidencia inválido: {tipo}"}

    content_hash = hashlib.sha256((referencia or "").encode()).hexdigest()[:64]
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _dispute_repo.select_por_id(cursor, dispute_id)
            if not row:
                return {"status": "error", "message": "Disputa no encontrada"}
            if EstadoDisputa.es_terminal(EstadoDisputa((row.get("estado_interno") or "").upper())):
                return {"status": "error", "message": "disputa cerrada"}
            ev_id = _dispute_repo.insertar_evidencia(
                cursor, dispute_id=dispute_id, tipo=tipo.strip().lower(),
                referencia=referencia, content_hash=content_hash,
                autor_codigo=actor, metadata=metadata,
            )
            _dispute_repo.actualizar_snapshot_stripe(cursor, dispute_id, has_evidence=True)
            _dispute_repo.registrar_intento(
                cursor, dispute_id, "add_evidence", actor, "ok",
                permiso_usado=permiso_usado, metadata={"evidence_id": ev_id, "tipo": tipo},
            )
            conn.commit()
            return {"status": "success", "evidence_id": ev_id}
        finally:
            conn.close()


def enviar_evidencia_stripe(
    db,
    dispute_id: int,
    *,
    actor: str,
    permiso_usado: str = DISPUTE_SUBMIT_EVIDENCE,
    evidence_payload: Optional[Dict[str, str]] = None,
    idempotency_key: str = "",
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _dispute_repo.select_por_id(cursor, dispute_id)
            if not row:
                return {"status": "error", "message": "Disputa no encontrada"}
            if row.get("evidence_submitted"):
                return {"status": "success", "idempotent": True, "message": "evidencia ya enviada"}
            if _dispute_repo.deadline_expirado(row.get("evidence_due_by")):
                return {"status": "error", "message": "deadline de evidencia expirado", "bloqueo": "deadline"}
            if not _dispute_repo.intentar_envio_evidencia(cursor, dispute_id):
                return {"status": "error", "message": "envío concurrente en curso"}
            stripe_dispute_id = row.get("stripe_dispute_id") or ""
            conn.commit()
        finally:
            conn.close()

    payload = {k: v for k, v in (evidence_payload or {}).items() if v and k != "card_number"}
    try:
        stripe_client.update_dispute_evidence(
            stripe_dispute_id,
            evidence=payload,
            idempotency_key=idempotency_key or f"dispute-evidence-{dispute_id}",
        )
        stripe_client.submit_dispute_evidence(stripe_dispute_id)
        stripe_ok = True
        err = ""
    except Exception as e:
        stripe_ok = False
        err = str(e)
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE financial_disputes SET evidence_submitted = 0 WHERE id = ?",
                    (dispute_id,),
                )
                conn.commit()
            finally:
                conn.close()
        return {"status": "error", "message": err}

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            evidencias = _dispute_repo.listar_evidencias(cursor, dispute_id)
            for ev in evidencias:
                if not ev.get("enviada_a_stripe"):
                    _dispute_repo.marcar_evidencia_enviada(cursor, int(ev["id"]))
            actual = EstadoDisputa((row.get("estado_interno") or "ABIERTO").upper())
            if puede_transicionar(actual, EstadoDisputa.EVIDENCIA_ENVIADA):
                _dispute_repo.transicionar_estado(
                    cursor, dispute_id, estado_nuevo=EstadoDisputa.EVIDENCIA_ENVIADA.value,
                )
            _dispute_repo.registrar_intento(
                cursor, dispute_id, "submit_evidence", actor,
                "ok" if stripe_ok else "failed",
                permiso_usado=permiso_usado,
                metadata={"payload_keys": list(payload.keys())},
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "success", "stripe_submitted": True}


def vincular_conflicto(db, dispute_id: int, conflicto_id: int, *, actor: str) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if not _dispute_repo.select_por_id(cursor, dispute_id):
                return {"status": "error", "message": "Disputa no encontrada"}
            _dispute_repo.vincular_conflicto(cursor, dispute_id, conflicto_id)
            _dispute_repo.registrar_intento(
                cursor, dispute_id, "vincular_conflicto", actor, "ok",
                metadata={"conflicto_id": conflicto_id},
            )
            conn.commit()
            return {"status": "success", "conflicto_id": conflicto_id}
        finally:
            conn.close()


def obtener_disputa(db, dispute_id: int) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            row = _dispute_repo.select_por_id(cursor, dispute_id)
            if not row:
                return {"status": "error", "message": "Disputa no encontrada"}
            evidencias = _dispute_repo.listar_evidencias(cursor, dispute_id)
            return {"status": "success", "dispute": row, "evidencias": evidencias}
        finally:
            conn.close()


def listar_por_contacto(db, contacto_id: int) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            rows = _dispute_repo.listar_por_contacto(cursor, contacto_id)
            return {"status": "success", "disputes": rows}
        finally:
            conn.close()


def _importe_cobrado_cents(db, contacto_id: int) -> int:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _fin_repo.select_contacto_financiero(cursor, contacto_id)
            if not row:
                return 0
            d = dict(row)
            return importe_bd_a_cents(d.get("importe_acordado") or d.get("importe_final"))
        finally:
            conn.close()


def _tiene_refund_previo(db, contacto_id: int) -> bool:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if not _refund_repo.tabla_existe(cursor):
                return False
            cursor.execute(
                """
                SELECT 1 FROM financial_refunds
                WHERE contacto_id = ? AND estado IN ('SUCCEEDED', 'PENDING_RECONCILIATION')
                LIMIT 1
                """,
                (contacto_id,),
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()


def _alerta_critica(db, contacto_id: int, dispute_id: int, mensaje: str, metadata: Optional[Dict] = None) -> None:
    try:
        db.registrar_evento_sistema(
            "disputa_stripe_alerta_critica",
            mensaje[:500],
            actor_tipo="sistema",
            metadata={"contacto_id": contacto_id, "dispute_id": dispute_id, **(metadata or {})},
        )
    except Exception:
        pass
