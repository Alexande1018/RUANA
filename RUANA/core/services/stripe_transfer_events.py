"""Eventos Stripe Connect para transferencias — reconciliación explícita (FASE 03.2).

transfer.created confirma creación en Stripe → TRANSFERENCIA_ENVIADA + snapshot.
TRANSFERIDO solo tras evaluación explícita ``confirmed`` (ver transfer_reconciliation.py).

Legacy (no configurar en endpoint moderno):
- transfer.paid → alias de confirmación legacy
- transfer.failed → fallos síncronos en API moderna
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional, Tuple

from core.financial.discrepancia import TipoDiscrepancia
from core.financial.estados import EstadoFinanciero, EstadoTransferencia
from core.financial.transfer_reconciliation import (
    DecisionReconciliacionTransfer,
    comparar_snapshots,
    evaluar_reconciliacion_transfer,
    extraer_snapshot_stripe,
)
from core.financial.state_machine import FinancialStateMachine
from core.repositories.financial_transaction_repo import FinancialTransactionRepo
from core.repositories.financial_transfer_repo import FinancialTransferRepo
from core.services import financial_reconciliation_service as reconciliation
from core.services import financial_transaction_service as fts
from core.services import financial_transfer_service as transfer_svc

_fin_repo = FinancialTransactionRepo()
_transfer_repo = FinancialTransferRepo()
_sm = FinancialStateMachine()

_EVENTOS_LEGACY = frozenset({"transfer.paid", "transfer.failed"})


def es_evento_legacy(event_type: str) -> bool:
    return event_type in _EVENTOS_LEGACY


def procesar_transfer_created(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_type: str,
    event_id: str,
) -> Tuple[str, str, str]:
    return _procesar_evento_transfer(
        db, contacto_id, transfer_id, obj,
        event_type=event_type, event_id=event_id, legacy_confirmacion=False,
    )


def procesar_transfer_paid_legacy(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_id: str,
) -> Tuple[str, str, str]:
    return _procesar_evento_transfer(
        db, contacto_id, transfer_id, obj,
        event_type="transfer.paid", event_id=event_id, legacy_confirmacion=True,
    )


def sincronizar_transfer_actualizada(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_id: str,
) -> Tuple[str, str, str]:
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""
    snapshot = extraer_snapshot_stripe(obj)

    anterior = _cargar_ultimo_snapshot(db, contacto_id)
    _persistir_snapshot(db, contacto_id, transfer_id, snapshot, event_id, "transfer.updated")
    _persistir_referencias_stripe(db, contacto_id, transfer_id, obj)

    if anterior:
        cambio = comparar_snapshots(anterior, snapshot)
        if cambio:
            tipo = {
                "amount": TipoDiscrepancia.AMOUNT_MISMATCH,
                "currency": TipoDiscrepancia.CURRENCY_MISMATCH,
                "destination": TipoDiscrepancia.TRANSFER_ID_MISMATCH,
            }.get(cambio, TipoDiscrepancia.STATUS_MISMATCH)
            reconciliation.registrar_discrepancia(
                db, contacto_id, tipo,
                stripe_transfer_id=transfer_id,
                ruana_estado=ant_val,
                stripe_estado=f"transfer.updated:{cambio}",
                metadata={"event_id": event_id, "anterior": anterior, "nuevo": snapshot},
            )
            return f"discrepancia_{cambio}", ant_val, ant_val

    if snapshot.get("reversed"):
        return manejar_reversion_transfer(
            db, contacto_id, transfer_id, obj, event_id=event_id, event_type="transfer.updated",
        )

    decision, motivo, _resultado = _evaluar_y_aplicar(
        db, contacto_id, transfer_id, snapshot, estado,
        event_type="transfer.updated", event_id=event_id, legacy_confirmacion=False,
    )
    nuevo = fts.obtener_estado_financiero(db, contacto_id)
    nuevo_val = nuevo.value if nuevo else ant_val
    return f"sync_{decision.value}", ant_val, nuevo_val


def manejar_reversion_transfer(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_id: str,
    event_type: str,
) -> Tuple[str, str, str]:
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""
    snapshot = extraer_snapshot_stripe(obj)

    _persistir_snapshot(db, contacto_id, transfer_id, snapshot, event_id, event_type)
    _persistir_referencias_stripe(db, contacto_id, transfer_id, obj)
    _marcar_bloqueada(db, contacto_id)

    if estado == EstadoFinanciero.TRANSFERENCIA_REVERTIDA:
        return "idempotent", ant_val, ant_val

    era_transferido = estado == EstadoFinanciero.TRANSFERIDO

    if era_transferido:
        try:
            db.registrar_evento_sistema(
                "transfer_reversion_critica",
                f"ALERTA CRÍTICA: transferencia revertida tras TRANSFERIDO en contacto #{contacto_id}",
                actor_tipo="sistema",
                metadata={
                    "contacto_id": contacto_id,
                    "transfer_id": transfer_id,
                    "event_id": event_id,
                    "event_type": event_type,
                    "nota": "Score/notificación previos no se revierten automáticamente; revisión administrativa",
                },
            )
        except Exception:
            pass
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
            stripe_transfer_id=transfer_id,
            ruana_estado=ant_val,
            stripe_estado="reversed",
            metadata={"event_id": event_id, "critico": True},
        )

    if _sm.puede_transicionar(estado or EstadoFinanciero.TRANSFERENCIA_ENVIADA, EstadoFinanciero.TRANSFERENCIA_REVERTIDA):
        res = fts.transicionar(
            db, contacto_id, EstadoFinanciero.TRANSFERENCIA_REVERTIDA,
            actor_tipo="stripe_webhook", motivo=event_type, stripe_ref=transfer_id,
        )
        if res.get("status") == "success":
            with db._lock:
                conn = db._connect()
                cursor = conn.cursor()
                _fin_repo.actualizar_solo_estado_transferencia(
                    cursor, contacto_id, EstadoTransferencia.REVERTIDA.value
                )
                _transfer_repo.marcar_reconciliacion(
                    cursor, contacto_id, DecisionReconciliacionTransfer.REVERSED.value,
                )
                conn.commit()
                conn.close()
            return "ok", ant_val, EstadoFinanciero.TRANSFERENCIA_REVERTIDA.value

    reconciliation.registrar_discrepancia(
        db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
        stripe_transfer_id=transfer_id,
        ruana_estado=ant_val,
        stripe_estado="reversed",
        metadata={"event_id": event_id, "nota": "reversión sin transición permitida"},
    )
    return "discrepancia_registrada", ant_val, ant_val


def manejar_transfer_failed_legacy(
    db,
    contacto_id: int,
    transfer_id: str,
    *,
    event_id: str,
    estado_terminal: bool,
    ant_val: str,
) -> Tuple[str, str, str]:
    db.registrar_evento_sistema(
        "stripe_transfer_failed_legacy",
        f"Evento legacy transfer.failed en contacto #{contacto_id} (no usar en API moderna)",
        actor_tipo="sistema",
        metadata={"contacto_id": contacto_id, "transfer_id": transfer_id, "event_id": event_id},
    )
    if estado_terminal:
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
            stripe_transfer_id=transfer_id,
            ruana_estado=ant_val,
            stripe_estado="failed",
            metadata={"event_id": event_id, "legacy": True},
        )
        return "discrepancia_registrada", ant_val, ant_val

    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _fin_repo.actualizar_solo_estado_transferencia(
            cursor, contacto_id, EstadoTransferencia.FALLIDA.value
        )
        conn.commit()
        conn.close()

    estado = fts.obtener_estado_financiero(db, contacto_id)
    if estado == EstadoFinanciero.TRANSFERENCIA_FALLIDA:
        return "idempotent", ant_val, ant_val
    res = fts.transicionar(
        db, contacto_id, EstadoFinanciero.TRANSFERENCIA_FALLIDA,
        actor_tipo="stripe_webhook", motivo="transfer.failed (legacy)", stripe_ref=transfer_id,
    )
    nuevo = res.get("estado_nuevo", ant_val) if res.get("status") == "success" else ant_val
    return res.get("status", "error"), ant_val, nuevo


def evaluar_reconciliacion_contacto(
    db, contacto_id: int, stripe_snapshot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """API pública: decisión explícita confirmed/pending/reversed/mismatch."""
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ft = _cargar_financial_transfer(db, contacto_id)
    snap: Dict[str, Any] = dict(stripe_snapshot) if stripe_snapshot else {}
    if not snap and ft and ft.get("stripe_snapshot_json"):
        try:
            snap = json.loads(ft["stripe_snapshot_json"])
        except (json.JSONDecodeError, TypeError):
            snap = {}
    if not snap.get("id") and ft and ft.get("stripe_transfer_id"):
        snap.setdefault("id", ft["stripe_transfer_id"])
        snap.setdefault("amount", ft.get("amount_cents"))
        snap.setdefault("currency", ft.get("currency") or "eur")
        snap.setdefault("destination", ft.get("destination_account_id") or "")
        snap.setdefault("balance_transaction", ft.get("stripe_balance_transaction_id") or "")
        snap.setdefault("destination_payment", ft.get("stripe_destination_payment_id") or "")
    decision, motivo = evaluar_reconciliacion_transfer(
        contacto_id=contacto_id,
        estado_financiero=estado,
        financial_transfer=ft,
        stripe_snapshot=snap,
        conflicto_abierto=_conflicto_bloquea(db, contacto_id),
    )
    return {
        "status": "success",
        "decision": decision.value,
        "motivo": motivo,
        "estado_financiero": estado.value if estado else None,
    }


def _procesar_evento_transfer(
    db,
    contacto_id: int,
    transfer_id: str,
    obj: Any,
    *,
    event_type: str,
    event_id: str,
    legacy_confirmacion: bool,
) -> Tuple[str, str, str]:
    estado = fts.obtener_estado_financiero(db, contacto_id)
    ant_val = estado.value if estado else ""
    snapshot = extraer_snapshot_stripe(obj)

    if snapshot.get("reversed"):
        return manejar_reversion_transfer(
            db, contacto_id, transfer_id, obj, event_id=event_id, event_type=event_type,
        )

    _persistir_snapshot(db, contacto_id, transfer_id, snapshot, event_id, event_type)
    _persistir_referencias_stripe(db, contacto_id, transfer_id, obj)
    _avanzar_hasta_enviada(db, contacto_id, transfer_id, event_type)

    decision, motivo, resultado = _evaluar_y_aplicar(
        db, contacto_id, transfer_id, snapshot, estado,
        event_type=event_type, event_id=event_id, legacy_confirmacion=legacy_confirmacion,
    )
    nuevo = fts.obtener_estado_financiero(db, contacto_id)
    nuevo_val = nuevo.value if nuevo else ant_val
    if legacy_confirmacion and resultado == "ok":
        resultado = "ok_legacy_alias"
    return resultado, ant_val, nuevo_val


def _evaluar_y_aplicar(
    db,
    contacto_id: int,
    transfer_id: str,
    snapshot: Dict[str, Any],
    estado: Optional[EstadoFinanciero],
    *,
    event_type: str,
    event_id: str,
    legacy_confirmacion: bool,
) -> Tuple[DecisionReconciliacionTransfer, str, str]:
    ft = _cargar_financial_transfer(db, contacto_id)
    decision, motivo = evaluar_reconciliacion_transfer(
        contacto_id=contacto_id,
        estado_financiero=estado,
        financial_transfer=ft,
        stripe_snapshot=snapshot,
        legacy_confirmacion=legacy_confirmacion,
        conflicto_abierto=_conflicto_bloquea(db, contacto_id),
    )

    if decision == DecisionReconciliacionTransfer.BLOCKED:
        reconciliation.registrar_discrepancia(
            db, contacto_id, TipoDiscrepancia.STATUS_MISMATCH,
            stripe_transfer_id=transfer_id,
            ruana_estado=estado.value if estado else "",
            stripe_estado=event_type,
            metadata={"event_id": event_id, "motivo": motivo, "conflicto": True},
        )
        _marcar_reconciliacion(db, contacto_id, DecisionReconciliacionTransfer.BLOCKED.value)
        return decision, motivo, "bloqueado_conflicto"

    if decision == DecisionReconciliacionTransfer.MISMATCH:
        tipo = {
            "importe": TipoDiscrepancia.AMOUNT_MISMATCH,
            "moneda": TipoDiscrepancia.CURRENCY_MISMATCH,
            "destination": TipoDiscrepancia.TRANSFER_ID_MISMATCH,
            "metadata_contacto_id": TipoDiscrepancia.STATUS_MISMATCH,
            "transfer_id": TipoDiscrepancia.TRANSFER_ID_MISMATCH,
        }.get(motivo, TipoDiscrepancia.STATUS_MISMATCH)
        reconciliation.registrar_discrepancia(
            db, contacto_id, tipo,
            stripe_transfer_id=transfer_id,
            ruana_estado=estado.value if estado else "",
            stripe_estado=event_type,
            metadata={"event_id": event_id, "motivo": motivo, "snapshot": snapshot},
        )
        _marcar_reconciliacion(db, contacto_id, DecisionReconciliacionTransfer.MISMATCH.value)
        return decision, motivo, "bloqueado_coherencia"

    if decision == DecisionReconciliacionTransfer.REVERSED:
        res, ant, nuevo = manejar_reversion_transfer(
            db, contacto_id, transfer_id, snapshot,
            event_id=event_id, event_type=event_type,
        )
        return decision, motivo, res

    if decision == DecisionReconciliacionTransfer.PENDING:
        _marcar_reconciliacion(db, contacto_id, DecisionReconciliacionTransfer.PENDING.value)
        _auditar_webhook(db, contacto_id, event_type, event_id, "pending", motivo, estado, None)
        return decision, motivo, "pending"

    if decision == DecisionReconciliacionTransfer.CONFIRMED:
        if motivo == "ya_transferido_idempotente":
            return decision, motivo, "idempotent"
        aplicado = _aplicar_confirmacion_reconciliada(
            db, contacto_id, transfer_id, event_type=event_type, event_id=event_id,
        )
        return decision, motivo, aplicado

    return decision, motivo, "ignored"


def _aplicar_confirmacion_reconciliada(
    db, contacto_id: int, transfer_id: str, *, event_type: str, event_id: str,
) -> str:
    ft = _cargar_financial_transfer(db, contacto_id)
    if ft and ft.get("efectos_post_transfer_aplicados"):
        _marcar_reconciliacion(db, contacto_id, DecisionReconciliacionTransfer.CONFIRMED.value)
        return "idempotent"

    fin = transfer_svc.finalizar_transferencia_completada(
        db, contacto_id, transfer_id, origen=f"reconciliacion:{event_type}",
    )
    if fin.get("status") == "success":
        _marcar_reconciliacion(db, contacto_id, DecisionReconciliacionTransfer.CONFIRMED.value)
        _marcar_efectos_aplicados(db, contacto_id)
        _auditar_webhook(
            db, contacto_id, event_type, event_id, "confirmed", "reconciliacion_explicita",
            fts.obtener_estado_financiero(db, contacto_id),
            EstadoFinanciero.TRANSFERIDO,
        )
        return "idempotent" if fin.get("idempotent") else "ok"
    return fin.get("message", "error_confirmacion")


def _avanzar_hasta_enviada(db, contacto_id: int, transfer_id: str, event_type: str) -> None:
    estado = fts.obtener_estado_financiero(db, contacto_id)
    if estado in (EstadoFinanciero.TRANSFERENCIA_ENVIADA, EstadoFinanciero.TRANSFERIDO):
        return
    if estado == EstadoFinanciero.LIBERACION_AUTORIZADA:
        fts.transicionar(
            db, contacto_id, EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
            actor_tipo="stripe_webhook", motivo=event_type, stripe_ref=transfer_id,
        )
    estado = fts.obtener_estado_financiero(db, contacto_id)
    if estado in (EstadoFinanciero.TRANSFERENCIA_PENDIENTE, EstadoFinanciero.LIBERACION_AUTORIZADA):
        fts.transicionar(
            db, contacto_id, EstadoFinanciero.TRANSFERENCIA_ENVIADA,
            actor_tipo="stripe_webhook", motivo=event_type, stripe_ref=transfer_id,
        )
        with db._lock:
            conn = db._connect()
            cursor = conn.cursor()
            _fin_repo.actualizar_solo_estado_transferencia(
                cursor, contacto_id, EstadoTransferencia.ENVIADA.value
            )
            conn.commit()
            conn.close()


def _persistir_referencias_stripe(db, contacto_id: int, transfer_id: str, obj: Any) -> None:
    snapshot = extraer_snapshot_stripe(obj)
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        from core.repositories.stripe_webhook_repo import StripeWebhookRepo
        wh = StripeWebhookRepo()
        wh.actualizar_stripe_transfer_id(cursor, contacto_id, transfer_id)
        _transfer_repo.actualizar_referencias_stripe(
            cursor, contacto_id, transfer_id,
            balance_transaction_id=snapshot.get("balance_transaction", ""),
            destination_payment_id=snapshot.get("destination_payment", ""),
        )
        conn.commit()
        conn.close()


def _persistir_snapshot(
    db, contacto_id: int, transfer_id: str, snapshot: Dict[str, Any],
    event_id: str, event_type: str,
) -> None:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _transfer_repo.guardar_snapshot(
            cursor, contacto_id, transfer_id, snapshot, event_id, event_type,
        )
        conn.commit()
        conn.close()


def _cargar_ultimo_snapshot(db, contacto_id: int) -> Optional[Dict[str, Any]]:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        snap = _transfer_repo.ultimo_snapshot(cursor, contacto_id)
        conn.close()
    return snap


def _conflicto_bloquea(db, contacto_id: int) -> bool:
    from core.services import financial_conflict_service as fcs
    bloquea, _ = fcs.bloquea_operaciones_financieras(db, contacto_id)
    return bloquea


def _cargar_financial_transfer(db, contacto_id: int) -> Optional[Dict[str, Any]]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = _transfer_repo.select_por_contacto(cursor, contacto_id)
        conn.close()
    return _transfer_repo._row_dict(row) if row else None


def _marcar_reconciliacion(db, contacto_id: int, estado_recon: str) -> None:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _transfer_repo.marcar_reconciliacion(cursor, contacto_id, estado_recon)
        conn.commit()
        conn.close()


def _marcar_efectos_aplicados(db, contacto_id: int) -> None:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _transfer_repo.marcar_efectos_aplicados(cursor, contacto_id)
        conn.commit()
        conn.close()


def _marcar_bloqueada(db, contacto_id: int) -> None:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        _transfer_repo.marcar_bloqueada(cursor, contacto_id)
        conn.commit()
        conn.close()


def _auditar_webhook(
    db, contacto_id: int, event_type: str, event_id: str,
    resultado: str, motivo: str,
    estado_antes: Optional[EstadoFinanciero],
    estado_despues: Optional[EstadoFinanciero],
) -> None:
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        if _transfer_repo.tabla_existe(cursor):
            _transfer_repo.registrar_intento(
                cursor, contacto_id,
                resultado=resultado, motivo_bloqueo=motivo,
                estado_anterior=estado_antes.value if estado_antes else "",
                estado_nuevo=estado_despues.value if estado_despues else "",
                metadata={"event_type": event_type, "event_id": event_id},
            )
        conn.commit()
        conn.close()
