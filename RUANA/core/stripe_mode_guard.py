"""Barrera Test/Live para Stripe (FASE 13A P0-1)."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from core.runtime_environment import is_production, is_test_context

_ALERT_TYPE = "stripe_livemode_mismatch"


def configured_stripe_mode() -> str:
    mode = (os.environ.get("RUANA_STRIPE_MODE") or "").strip().lower()
    if mode in ("test", "live"):
        return mode
    if is_test_context():
        return "test"
    if is_production():
        raise RuntimeError("RUANA_STRIPE_MODE no configurado en producción")
    return "test"


def event_livemode_bool(event: Any) -> Optional[bool]:
    raw = None
    if isinstance(event, dict):
        raw = event.get("livemode")
        if raw is None:
            data = event.get("data") or {}
            if isinstance(data, dict) and "object" in data:
                obj = data.get("object") or {}
                if isinstance(obj, dict):
                    raw = obj.get("livemode")
    elif hasattr(event, "livemode"):
        raw = getattr(event, "livemode", None)
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str) and raw.strip().lower() in ("true", "false"):
        return raw.strip().lower() == "true"
    return None


def validate_event_livemode(event: Any) -> Dict[str, Any]:
    """Valida livemode del evento contra RUANA_STRIPE_MODE. No registra secretos."""
    mode = configured_stripe_mode()
    live = event_livemode_bool(event)
    if live is None:
        return {"status": "success", "skipped": True, "reason": "livemode_no_presente"}

    expected_live = mode == "live"
    if bool(live) == expected_live:
        return {"status": "success", "livemode": live, "mode": mode}

    event_id = ""
    if hasattr(event, "id"):
        event_id = str(event.id or "")
    elif isinstance(event, dict):
        event_id = str(event.get("id") or "")

    return {
        "status": "error",
        "code": "stripe_livemode_mismatch",
        "message": "Evento Stripe incompatible con RUANA_STRIPE_MODE",
        "expected_mode": mode,
        "event_livemode": live,
        "event_id": event_id[:64],
        "alert_type": _ALERT_TYPE,
    }


def registrar_alerta_livemode(db, *, event_id: str, expected_mode: str, event_livemode: bool) -> None:
    """Persiste alerta idempotente por event_id (best-effort)."""
    try:
        from core.repositories.financial_automation_repo import FinancialAutomationRepo
        repo = FinancialAutomationRepo()
        key = f"stripe_livemode:{event_id or 'unknown'}"
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                if not repo.tabla_existe(cursor, "financial_alerts"):
                    return
                repo.upsert_alerta(
                    cursor,
                    alert_key=key,
                    tipo=_ALERT_TYPE,
                    severidad="critical",
                    contacto_id=None,
                    accion_recomendada="Revisar configuración RUANA_STRIPE_MODE y endpoint webhook",
                    accion_disponible=None,
                    fuente="stripe_webhook",
                    run_id="startup-guard",
                    metadata={
                        "expected_mode": expected_mode,
                        "event_livemode": event_livemode,
                        "event_id": event_id,
                    },
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass
