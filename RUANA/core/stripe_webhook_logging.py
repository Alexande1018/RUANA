"""Logs estructurados seguros para webhook Stripe (sin secretos ni payload)."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ruana.stripe_webhook")

WEBHOOK_SECRET_ENV_VAR = "STRIPE_WEBHOOK_SECRET"

StripeWebhookResultado = str  # signature_rejected | signature_verified | processed | unsupported_event | processing_error


def log_stripe_webhook(
    *,
    resultado: StripeWebhookResultado,
    path: str = "",
    method: str = "",
    content_type: str = "",
    payload_len: int = 0,
    has_stripe_signature: bool = False,
    event_id: str = "",
    event_type: str = "",
    correlation_id: str = "",
    error_kind: str = "",
) -> None:
    """Emite un log JSON de una línea sin secretos, firmas ni payload."""
    payload: Dict[str, Any] = {
        "component": "stripe_webhook",
        "resultado": resultado,
        "path": path or "",
        "method": method or "",
        "content_type": content_type or "",
        "payload_len": int(payload_len or 0),
        "hasStripeSignature": bool(has_stripe_signature),
        "webhook_secret_env": WEBHOOK_SECRET_ENV_VAR,
    }
    if event_id:
        payload["event_id"] = str(event_id)[:64]
    if event_type:
        payload["event_type"] = str(event_type)[:128]
    if correlation_id:
        payload["correlation_id"] = str(correlation_id)[:128]
    if error_kind:
        payload["error_kind"] = str(error_kind)[:64]
    try:
        logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        logger.info(
            "stripe_webhook resultado=%s path=%s payload_len=%s",
            resultado,
            path,
            payload_len,
        )


def correlation_id_from_headers(headers: Any) -> str:
    """Extrae id de correlación de cabeceras comunes (Cloud Run / proxies)."""
    for key in (
        "X-Cloud-Trace-Context",
        "X-Request-ID",
        "X-Correlation-ID",
        "Traceparent",
    ):
        raw = headers.get(key) if hasattr(headers, "get") else None
        if raw:
            return str(raw).strip()[:128]
    return ""
