"""Servicio de automatización y monitorización financiera (FASE 11).

Solo detecta, registra y alerta — nunca mueve dinero ni resuelve incidencias.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from core.financial_automation_authorization import AUTOMATION_EXECUTE, MONITORING_VIEW
from core.repositories.financial_automation_repo import FinancialAutomationRepo
from core.repositories.financial_admin_repo import FinancialAdminRepo
from core.services import financial_audit_service as audit
from core.services import financial_ledger_reconciliation_service as flrs
from core.services import financial_reconciliation_advanced_service as fras

_repo = FinancialAutomationRepo()
_admin_repo = FinancialAdminRepo()

JOB_MONITORING_CYCLE = "financial_monitoring_cycle"
JOB_RECONCILIATION_BATCH = "financial_reconciliation_batch"

_DEFAULT_LEASE_TTL = int(os.environ.get("RUANA_FIN_AUTOMATION_LEASE_TTL", "300"))
_DEFAULT_RECON_LIMIT = int(os.environ.get("RUANA_FIN_AUTOMATION_RECON_LIMIT", "20"))
_DISPUTE_DEADLINE_HOURS = int(os.environ.get("RUANA_FIN_ALERT_DISPUTE_HOURS", "72"))
_CONFLICT_OLD_DAYS = int(os.environ.get("RUANA_FIN_ALERT_CONFLICT_DAYS", "7"))
_REFUND_STALE_HOURS = int(os.environ.get("RUANA_FIN_ALERT_REFUND_STALE_HOURS", "48"))
_WEBHOOK_STUCK_HOURS = int(os.environ.get("RUANA_FIN_ALERT_WEBHOOK_STUCK_HOURS", "2"))
_TRANSFER_STUCK_HOURS = int(os.environ.get("RUANA_FIN_ALERT_TRANSFER_STUCK_HOURS", "24"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iso_hours_ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(microsecond=0).isoformat()


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()


def adquirir_lease(db, *, job_name: str, holder: str, ttl_seconds: int = _DEFAULT_LEASE_TTL) -> bool:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            ok = _repo.adquirir_lease(cursor, job_name=job_name, holder=holder, ttl_seconds=ttl_seconds)
            conn.commit()
            return ok
        finally:
            conn.close()


def liberar_lease(db, *, job_name: str, holder: str) -> None:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _repo.liberar_lease(cursor, job_name=job_name, holder=holder)
            conn.commit()
        finally:
            conn.close()


def _registrar_alerta(
    cursor,
    *,
    run_id: str,
    alert_key: str,
    tipo: str,
    severidad: str,
    contacto_id: Optional[int],
    accion_recomendada: str,
    accion_disponible: Optional[str],
    fuente: str,
    metadata: Optional[Dict[str, Any]] = None,
    fecha_evento: Optional[str] = None,
) -> tuple[bool, bool]:
    """Devuelve (nueva, actualizada)."""
    if _admin_repo.alerta_resuelta(cursor, alert_key):
        return False, False
    nueva, _ = _repo.upsert_alerta(
        cursor,
        alert_key=alert_key,
        tipo=tipo,
        severidad=severidad,
        contacto_id=contacto_id,
        accion_recomendada=accion_recomendada,
        accion_disponible=accion_disponible,
        fuente=fuente,
        run_id=run_id,
        metadata=metadata,
        fecha_evento=fecha_evento,
    )
    return nueva, not nueva


def _detectar_webhooks(cursor, run_id: str) -> Dict[str, int]:
    stats = {"nuevas": 0, "actualizadas": 0}
    if not _admin_repo.tabla_existe(cursor, "stripe_webhook_events"):
        return stats
    cols = {c[1] for c in cursor.execute("PRAGMA table_info(stripe_webhook_events)").fetchall()}
    stuck_before = _iso_hours_ago(_WEBHOOK_STUCK_HOURS)
    if "estado_procesamiento" in cols:
        wh_fail = "estado_procesamiento != 'completed' OR error_message IS NOT NULL"
        wh_stuck = f"({wh_fail}) AND creado_en < ?"
    elif "procesado" in cols:
        wh_fail = "procesado = 0 OR estado = 'error'"
        wh_stuck = f"({wh_fail}) AND creado_en < ?"
    else:
        wh_fail = "resultado IS NOT NULL AND resultado != 'ok'"
        wh_stuck = f"({wh_fail}) AND creado_en < ?"

    for sql, tipo, sev in (
        (f"SELECT id, stripe_event_id, tipo, contacto_id, creado_en, resultado FROM stripe_webhook_events WHERE {wh_fail} ORDER BY id DESC LIMIT 100", "webhook_fallido", "high"),
        (f"SELECT id, stripe_event_id, tipo, contacto_id, creado_en, resultado FROM stripe_webhook_events WHERE {wh_stuck} ORDER BY id DESC LIMIT 100", "webhook_atascado", "critical"),
    ):
        params: tuple = () if tipo == "webhook_fallido" else (stuck_before,)
        cursor.execute(sql, params)
        for row in _admin_repo._rows(cursor):
            key = f"webhook:{row.get('id')}"
            meta = {"object_id": row.get("stripe_event_id")}
            n, u = _registrar_alerta(
                cursor, run_id=run_id, alert_key=key, tipo=tipo, severidad=sev,
                contacto_id=row.get("contacto_id"),
                accion_recomendada="Revisar evento webhook y reprocesar si procede",
                accion_disponible=None, fuente="stripe_webhook_events",
                metadata=meta, fecha_evento=row.get("creado_en"),
            )
            stats["nuevas"] += int(n)
            stats["actualizadas"] += int(u)
    return stats


def _detectar_refunds(cursor, run_id: str) -> Dict[str, int]:
    stats = {"nuevas": 0, "actualizadas": 0}
    if not _admin_repo.tabla_existe(cursor, "financial_refunds"):
        return stats
    stale = _iso_hours_ago(_REFUND_STALE_HOURS)
    queries = [
        (
            """
            SELECT id, contacto_id, estado, importe_solicitado_cents, importe_confirmado_cents, creado_en
            FROM financial_refunds
            WHERE estado IN ('REQUESTED', 'STRIPE_PROCESSING', 'PENDING_RECONCILIATION')
              AND creado_en < ?
            ORDER BY creado_en ASC LIMIT 100
            """,
            (stale,),
            "refund_pendiente_antiguo",
            "high",
            "Revisar reembolso pendiente y su estado en Stripe",
            "financial.refund.execute",
        ),
        (
            """
            SELECT id, contacto_id, estado, importe_solicitado_cents, importe_confirmado_cents, creado_en
            FROM financial_refunds
            WHERE estado = 'FAILED' OR (estado = 'SUCCEEDED' AND (stripe_refund_id IS NULL OR stripe_refund_id = ''))
            ORDER BY creado_en DESC LIMIT 100
            """,
            (),
            "refund_inconsistente",
            "critical",
            "Investigar inconsistencia de reembolso (estado vs Stripe)",
            "financial.refund.view",
        ),
    ]
    for sql, params, tipo, sev, accion, perm in queries:
        cursor.execute(sql, params)
        for row in _admin_repo._rows(cursor):
            key = f"refund:{tipo}:{row.get('id')}"
            n, u = _registrar_alerta(
                cursor, run_id=run_id, alert_key=key, tipo=tipo, severidad=sev,
                contacto_id=row.get("contacto_id"),
                accion_recomendada=accion, accion_disponible=perm,
                fuente="financial_refunds", fecha_evento=row.get("creado_en"),
                metadata={"estado": row.get("estado")},
            )
            stats["nuevas"] += int(n)
            stats["actualizadas"] += int(u)
    return stats


def _detectar_disputas(cursor, run_id: str) -> Dict[str, int]:
    stats = {"nuevas": 0, "actualizadas": 0}
    if not _admin_repo.tabla_existe(cursor, "financial_disputes"):
        return stats
    deadline_limit = (datetime.now(timezone.utc) + timedelta(hours=_DISPUTE_DEADLINE_HOURS)).replace(microsecond=0).isoformat()
    cursor.execute(
        """
        SELECT id, contacto_id, stripe_dispute_id, estado_interno, evidence_due_by, creado_en
        FROM financial_disputes
        WHERE estado_interno IN ('ABIERTO', 'EN_INVESTIGACION', 'PENDIENTE_EVIDENCIA')
          AND evidence_due_by IS NOT NULL AND evidence_due_by <= ?
        ORDER BY evidence_due_by ASC LIMIT 100
        """,
        (deadline_limit,),
    )
    for row in _admin_repo._rows(cursor):
        key = f"disputa:{row.get('id')}"
        n, u = _registrar_alerta(
            cursor, run_id=run_id, alert_key=key, tipo="disputa_deadline_proximo",
            severidad="critical", contacto_id=row.get("contacto_id"),
            accion_recomendada="Disputa próxima a deadline — preparar evidencia",
            accion_disponible="financial.dispute.investigate",
            fuente="financial_disputes", fecha_evento=row.get("creado_en"),
            metadata={"deadline": row.get("evidence_due_by")},
        )
        stats["nuevas"] += int(n)
        stats["actualizadas"] += int(u)
    return stats


def _detectar_conflictos(cursor, run_id: str) -> Dict[str, int]:
    stats = {"nuevas": 0, "actualizadas": 0}
    if not _admin_repo.tabla_existe(cursor, "payment_conflicts"):
        return stats
    old_before = _iso_days_ago(_CONFLICT_OLD_DAYS)
    for sql, tipo, sev, params in (
        (
            """
            SELECT id, trabajo_id, estado_conflicto, bloqueo_financiero, responsable_codigo, created_at
            FROM payment_conflicts
            WHERE bloqueo_financiero = 1 AND estado_conflicto NOT IN ('CERRADO', 'RESUELTO')
            ORDER BY created_at ASC LIMIT 100
            """,
            "conflicto_bloqueante",
            "critical",
            (),
        ),
        (
            """
            SELECT id, trabajo_id, estado_conflicto, bloqueo_financiero, responsable_codigo, created_at
            FROM payment_conflicts
            WHERE estado_conflicto NOT IN ('CERRADO', 'RESUELTO') AND created_at < ?
            ORDER BY created_at ASC LIMIT 100
            """,
            "conflicto_antiguo",
            "high",
            (old_before,),
        ),
    ):
        cursor.execute(sql, params)
        for row in _admin_repo._rows(cursor):
            key = f"conflicto:{row.get('id')}"
            n, u = _registrar_alerta(
                cursor, run_id=run_id, alert_key=key, tipo=tipo, severidad=sev,
                contacto_id=row.get("trabajo_id"),
                accion_recomendada="Investigar y resolver conflicto financiero",
                accion_disponible="financial.conflict.resolve",
                fuente="payment_conflicts", fecha_evento=row.get("created_at"),
                metadata={"estado": row.get("estado_conflicto")},
            )
            stats["nuevas"] += int(n)
            stats["actualizadas"] += int(u)
    return stats


def _detectar_transfers(cursor, run_id: str) -> Dict[str, int]:
    stats = {"nuevas": 0, "actualizadas": 0}
    stuck_before = _iso_hours_ago(_TRANSFER_STUCK_HOURS)

    if _admin_repo.tabla_existe(cursor, "contactos_ruana"):
        cursor.execute(
            """
            SELECT id, estado_financiero, actualizado_en
            FROM contactos_ruana
            WHERE modo_pago = 'stripe' AND estado_financiero = 'TRANSFERENCIA_REVERTIDA'
            ORDER BY actualizado_en DESC LIMIT 100
            """
        )
        for row in _admin_repo._rows(cursor):
            key = f"transfer_revertida:{row.get('id')}"
            n, u = _registrar_alerta(
                cursor, run_id=run_id, alert_key=key, tipo="transferencia_revertida",
                severidad="critical", contacto_id=row.get("id"),
                accion_recomendada="Investigar transferencia revertida",
                accion_disponible="financial.reconciliation.execute",
                fuente="contactos_ruana", fecha_evento=row.get("actualizado_en"),
            )
            stats["nuevas"] += int(n)
            stats["actualizadas"] += int(u)

    if _admin_repo.tabla_existe(cursor, "financial_transfers"):
        cursor.execute(
            """
            SELECT id, contacto_id, estado, stripe_transfer_id, creado_en, actualizado_en
            FROM financial_transfers
            WHERE estado IN ('pending', 'processing', 'PENDING', 'PROCESSING')
              AND creado_en < ?
            ORDER BY creado_en ASC LIMIT 100
            """,
            (stuck_before,),
        )
        for row in _admin_repo._rows(cursor):
            key = f"transfer_atascada:{row.get('id')}"
            n, u = _registrar_alerta(
                cursor, run_id=run_id, alert_key=key, tipo="transferencia_atascada",
                severidad="high", contacto_id=row.get("contacto_id"),
                accion_recomendada="Transferencia atascada — revisar estado en Stripe",
                accion_disponible="financial.reconciliation.execute",
                fuente="financial_transfers", fecha_evento=row.get("creado_en"),
            )
            stats["nuevas"] += int(n)
            stats["actualizadas"] += int(u)
    return stats


def _detectar_ledger(cursor, run_id: str) -> Dict[str, int]:
    stats = {"nuevas": 0, "actualizadas": 0}
    if not _admin_repo.tabla_existe(cursor, "ledger_transactions"):
        return stats
    from core.repositories.financial_ledger_repo import FinancialLedgerRepo
    lrepo = FinancialLedgerRepo()
    desequilibrados = lrepo.listar_desequilibrados(cursor, 50)
    huerfanos = lrepo.listar_posted_sin_entries(cursor, 50)
    for row in desequilibrados:
        tid = row.get("ledger_transaction_id") or row.get("id")
        key = f"ledger_desequilibrio:{tid}"
        n, u = _registrar_alerta(
            cursor, run_id=run_id, alert_key=key, tipo="ledger_desequilibrio",
            severidad="critical", contacto_id=row.get("contacto_id"),
            accion_recomendada="Ledger desequilibrado — revisión humana obligatoria",
            accion_disponible="financial.ledger.reconcile",
            fuente="ledger_transactions", metadata=row,
        )
        stats["nuevas"] += int(n)
        stats["actualizadas"] += int(u)
    for row in huerfanos:
        tid = row.get("id") or row.get("ledger_transaction_id")
        key = f"ledger_huerfano:{tid}"
        n, u = _registrar_alerta(
            cursor, run_id=run_id, alert_key=key, tipo="ledger_huerfano",
            severidad="critical", contacto_id=row.get("contacto_id"),
            accion_recomendada="Transacción ledger sin entries — revisión humana",
            accion_disponible="financial.ledger.view",
            fuente="ledger_transactions", metadata=row,
        )
        stats["nuevas"] += int(n)
        stats["actualizadas"] += int(u)
    return stats


def _detectar_reconciliacion_y_discrepancias(cursor, run_id: str) -> Dict[str, int]:
    stats = {"nuevas": 0, "actualizadas": 0}
    if _admin_repo.tabla_existe(cursor, "financial_reconciliation"):
        cursor.execute(
            """
            SELECT id, contacto_id, tipo_discrepancia, estado_reconciliacion, detected_at
            FROM financial_reconciliation WHERE estado_reconciliacion = 'open'
            ORDER BY detected_at ASC LIMIT 100
            """
        )
        for row in _admin_repo._rows(cursor):
            key = f"discrepancia:{row.get('id')}"
            n, u = _registrar_alerta(
                cursor, run_id=run_id, alert_key=key, tipo="discrepancia_stripe_ruana",
                severidad="critical", contacto_id=row.get("contacto_id"),
                accion_recomendada="Revisar reconciliación y resolver discrepancia",
                accion_disponible="financial.reconciliation.resolve",
                fuente="financial_reconciliation", fecha_evento=row.get("detected_at"),
            )
            stats["nuevas"] += int(n)
            stats["actualizadas"] += int(u)
    if _admin_repo.tabla_existe(cursor, "financial_reconciliation_executions"):
        cursor.execute(
            """
            SELECT id, contacto_id, estado, creado_en
            FROM financial_reconciliation_executions
            WHERE estado IN ('pending', 'running', 'PENDING', 'RUNNING')
            ORDER BY creado_en ASC LIMIT 100
            """
        )
        for row in _admin_repo._rows(cursor):
            key = f"recon_pendiente:{row.get('id')}"
            n, u = _registrar_alerta(
                cursor, run_id=run_id, alert_key=key, tipo="reconciliacion_pendiente",
                severidad="medium", contacto_id=row.get("contacto_id"),
                accion_recomendada="Completar o resolver ejecución de reconciliación",
                accion_disponible="financial.reconciliation.resolve",
                fuente="financial_reconciliation_executions", fecha_evento=row.get("creado_en"),
            )
            stats["nuevas"] += int(n)
            stats["actualizadas"] += int(u)
    return stats


def calcular_metricas(db) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            kpis = _admin_repo.dashboard_kpis(cursor)
            alertas = _repo.contar_alertas_abiertas(cursor) if _repo.tabla_existe(cursor, "financial_alerts") else {}
            ultimo = _repo.ultimo_run(cursor, JOB_MONITORING_CYCLE) if _repo.tabla_existe(cursor, "financial_automation_runs") else None
        finally:
            conn.close()
    return {
        "pagos": {
            "pendientes": kpis.get("pagos_pendientes", 0),
            "confirmados": kpis.get("pagos_confirmados", 0),
            "bloqueados": kpis.get("operaciones_bloqueadas", 0),
        },
        "transfers": {
            "revertidas": kpis.get("transferencias_revertidas", 0),
        },
        "refunds": {
            "pendientes": kpis.get("refunds_pendientes", 0),
            "fallidos": kpis.get("refunds_fallidos", 0),
        },
        "disputas": {"abiertas": kpis.get("disputas_abiertas", 0)},
        "conflictos": {"abiertos": kpis.get("conflictos_abiertos", 0)},
        "reconciliacion": {"discrepancias_abiertas": kpis.get("discrepancias_abiertas", 0)},
        "ledger": {"tx_posted": kpis.get("ledger_tx_posted", 0)},
        "webhooks": {"fallidos": kpis.get("webhooks_fallidos", 0)},
        "alertas_abiertas": alertas,
        "ultima_ejecucion": ultimo,
    }


def ejecutar_reconciliacion_periodica(
    db,
    *,
    limit: int = _DEFAULT_RECON_LIMIT,
    actor: str = "cron",
    permiso: str = AUTOMATION_EXECUTE,
    stripe_fetcher: Optional[Dict[str, Callable]] = None,
) -> Dict[str, Any]:
    """Ejecuta lote de reconciliación con límite — solo observa, no mueve dinero."""
    return fras.ejecutar_lote(
        db, limit=limit, actor=actor, permiso_usado=permiso, stripe_fetcher=stripe_fetcher,
    )


def ejecutar_ciclo_monitoreo(
    db,
    *,
    actor: str = "cron",
    permiso: str = AUTOMATION_EXECUTE,
    recon_limit: int = _DEFAULT_RECON_LIMIT,
    holder: Optional[str] = None,
    incluir_reconciliacion: bool = True,
    stripe_fetcher: Optional[Dict[str, Callable]] = None,
) -> Dict[str, Any]:
    """Ciclo completo: lease → detectores → reconciliación opcional → métricas → auditoría."""
    run_id = str(uuid.uuid4())[:12]
    lease_holder = holder or f"worker-{run_id}"
    if not adquirir_lease(db, job_name=JOB_MONITORING_CYCLE, holder=lease_holder):
        return {
            "status": "skipped",
            "message": "Otro worker tiene el lease activo",
            "job_name": JOB_MONITORING_CYCLE,
        }

    errores: List[str] = []
    alertas_nuevas = 0
    alertas_actualizadas = 0
    detalle_detectores: Dict[str, Any] = {}
    recon_result: Optional[Dict[str, Any]] = None

    try:
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                _repo.insertar_run(cursor, run_id=run_id, job_name=JOB_MONITORING_CYCLE, actor=actor)
                audit.registrar(
                    db, cursor, actor=actor, permiso=permiso,
                    accion="automation_cycle_started", recurso_tipo="job",
                    recurso_id=JOB_MONITORING_CYCLE, idempotency_key=run_id,
                )
                conn.commit()
            finally:
                conn.close()

        detectores = [
            ("webhooks", _detectar_webhooks),
            ("refunds", _detectar_refunds),
            ("disputas", _detectar_disputas),
            ("conflictos", _detectar_conflictos),
            ("transfers", _detectar_transfers),
            ("ledger", _detectar_ledger),
            ("reconciliacion", _detectar_reconciliacion_y_discrepancias),
        ]
        for nombre, fn in detectores:
            try:
                with db._lock:
                    conn = db._connect()
                    try:
                        cursor = conn.cursor()
                        stats = fn(cursor, run_id)
                        conn.commit()
                    finally:
                        conn.close()
                detalle_detectores[nombre] = stats
                alertas_nuevas += int(stats.get("nuevas", 0))
                alertas_actualizadas += int(stats.get("actualizadas", 0))
            except Exception as e:
                errores.append(f"{nombre}: {str(e)[:200]}")
                detalle_detectores[nombre] = {"error": str(e)[:200]}

        if incluir_reconciliacion:
            try:
                recon_result = ejecutar_reconciliacion_periodica(
                    db, limit=recon_limit, actor=actor, permiso=permiso,
                    stripe_fetcher=stripe_fetcher,
                )
            except Exception as e:
                errores.append(f"reconciliacion: {str(e)[:200]}")
                recon_result = {"status": "error", "message": str(e)[:200]}

        metricas = calcular_metricas(db)
        if recon_result and recon_result.get("metricas"):
            metricas["reconciliacion_lote"] = recon_result["metricas"]

        estado = "SUCCESS" if not errores else ("PARTIAL" if alertas_nuevas or alertas_actualizadas else "FAILED")

        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                _repo.finalizar_run(
                    cursor, run_id,
                    estado=estado,
                    metricas=metricas,
                    errores=errores,
                    alertas_nuevas=alertas_nuevas,
                    alertas_actualizadas=alertas_actualizadas,
                    detalle={"detectores": detalle_detectores, "reconciliacion": recon_result},
                )
                audit.registrar(
                    db, cursor, actor=actor, permiso=permiso,
                    accion="automation_cycle_finished", recurso_tipo="run",
                    recurso_id=run_id,
                    metadata={"estado": estado, "alertas_nuevas": alertas_nuevas},
                    resultado="success" if estado != "FAILED" else "partial",
                )
                conn.commit()
            finally:
                conn.close()

        return {
            "status": "success",
            "run_id": run_id,
            "estado": estado,
            "alertas_nuevas": alertas_nuevas,
            "alertas_actualizadas": alertas_actualizadas,
            "errores": errores,
            "metricas": metricas,
            "reconciliacion": recon_result,
        }
    finally:
        liberar_lease(db, job_name=JOB_MONITORING_CYCLE, holder=lease_holder)


def obtener_resumen(db) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if not _repo.tabla_existe(cursor, "financial_automation_runs"):
                return {"status": "success", "automation_disponible": False}
            ultimo = _repo.ultimo_run(cursor, JOB_MONITORING_CYCLE)
            alertas = _repo.contar_alertas_abiertas(cursor)
            runs = _repo.listar_runs(cursor, limit=5)
        finally:
            conn.close()
    metricas = calcular_metricas(db)
    return {
        "status": "success",
        "automation_disponible": True,
        "ultima_ejecucion": ultimo,
        "alertas_abiertas": alertas,
        "metricas": metricas,
        "ejecuciones_recientes": runs,
    }


def listar_ejecuciones(db, *, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            items = _repo.listar_runs(cursor, limit=limit, offset=offset)
        finally:
            conn.close()
    return {"status": "success", "items": items, "pagination": {"limit": limit, "offset": offset}}


def obtener_ejecucion(db, run_id: str) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _repo.select_run(cursor, run_id)
        finally:
            conn.close()
    if not row:
        return {"status": "error", "message": "Ejecución no encontrada"}
    for field in ("metricas_json", "errores_json", "detalle_json"):
        if row.get(field):
            try:
                row[field.replace("_json", "")] = json.loads(row[field])
            except (TypeError, json.JSONDecodeError):
                row[field.replace("_json", "")] = {}
    return {"status": "success", "ejecucion": row}


def listar_alertas_persistidas(db, *, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if not _repo.tabla_existe(cursor, "financial_alerts"):
                return {"status": "success", "items": [], "pagination": {"limit": limit, "offset": offset, "total": 0}}
            items = _repo.listar_alertas_abiertas(cursor, limit=limit, offset=offset)
        finally:
            conn.close()
    return {
        "status": "success",
        "items": items,
        "pagination": {"limit": limit, "offset": offset, "total": len(items)},
        "generated_at": _utc_now(),
    }


def resolver_alerta_persistida(db, *, alert_key: str, actor: str, permiso: str = MONITORING_VIEW) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            ok = _repo.marcar_alerta_resuelta(cursor, alert_key, actor=actor)
            conn.commit()
        finally:
            conn.close()
    if not ok:
        return {"status": "error", "message": "Alerta no encontrada o ya resuelta"}
    return {"status": "success", "alert_key": alert_key}
