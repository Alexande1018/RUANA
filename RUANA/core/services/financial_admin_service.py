"""Servicio del panel administrativo financiero (FASE 09). Solo lectura agregada + cierre de alertas."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.financial_admin_authorization import (
    AUDIT_VIEW,
    CONFLICTS_VIEW,
    DASHBOARD_VIEW,
    DISPUTES_VIEW,
    LEDGER_VIEW,
    PAYMENTS_VIEW,
    RECONCILIATION_VIEW,
    REFUNDS_VIEW,
    TRANSFERS_VIEW,
)
from core.repositories.financial_admin_repo import FinancialAdminRepo

_repo = FinancialAdminRepo()

_SENSITIVE_KEYS = frozenset({
    "stripe_secret", "secret_key", "api_key", "password", "token",
    "card_number", "cvc", "cvv", "pan", "last4", "fingerprint",
})
_CARD_PATTERN = re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b")
_SECRET_PATTERN = re.compile(r"(sk_(live|test)_[A-Za-z0-9]+|whsec_[A-Za-z0-9]+|rk_(live|test)_[A-Za-z0-9]+)")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _freshness_meta(ultima_fuente: Optional[str], stale_minutes: int = 30) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    generated = _utc_now_iso()
    freshness = "live"
    if ultima_fuente:
        try:
            ts = datetime.fromisoformat(str(ultima_fuente).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_min = (now - ts).total_seconds() / 60.0
            if age_min > stale_minutes:
                freshness = "stale"
        except (TypeError, ValueError):
            freshness = "unknown"
    return {
        "generated_at": generated,
        "data_freshness": freshness,
        "ultima_actualizacion_fuente": ultima_fuente,
    }


def _sanitize_value(val: Any) -> Any:
    if isinstance(val, dict):
        return _sanitize_record(val)
    if isinstance(val, list):
        return [_sanitize_value(v) for v in val]
    if isinstance(val, str):
        if _SECRET_PATTERN.search(val):
            return "[REDACTED]"
        if _CARD_PATTERN.search(val):
            return "[REDACTED_CARD]"
    return val


def _sanitize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in record.items():
        kl = str(k).lower()
        if kl in _SENSITIVE_KEYS or "secret" in kl or "password" in kl:
            continue
        out[k] = _sanitize_value(v)
    return out


def _sanitize_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_sanitize_record(i) for i in items]


def _paginated(
    db,
    *,
    list_fn,
    count_sql: str,
    count_params: tuple = (),
    limit: int,
    offset: int,
    freshness_source: Optional[str] = None,
    count_table: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    lim, off = _repo.clamp_pagination(limit, offset)
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            items = list_fn(cursor, limit=lim, offset=off)
            if count_sql and count_table and not _repo.tabla_existe(cursor, count_table):
                total = len(items)
            elif count_sql:
                total = _repo.count_query(cursor, count_sql, count_params)
            else:
                total = len(items)
        finally:
            conn.close()
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    meta = _freshness_meta(freshness_source)
    meta["query_duration_ms"] = elapsed_ms
    if elapsed_ms > 500:
        meta["slow_query"] = True
    return {
        "status": "success",
        "items": _sanitize_list(items),
        "pagination": {"limit": lim, "offset": off, "total": total},
        **meta,
    }


def obtener_dashboard(db) -> Dict[str, Any]:
    t0 = time.perf_counter()
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            kpis = _repo.dashboard_kpis(cursor)
            ultima_recon = _repo.ultima_reconciliacion(cursor)
        finally:
            conn.close()
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    meta = _freshness_meta(ultima_recon)
    meta["query_duration_ms"] = elapsed_ms
    kpi_items = []
    mapping = [
        ("pagos_pendientes", "pagos", PAYMENTS_VIEW, "contactos_ruana"),
        ("pagos_confirmados", "pagos", PAYMENTS_VIEW, "contactos_ruana"),
        ("dinero_retenido_cents", "pagos", PAYMENTS_VIEW, "contactos_ruana"),
        ("dinero_transferido_cents", "pagos", PAYMENTS_VIEW, "contactos_ruana"),
        ("refunds_pendientes", "refunds", REFUNDS_VIEW, "financial_refunds"),
        ("refunds_fallidos", "refunds", REFUNDS_VIEW, "financial_refunds"),
        ("disputas_abiertas", "disputas", DISPUTES_VIEW, "financial_disputes"),
        ("conflictos_abiertos", "conflictos", CONFLICTS_VIEW, "payment_conflicts"),
        ("discrepancias_abiertas", "reconciliacion", RECONCILIATION_VIEW, "financial_reconciliation"),
        ("webhooks_fallidos", "webhooks", AUDIT_VIEW, "stripe_webhook_events"),
        ("operaciones_bloqueadas", "pagos", PAYMENTS_VIEW, "contactos_ruana"),
        ("transferencias_revertidas", "transfers", TRANSFERS_VIEW, "contactos_ruana"),
        ("ledger_tx_posted", "ledger", LEDGER_VIEW, "ledger_transactions"),
    ]
    for key, seccion, permiso, fuente in mapping:
        if key not in kpis:
            continue
        kpi_items.append({
            "id": key,
            "valor": kpis[key],
            "seccion": seccion,
            "permiso": permiso,
            "fuente": fuente,
            "enlace": f"/admin#finanzas-{seccion}",
        })
    ledger_ok = True
    try:
        from core.services import financial_ledger_reconciliation_service as flrs
        bal = flrs.comprobar_equilibrio(db, limit=5)
        ledger_ok = bool(bal.get("ok"))
        if not ledger_ok:
            kpi_items.append({
                "id": "ledger_desequilibrado",
                "valor": len(bal.get("desequilibrados", [])) + len(bal.get("huerfanos", [])),
                "seccion": "ledger",
                "permiso": LEDGER_VIEW,
                "fuente": "ledger_transactions",
                "enlace": "/admin#finanzas-ledger",
                "alerta": True,
            })
    except Exception:
        ledger_ok = False
    automation = {}
    try:
        from core.services import financial_automation_service as fauto
        automation = fauto.obtener_resumen(db)
    except Exception:
        automation = {"automation_disponible": False}
    return {
        "status": "success",
        "kpis": kpi_items,
        "ledger_equilibrado": ledger_ok,
        "ultima_reconciliacion": ultima_recon,
        "automation": automation,
        **meta,
    }


def listar_alertas(db, *, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    lim, off = _repo.clamp_pagination(limit, offset)
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            from core.repositories.financial_automation_repo import FinancialAutomationRepo
            auto_repo = FinancialAutomationRepo()
            todas: List[Dict[str, Any]] = []
            if auto_repo.tabla_existe(cursor, "financial_alerts"):
                todas = auto_repo.listar_alertas_abiertas(cursor, limit=lim + off + 200, offset=0)
            keys = {a.get("alert_key") for a in todas}
            for gen in _repo.generar_alertas(cursor, limit=lim + off + 200):
                if gen.get("alert_key") not in keys:
                    todas.append(gen)
                    keys.add(gen.get("alert_key"))
        finally:
            conn.close()
    todas.sort(key=lambda a: (
        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.get("severidad", "low"), 9),
        str(a.get("fecha") or a.get("fecha_ultima_deteccion") or ""),
    ))
    page = todas[off: off + lim]
    meta = _freshness_meta(_utc_now_iso(), stale_minutes=5)
    return {
        "status": "success",
        "items": _sanitize_list(page),
        "pagination": {"limit": lim, "offset": off, "total": len(todas)},
        **meta,
    }


def resolver_alerta(
    db,
    *,
    alert_key: str,
    motivo: str,
    actor: str,
    permiso: str,
) -> Dict[str, Any]:
    motivo = (motivo or "").strip()
    if not motivo or len(motivo) < 5:
        return {"status": "error", "message": "motivo obligatorio (mínimo 5 caracteres)"}
    key = (alert_key or "").strip()
    if not key:
        return {"status": "error", "message": "alert_key inválido"}
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if _repo.alerta_resuelta(cursor, key):
                return {"status": "success", "message": "Alerta ya resuelta", "alert_key": key}
            contacto_id = None
            parts = key.split(":", 1)
            if len(parts) == 2 and parts[0] in (
                "transfer_revertida", "sin_pi", "disputa", "recon_pendiente",
            ):
                try:
                    cursor.execute(
                        "SELECT contacto_id FROM financial_disputes WHERE id = ?",
                        (parts[1],),
                    ) if parts[0] == "disputa" else None
                except Exception:
                    pass
                if parts[0] in ("transfer_revertida", "sin_pi"):
                    try:
                        contacto_id = int(parts[1])
                    except (TypeError, ValueError):
                        contacto_id = None
            rid = _repo.registrar_alerta_resolucion(
                cursor,
                alert_key=key,
                contacto_id=contacto_id,
                motivo=motivo,
                actor=actor,
                permiso=permiso,
            )
            from core.repositories.financial_automation_repo import FinancialAutomationRepo
            auto_repo = FinancialAutomationRepo()
            if auto_repo.tabla_existe(cursor, "financial_alerts"):
                auto_repo.marcar_alerta_resuelta(cursor, key, actor=actor)
            conn.commit()
        finally:
            conn.close()
    if not rid:
        return {"status": "error", "message": "No se pudo registrar resolución"}
    return {"status": "success", "alert_key": key, "resolucion_id": rid}


def listar_pagos(db, **kwargs) -> Dict[str, Any]:
    estado = (kwargs.get("estado") or "").strip()
    q = (kwargs.get("q") or "").strip()
    contacto_id = kwargs.get("contacto_id")
    where = ["modo_pago = 'stripe'"]
    params: list = []
    if estado:
        where.append("estado_financiero = ?")
        params.append(estado)
    if contacto_id:
        where.append("id = ?")
        params.append(int(contacto_id))
    if q:
        where.append("(stripe_payment_intent_id LIKE ? OR stripe_charge_id LIKE ? OR CAST(id AS TEXT) = ?)")
        params.extend([f"%{q}%", f"%{q}%", q])
    sql = f"SELECT COUNT(*) FROM contactos_ruana WHERE {' AND '.join(where)}"
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_pagos(
            c, limit=limit, offset=offset, estado=estado, contacto_id=contacto_id, q=q,
        ),
        count_sql=sql,
        count_params=tuple(params),
        count_table="contactos_ruana",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def listar_transfers(db, **kwargs) -> Dict[str, Any]:
    estado = (kwargs.get("estado") or "").strip()
    q = (kwargs.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if estado:
        where.append("estado = ?")
        params.append(estado)
    if q:
        where.append("(stripe_transfer_id LIKE ? OR CAST(contacto_id AS TEXT) = ?)")
        params.extend([f"%{q}%", q])
    sql = f"SELECT COUNT(*) FROM financial_transfers WHERE {' AND '.join(where)}" if _repo else ""
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_transfers(c, limit=limit, offset=offset, estado=estado, q=q),
        count_sql=sql,
        count_params=tuple(params),
        count_table="financial_transfers",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def listar_refunds(db, **kwargs) -> Dict[str, Any]:
    estado = (kwargs.get("estado") or "").strip()
    q = (kwargs.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if estado:
        where.append("estado = ?")
        params.append(estado)
    if q:
        where.append("(stripe_refund_id LIKE ? OR CAST(contacto_id AS TEXT) = ?)")
        params.extend([f"%{q}%", q])
    sql = f"SELECT COUNT(*) FROM financial_refunds WHERE {' AND '.join(where)}"
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_refunds(c, limit=limit, offset=offset, estado=estado, q=q),
        count_sql=sql,
        count_params=tuple(params),
        count_table="financial_refunds",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def listar_disputes(db, **kwargs) -> Dict[str, Any]:
    estado = (kwargs.get("estado") or "").strip()
    q = (kwargs.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if estado:
        where.append("estado_interno = ?")
        params.append(estado)
    if q:
        where.append("(stripe_dispute_id LIKE ? OR CAST(contacto_id AS TEXT) = ?)")
        params.extend([f"%{q}%", q])
    sql = f"SELECT COUNT(*) FROM financial_disputes WHERE {' AND '.join(where)}"
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_disputes(c, limit=limit, offset=offset, estado=estado, q=q),
        count_sql=sql,
        count_params=tuple(params),
        count_table="financial_disputes",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def listar_conflicts(db, **kwargs) -> Dict[str, Any]:
    estado = (kwargs.get("estado") or "").strip()
    q = (kwargs.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if estado:
        where.append("estado_conflicto = ?")
        params.append(estado)
    if q:
        where.append("(CAST(trabajo_id AS TEXT) = ? OR stripe_payment_intent_id LIKE ?)")
        params.extend([q, f"%{q}%"])
    sql = f"SELECT COUNT(*) FROM payment_conflicts WHERE {' AND '.join(where)}"
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_conflicts(c, limit=limit, offset=offset, estado=estado, q=q),
        count_sql=sql,
        count_params=tuple(params),
        count_table="payment_conflicts",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def listar_reconciliation(db, **kwargs) -> Dict[str, Any]:
    estado = (kwargs.get("estado") or "").strip()
    where = ["1=1"]
    params: list = []
    if estado:
        where.append("estado = ?")
        params.append(estado)
    sql = f"SELECT COUNT(*) FROM financial_reconciliation_executions WHERE {' AND '.join(where)}"
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            ultima = _repo.ultima_reconciliacion(cursor)
        finally:
            conn.close()
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_reconciliacion(c, limit=limit, offset=offset, estado=estado),
        count_sql=sql,
        count_params=tuple(params),
        count_table="financial_reconciliation_executions",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
        freshness_source=ultima,
    )


def listar_ledger(db, **kwargs) -> Dict[str, Any]:
    estado = (kwargs.get("estado") or "").strip()
    where = ["1=1"]
    params: list = []
    if estado:
        where.append("estado = ?")
        params.append(estado)
    sql = f"SELECT COUNT(*) FROM ledger_transactions WHERE {' AND '.join(where)}"
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_ledger(c, limit=limit, offset=offset, estado=estado),
        count_sql=sql,
        count_params=tuple(params),
        count_table="ledger_transactions",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def listar_webhooks(db, **kwargs) -> Dict[str, Any]:
    solo_fallidos = str(kwargs.get("solo_fallidos", "1")).lower() in ("1", "true", "yes")
    sql = ""
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if _repo.tabla_existe(cursor, "stripe_webhook_events"):
                if solo_fallidos:
                    wh_sql = _repo._stripe_webhook_failed_where(cursor)
                    sql = (
                        f"SELECT COUNT(*) FROM stripe_webhook_events WHERE {wh_sql}"
                        if wh_sql else ""
                    )
                else:
                    sql = "SELECT COUNT(*) FROM stripe_webhook_events"
        finally:
            conn.close()
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_webhooks(c, limit=limit, offset=offset, solo_fallidos=solo_fallidos),
        count_sql=sql,
        count_params=(),
        count_table="stripe_webhook_events",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def listar_audit(db, **kwargs) -> Dict[str, Any]:
    entidad = (kwargs.get("entidad") or "").strip()
    q = (kwargs.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if entidad:
        where.append("entidad = ?")
        params.append(entidad)
    if q:
        where.append("(CAST(entidad_id AS TEXT) = ? OR accion LIKE ?)")
        params.extend([q, f"%{q}%"])
    sql = f"SELECT COUNT(*) FROM audit_log WHERE {' AND '.join(where)}"
    return _paginated(
        db,
        list_fn=lambda c, limit, offset: _repo.listar_audit(c, limit=limit, offset=offset, entidad=entidad, q=q),
        count_sql=sql,
        count_params=tuple(params),
        count_table="audit_log",
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def obtener_operacion(db, contacto_id: int) -> Dict[str, Any]:
    detalle: Optional[Dict[str, Any]] = None
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            detalle = _repo.operacion_detalle(cursor, contacto_id)
            if detalle and detalle.get("contacto"):
                detalle["contacto"] = _sanitize_record(detalle["contacto"])
            if detalle:
                for key in ("transfers", "refunds", "disputes", "conflicts", "discrepancias", "reconciliaciones", "ledger", "webhooks"):
                    if key in detalle:
                        detalle[key] = _sanitize_list(detalle[key])
        finally:
            conn.close()
    if not detalle:
        return {"status": "error", "message": "Operación no encontrada"}
    meta = _freshness_meta(detalle.get("contacto", {}).get("actualizado_en"))
    return {"status": "success", "operacion": detalle, **meta}
