"""Webhook Stripe (sin autenticación de sesión; verificación por firma)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.stripe_webhook_logging import correlation_id_from_headers, log_stripe_webhook
from core.services import pago_service
from web.financial_rate_limit import limit_stripe_webhook

stripe_webhook_bp = Blueprint("stripe_webhook", __name__)

_SIGNATURE_ERROR_CODES = frozenset({"signature_invalid"})
_CLIENT_ERROR_CODES = frozenset({"invalid_event", "stripe_livemode_mismatch"})


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _ingress_log_kwargs() -> dict:
    return {
        "path": request.path,
        "method": request.method,
        "content_type": (request.content_type or ""),
        "correlation_id": correlation_id_from_headers(request.headers),
    }


def _json_error(message: str, code: str | None = None) -> dict:
    body = {"status": "error", "message": message}
    if code:
        body["code"] = code
    return body


def _http_response_for_webhook_result(result: dict) -> tuple:
    if result.get("status") == "success":
        return jsonify(result), 200

    code = (result.get("code") or "").strip()
    if code in _SIGNATURE_ERROR_CODES:
        return jsonify(_json_error("Firma webhook inválida", "signature_invalid")), 400

    if code == "processing_error" or result.get("retry"):
        return jsonify(_json_error("Error interno del servidor", "processing_error")), 500

    if code in _CLIENT_ERROR_CODES:
        return jsonify(
            _json_error(result.get("message") or "Solicitud inválida", code or None)
        ), 400

    if result.get("status") == "error":
        return jsonify(_json_error(result.get("message") or "Solicitud inválida")), 400

    return jsonify(result), 200


@stripe_webhook_bp.route("/api/stripe/webhook", methods=["POST"])
@limit_stripe_webhook
def stripe_webhook():
    """
    POST /api/stripe/webhook
    Procesa eventos Stripe con verificación de firma.
    """
    ingress = _ingress_log_kwargs()
    payload = request.get_data()
    payload_len = len(payload) if payload is not None else 0
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        log_stripe_webhook(
            resultado="signature_rejected",
            payload_len=payload_len,
            has_stripe_signature=False,
            error_kind="missing_signature_header",
            **ingress,
        )
        return jsonify(_json_error("Solicitud inválida")), 400

    db = get_db()
    result = pago_service.procesar_webhook_stripe(
        db,
        payload,
        sig_header,
        log_kwargs=ingress,
    )
    return _http_response_for_webhook_result(result)
