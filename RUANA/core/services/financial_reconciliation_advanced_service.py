"""Servicio de reconciliación financiera avanzada (FASE 07). Solo observa — no mueve dinero."""
from __future__ import annotations

import sqlite3
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import stripe_client
from core.financial.discrepancia import TipoDiscrepancia
from core.financial.reconciliation_estados import EstadoReconciliacionAvanzada
from core.financial.reconciliation_snapshot import (
    RECONCILER_VERSION,
    build_ruana_snapshot,
    comision_ruana_cents,
    empty_snapshot,
    merge_stripe_into_snapshot,
)
from core.reconciliation_authorization import RECON_EXECUTE, RECON_RESOLVE
from core.repositories.financial_reconciliation_advanced_repo import FinancialReconciliationAdvancedRepo
from core.repositories.financial_reconciliation_repo import FinancialReconciliationRepo
from core.services import financial_conflict_service as fcs
from core.services import financial_dispute_service as fds
from core.services import financial_reconciliation_service as reconciliation

_adv_repo = FinancialReconciliationAdvancedRepo()


def _row_dict(row, cursor=None) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return dict(row)
    if cursor and cursor.description:
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}
    return {}


def _contacto_por_pi(db, payment_intent_id: str) -> Optional[Dict[str, Any]]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT cr.*, a.stripe_account_id
                FROM contactos_ruana cr
                LEFT JOIN aliados a ON a.codigo = cr.profesional_codigo
                WHERE cr.stripe_payment_intent_id = ?
                LIMIT 1
                """,
                (payment_intent_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def _contacto_por_id(db, contacto_id: int) -> Optional[Dict[str, Any]]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT cr.*, a.stripe_account_id
                FROM contactos_ruana cr
                LEFT JOIN aliados a ON a.codigo = cr.profesional_codigo
                WHERE cr.id = ?
                LIMIT 1
                """,
                (contacto_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def _esta_bloqueado(db, contacto_id: int) -> Tuple[bool, str]:
    bloquea_c, motivo_c = fcs.bloquea_operaciones_financieras(db, contacto_id)
    if bloquea_c:
        return True, motivo_c
    if fds.tiene_disputa_bloqueante(db, contacto_id):
        return True, "disputa_stripe"
    return False, ""


def fetch_stripe_chain(
  contacto: Dict[str, Any],
  *,
  stripe_fetcher: Optional[Dict[str, Callable]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Obtiene recursos Stripe. Devuelve (snapshot_stripe, resource_logs, warnings)."""
    fetcher = stripe_fetcher or {}
    pi_id = str(contacto.get("stripe_payment_intent_id") or "")
    charge_id = str(contacto.get("stripe_charge_id") or "")
    transfer_id = str(contacto.get("stripe_transfer_id") or "")
    account_id = str(contacto.get("stripe_account_id") or "")

    snap = empty_snapshot()
    snap["identidad"]["contacto_id"] = int(contacto.get("id") or 0)
    logs: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def _read(name: str, fn, *args, **kwargs):
        if name in fetcher:
            return fetcher[name](*args, **kwargs)
        safe_fn = getattr(stripe_client, f"{fn}_safe", None)
        if safe_fn:
            return safe_fn(*args, **kwargs)
        return {"status": "not_applicable", "data": None, "error_code": "no_fetcher"}

    pi_res = _read("payment_intent", "retrieve_payment_intent", pi_id) if pi_id else {
        "status": "not_applicable", "data": None, "error_code": "",
    }
    logs.append({"type": "payment_intent", "id": pi_id, **pi_res})

    if pi_res["status"] == "ok" and pi_res.get("data"):
        snap = merge_stripe_into_snapshot(snap, payment_intent=pi_res["data"])
        if not charge_id:
            latest = (pi_res["data"].get("latest_charge") or "")
            if latest:
                charge_id = str(latest)

    charge_res = _read("charge", "retrieve_charge", charge_id) if charge_id else {
        "status": "not_applicable", "data": None, "error_code": "",
    }
    logs.append({"type": "charge", "id": charge_id, **charge_res})
    if charge_res["status"] == "ok" and charge_res.get("data"):
        snap = merge_stripe_into_snapshot(snap, charge=charge_res["data"])
        bt_id = charge_res["data"].get("balance_transaction")
        if isinstance(bt_id, str) and bt_id:
            bt_res = _read("balance_transaction", "retrieve_balance_transaction", bt_id)
            logs.append({"type": "balance_transaction", "id": bt_id, **bt_res})
            if bt_res["status"] == "ok" and bt_res.get("data"):
                snap = merge_stripe_into_snapshot(snap, balance_transaction=bt_res["data"])
            elif bt_res["status"] in ("pending", "unavailable"):
                warnings.append("balance_transaction_pending")

    transfer_res = _read("transfer", "retrieve_transfer", transfer_id) if transfer_id else {
        "status": "not_applicable", "data": None, "error_code": "",
    }
    logs.append({"type": "transfer", "id": transfer_id, **transfer_res})
    if transfer_res["status"] == "ok" and transfer_res.get("data"):
        snap = merge_stripe_into_snapshot(snap, transfer=transfer_res["data"])
        account_id = account_id or str(transfer_res["data"].get("destination") or "")

    if account_id:
        acc_res = _read("account", "retrieve_account", account_id)
        logs.append({"type": "account", "id": account_id, **acc_res})
        if acc_res["status"] == "ok" and acc_res.get("data"):
            snap = merge_stripe_into_snapshot(snap, account=acc_res["data"])

    ref_res = _read("refunds", "list_refunds", payment_intent_id=pi_id, charge_id=charge_id)
    logs.append({"type": "refunds", "id": pi_id or charge_id, **ref_res})
    if ref_res["status"] == "ok" and ref_res.get("data"):
        refunds = (ref_res["data"].get("data") or []) if isinstance(ref_res["data"], dict) else ref_res["data"]
        snap = merge_stripe_into_snapshot(snap, refunds=refunds or [])

    # Disputes: from charge if available
    disputes: List[Dict[str, Any]] = []
    if charge_res.get("data") and charge_res["data"].get("dispute"):
        disp_id = str(charge_res["data"]["dispute"])
        d_res = _read("dispute", "retrieve_dispute", disp_id)
        logs.append({"type": "dispute", "id": disp_id, **d_res})
        if d_res["status"] == "ok" and d_res.get("data"):
            disputes.append(d_res["data"])
    snap = merge_stripe_into_snapshot(snap, disputes=disputes)

    for log in logs:
        if log.get("status") in ("pending", "unavailable"):
            warnings.append(f"{log.get('type')}_{log.get('status')}")
        if log.get("error_code") == "rate_limit":
            warnings.append("stripe_rate_limit")

    return snap, logs, warnings


def _enrich_ruana_from_db(db, contacto_id: int, snap: Dict[str, Any]) -> Dict[str, Any]:
    """Enriquece snapshot RUANA con refunds y disputas persistidos."""
    out = dict(snap)
    ident = dict(out.get("identidad") or {})
    imp = dict(out.get("importes_cents") or {})
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT stripe_refund_id, importe_confirmado_cents FROM financial_refunds
                WHERE contacto_id = ? AND estado NOT IN ('FAILED', 'CANCELED')
                """,
                (contacto_id,),
            )
            refunds = cursor.fetchall()
            cursor.execute(
                """
                SELECT stripe_dispute_id, amount_cents, estado_interno
                FROM financial_disputes WHERE contacto_id = ?
                """,
                (contacto_id,),
            )
            disputes = cursor.fetchall()
        finally:
            conn.close()
    refund_ids = []
    total_ref = 0
    for row in refunds:
        rid = row[0] if not hasattr(row, "keys") else row["stripe_refund_id"]
        amt = row[1] if not hasattr(row, "keys") else row["importe_confirmado_cents"]
        if rid:
            refund_ids.append(str(rid))
        total_ref += int(amt or 0)
    dispute_ids = []
    total_disp = 0
    for row in disputes:
        did = row[0] if not hasattr(row, "keys") else row["stripe_dispute_id"]
        amt = row[1] if not hasattr(row, "keys") else row["amount_cents"]
        if did:
            dispute_ids.append(str(did))
        total_disp += int(amt or 0)
    ident["refund_ids"] = refund_ids
    ident["dispute_ids"] = dispute_ids
    if refund_ids:
        imp["total_reembolsado"] = total_ref
    if dispute_ids:
        imp["importe_disputado"] = total_disp
    out["identidad"] = ident
    out["importes_cents"] = imp
    return out


def comparar_snapshots(
    ruana: Dict[str, Any],
    stripe: Dict[str, Any],
) -> Tuple[EstadoReconciliacionAvanzada, List[TipoDiscrepancia], List[str]]:
    """Compara snapshots normalizados. Devuelve estado, discrepancias y warnings."""
    discrepancias: List[TipoDiscrepancia] = []
    warnings: List[str] = []
    r_id = ruana.get("identidad") or {}
    s_id = stripe.get("identidad") or {}
    r_imp = ruana.get("importes_cents") or {}
    s_imp = stripe.get("importes_cents") or {}
    r_ctrl = ruana.get("control") or {}
    s_ctrl = stripe.get("control") or {}

    if r_id.get("payment_intent_id") and s_id.get("payment_intent_id"):
        if r_id["payment_intent_id"] != s_id["payment_intent_id"]:
            discrepancias.append(TipoDiscrepancia.PAYMENT_INTENT_MISMATCH)

    if r_id.get("charge_id") and not s_id.get("charge_id"):
        discrepancias.append(TipoDiscrepancia.CHARGE_MISSING_STRIPE)
    elif s_id.get("charge_id") and not r_id.get("charge_id"):
        discrepancias.append(TipoDiscrepancia.CHARGE_MISSING_RUANA)

    if r_id.get("transfer_id") and not s_id.get("transfer_id"):
        discrepancias.append(TipoDiscrepancia.TRANSFER_MISSING_STRIPE)
    elif s_id.get("transfer_id") and not r_id.get("transfer_id"):
        discrepancias.append(TipoDiscrepancia.TRANSFER_MISSING_RUANA)

    if r_id.get("transfer_id") and s_id.get("transfer_id") and r_id["transfer_id"] != s_id["transfer_id"]:
        discrepancias.append(TipoDiscrepancia.TRANSFER_ID_MISMATCH)

    if r_id.get("connected_account_id") and s_id.get("connected_account_id"):
        if r_id["connected_account_id"] != s_id["connected_account_id"]:
            discrepancias.append(TipoDiscrepancia.DESTINATION_MISMATCH)

    bruto_r = int(r_imp.get("importe_bruto") or 0)
    bruto_s = int(s_imp.get("importe_cobrado") or s_imp.get("importe_bruto") or 0)
    if bruto_r and bruto_s and bruto_r != bruto_s:
        discrepancias.append(TipoDiscrepancia.AMOUNT_MISMATCH)

    mon_r = (r_ctrl.get("moneda") or "eur").lower()
    mon_s = (s_ctrl.get("moneda") or "eur").lower()
    if mon_s and mon_r != mon_s:
        discrepancias.append(TipoDiscrepancia.CURRENCY_MISMATCH)

    if r_id.get("balance_transaction_id") and s_id.get("balance_transaction_id"):
        if r_id["balance_transaction_id"] != s_id["balance_transaction_id"]:
            discrepancias.append(TipoDiscrepancia.BALANCE_TRANSACTION_MISMATCH)
    elif r_id.get("balance_transaction_id") and not s_id.get("balance_transaction_id"):
        discrepancias.append(TipoDiscrepancia.BALANCE_TRANSACTION_MISMATCH)
    elif s_id.get("balance_transaction_id") and not r_id.get("balance_transaction_id"):
        warnings.append("balance_transaction_missing_ruana")

    r_refunds = set(r_id.get("refund_ids") or [])
    s_refunds = set(s_id.get("refund_ids") or [])
    total_ref_r = int(r_imp.get("total_reembolsado") or 0)
    total_ref_s = int(s_imp.get("total_reembolsado") or 0)
    if s_refunds and not r_refunds:
        discrepancias.append(TipoDiscrepancia.REFUND_MISSING_RUANA)
    elif r_refunds and not s_refunds and total_ref_r > 0:
        discrepancias.append(TipoDiscrepancia.REFUND_MISSING_STRIPE)
    elif total_ref_r and total_ref_s and total_ref_r != total_ref_s:
        discrepancias.append(TipoDiscrepancia.REFUND_AMOUNT_MISMATCH)

    r_disputes = set(r_id.get("dispute_ids") or [])
    s_disputes = set(s_id.get("dispute_ids") or [])
    total_disp_r = int(r_imp.get("importe_disputado") or 0)
    total_disp_s = int(s_imp.get("importe_disputado") or 0)
    if s_disputes and not r_disputes:
        discrepancias.append(TipoDiscrepancia.DISPUTE_MISSING_RUANA)
    elif r_disputes and not s_disputes and total_disp_r > 0:
        discrepancias.append(TipoDiscrepancia.DISPUTE_MISSING_STRIPE)
    elif total_disp_r and total_disp_s and total_disp_r != total_disp_s:
        discrepancias.append(TipoDiscrepancia.DISPUTE_AMOUNT_MISMATCH)

    fee_r = int(r_imp.get("fee_stripe") or 0)
    fee_s = int(s_imp.get("fee_stripe") or 0)
    if fee_s > 0 and fee_r > 0 and fee_r != fee_s:
        discrepancias.append(TipoDiscrepancia.FEE_MISMATCH)

    com_r = int(r_imp.get("comision_ruana") or 0)
    esperada = comision_ruana_cents(bruto_r) if bruto_r else 0
    if com_r and esperada and com_r != esperada:
        warnings.append("comision_ruana_divergente")

    if discrepancias:
        return EstadoReconciliacionAvanzada.MISMATCH, discrepancias, warnings
    if warnings:
        return EstadoReconciliacionAvanzada.MATCHED_WITH_WARNINGS, discrepancias, warnings
    if not s_id.get("payment_intent_id") and not s_ctrl.get("estado_stripe"):
        return EstadoReconciliacionAvanzada.PENDING, discrepancias, warnings
    return EstadoReconciliacionAvanzada.MATCHED, discrepancias, warnings


def _registrar_discrepancias(
    db,
    contacto_id: int,
    tipos: List[TipoDiscrepancia],
    *,
    ruana_snap: Dict[str, Any],
    stripe_snap: Dict[str, Any],
) -> int:
    count = 0
    ident = stripe_snap.get("identidad") or {}
    ctrl = stripe_snap.get("control") or {}
    imp_s = stripe_snap.get("importes_cents") or {}
    imp_r = ruana_snap.get("importes_cents") or {}
    for tipo in tipos:
        r = reconciliation.registrar_discrepancia(
            db, contacto_id, tipo,
            stripe_payment_intent_id=ident.get("payment_intent_id") or "",
            stripe_transfer_id=ident.get("transfer_id") or "",
            ruana_estado=ctrl.get("estado_ruana") or "",
            stripe_estado=ctrl.get("estado_stripe") or "",
            importe_ruana=round(int(imp_r.get("importe_bruto") or 0) / 100.0, 2),
            importe_stripe=round(int(imp_s.get("importe_cobrado") or 0) / 100.0, 2),
            metadata={"reconciler_version": RECONCILER_VERSION},
            alerta_admin=False,
        )
        if r.get("discrepancia_id"):
            count += 1
    return count


def reconciliar_contacto_avanzado(
    db,
    contacto_id: int,
    *,
    actor: str = "sistema",
    permiso_usado: str = RECON_EXECUTE,
    idempotency_key: str = "",
    motivo: str = "",
    stripe_fetcher: Optional[Dict[str, Callable]] = None,
) -> Dict[str, Any]:
    contacto = _contacto_por_id(db, contacto_id)
    if not contacto:
        return {"status": "error", "message": "Contacto no encontrado"}

    key = idempotency_key or f"recon-contacto-{contacto_id}-{RECONCILER_VERSION}"
    bloqueado, motivo_b = _esta_bloqueado(db, contacto_id)

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            claim, prev = _adv_repo.reclamar_ejecucion(
                cursor,
                contacto_id=contacto_id,
                payment_intent_id=str(contacto.get("stripe_payment_intent_id") or ""),
                transfer_id=str(contacto.get("stripe_transfer_id") or ""),
                operacion="contacto",
                idempotency_key=key,
                actor_codigo=actor,
                permiso_usado=permiso_usado,
                motivo=motivo,
            )
            exec_id = int((prev or {}).get("id") or 0)
            if claim == "existing" and prev and prev.get("estado") in (
                EstadoReconciliacionAvanzada.MATCHED.value,
                EstadoReconciliacionAvanzada.MATCHED_WITH_WARNINGS.value,
                EstadoReconciliacionAvanzada.MISMATCH.value,
                EstadoReconciliacionAvanzada.BLOCKED.value,
                EstadoReconciliacionAvanzada.RESOLVED.value,
            ):
                conn.commit()
                return {
                    "status": "success", "idempotent": True,
                    "execution_id": exec_id, "estado": prev.get("estado"),
                }
            _adv_repo.actualizar_estado(cursor, exec_id, EstadoReconciliacionAvanzada.FETCHING.value)
            conn.commit()
        finally:
            conn.close()

    if bloqueado:
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                _adv_repo.actualizar_estado(
                    cursor, exec_id, EstadoReconciliacionAvanzada.BLOCKED.value,
                    metricas={"bloqueo": motivo_b}, finalizar=True,
                )
                snap_r = build_ruana_snapshot(contacto)
                _adv_repo.guardar_snapshot(cursor, execution_id=exec_id, contacto_id=contacto_id, snapshot=snap_r, origen="ruana_db")
                conn.commit()
            finally:
                conn.close()
        return {
            "status": "success", "execution_id": exec_id,
            "estado": EstadoReconciliacionAvanzada.BLOCKED.value, "bloqueo": motivo_b,
        }

    ruana_snap = _enrich_ruana_from_db(db, contacto_id, build_ruana_snapshot(contacto))
    stripe_snap, logs, fetch_warnings = fetch_stripe_chain(contacto, stripe_fetcher=stripe_fetcher)

    estado, disc_types, cmp_warnings = comparar_snapshots(ruana_snap, stripe_snap)
    all_warnings = fetch_warnings + cmp_warnings

    if any("pending" in w or "unavailable" in w or "rate_limit" in w for w in all_warnings):
        if estado in (
            EstadoReconciliacionAvanzada.MATCHED,
            EstadoReconciliacionAvanzada.MATCHED_WITH_WARNINGS,
            EstadoReconciliacionAvanzada.MISMATCH,
        ):
            estado = EstadoReconciliacionAvanzada.PENDING
            disc_types = []

    disc_count = 0
    if disc_types:
        disc_count = _registrar_discrepancias(db, contacto_id, disc_types, ruana_snap=ruana_snap, stripe_snap=stripe_snap)

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            for log in logs:
                _adv_repo.registrar_recurso(
                    cursor, exec_id,
                    resource_type=log.get("type") or "unknown",
                    resource_id=str(log.get("id") or ""),
                    fetch_status=log.get("status") or "error",
                    error_code=log.get("error_code") or "",
                    http_status=int(log.get("http_status") or 0),
                )
            _adv_repo.guardar_snapshot(
                cursor, execution_id=exec_id, contacto_id=contacto_id,
                snapshot=stripe_snap, origen="stripe_api",
            )
            _adv_repo.actualizar_estado(
                cursor, exec_id, estado.value,
                metricas={
                    "discrepancias": disc_count,
                    "warnings": all_warnings,
                    "estado": estado.value,
                },
                finalizar=True,
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "status": "success",
        "execution_id": exec_id,
        "contacto_id": contacto_id,
        "estado": estado.value,
        "discrepancias_nuevas": disc_count,
        "warnings": all_warnings,
    }


def reconciliar_payment_intent(
    db,
    payment_intent_id: str,
    *,
    actor: str = "sistema",
    permiso_usado: str = RECON_EXECUTE,
    idempotency_key: str = "",
    stripe_fetcher: Optional[Dict[str, Callable]] = None,
) -> Dict[str, Any]:
    contacto = _contacto_por_pi(db, payment_intent_id)
    if not contacto:
        return {"status": "error", "message": "Contacto no encontrado para PI"}
    key = idempotency_key or f"recon-pi-{payment_intent_id}"
    return reconciliar_contacto_avanzado(
        db, int(contacto["id"]),
        actor=actor, permiso_usado=permiso_usado,
        idempotency_key=key, stripe_fetcher=stripe_fetcher,
    )


def reconciliar_transfer(
    db,
    transfer_id: str,
    *,
    actor: str = "sistema",
    permiso_usado: str = RECON_EXECUTE,
    idempotency_key: str = "",
    stripe_fetcher: Optional[Dict[str, Callable]] = None,
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM contactos_ruana WHERE stripe_transfer_id = ? LIMIT 1",
                (transfer_id,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()
    if not row:
        return {"status": "error", "message": "Contacto no encontrado para transfer"}
    key = idempotency_key or f"recon-tr-{transfer_id}"
    return reconciliar_contacto_avanzado(
        db, int(row["id"]),
        actor=actor, permiso_usado=permiso_usado,
        idempotency_key=key, stripe_fetcher=stripe_fetcher,
    )


def ejecutar_lote(
    db,
    *,
    limit: int = 50,
    actor: str = "sistema",
    permiso_usado: str = RECON_EXECUTE,
    stripe_fetcher: Optional[Dict[str, Callable]] = None,
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            filas = _adv_repo.listar_pendientes_lote(cursor, limit)
        finally:
            conn.close()

    metricas = {
        "total": 0, "matched": 0, "warnings": 0, "pending": 0,
        "mismatch": 0, "blocked": 0, "error": 0,
    }
    resultados: List[Dict[str, Any]] = []

    for fila in filas[:limit]:
        cid = int(fila.get("id") or 0)
        metricas["total"] += 1
        try:
            r = reconciliar_contacto_avanzado(
                db, cid, actor=actor, permiso_usado=permiso_usado,
                idempotency_key=f"recon-lote-{cid}-{RECONCILER_VERSION}",
                stripe_fetcher=stripe_fetcher,
            )
            estado = (r.get("estado") or "error").lower()
            if estado == EstadoReconciliacionAvanzada.MATCHED.value.lower():
                metricas["matched"] += 1
            elif estado == EstadoReconciliacionAvanzada.MATCHED_WITH_WARNINGS.value.lower():
                metricas["warnings"] += 1
            elif estado == EstadoReconciliacionAvanzada.PENDING.value.lower():
                metricas["pending"] += 1
            elif estado == EstadoReconciliacionAvanzada.BLOCKED.value.lower():
                metricas["blocked"] += 1
            elif estado == EstadoReconciliacionAvanzada.MISMATCH.value.lower():
                metricas["mismatch"] += 1
            else:
                metricas["error"] += 1
            resultados.append(r)
        except Exception as e:
            metricas["error"] += 1
            resultados.append({"status": "error", "contacto_id": cid, "message": str(e)[:200]})

    return {"status": "success", "metricas": metricas, "resultados": resultados}


def resolver_ejecucion(
    db,
    execution_id: int,
    *,
    actor: str,
    permiso_usado: str = RECON_RESOLVE,
    motivo: str,
) -> Dict[str, Any]:
    """Marca ejecución RESOLVED administrativamente — no corrige dinero."""
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _adv_repo.select_por_id(cursor, execution_id)
            if not row:
                return {"status": "error", "message": "Ejecución no encontrada"}
            _adv_repo.actualizar_estado(
                cursor, execution_id, EstadoReconciliacionAvanzada.RESOLVED.value,
                metricas={"resolucion_admin": motivo, "actor": actor, "permiso": permiso_usado},
                finalizar=True,
            )
            conn.commit()
            return {"status": "success", "execution_id": execution_id, "estado": "RESOLVED"}
        finally:
            conn.close()
