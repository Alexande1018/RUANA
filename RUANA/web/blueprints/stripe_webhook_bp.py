"""Webhook Stripe (sin autenticación de sesión; verificación por firma)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import pago_service

stripe_webhook_bp = Blueprint("stripe_webhook", __name__)


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


@stripe_webhook_bp.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
  """
  POST /api/stripe/webhook
  Procesa eventos Stripe con verificación de firma.
  """
  payload = request.get_data()
  sig_header = request.headers.get("Stripe-Signature", "")
  if not sig_header:
    return jsonify({"status": "error", "message": "Falta cabecera Stripe-Signature"}), 400
  db = get_db()
  result = pago_service.procesar_webhook_stripe(db, payload, sig_header)
  if result.get("status") == "error":
    return jsonify(result), 400
  return jsonify(result), 200
