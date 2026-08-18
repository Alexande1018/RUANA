"""Cliente Stripe de RUANA (Connect: separate charges and transfers)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional

from core.settings import get_settings

DEFAULT_STRIPE_API_VERSION = "2024-11-20.acacia"


@lru_cache(maxsize=1)
def _stripe_module():
    import stripe  # noqa: WPS433 — import lazy para entornos sin dependencia en tests aislados

    return stripe


def stripe_configured() -> bool:
    settings = get_settings()
    return bool(settings.stripe_secret_key and settings.stripe_webhook_secret)


def stripe_payments_enabled() -> bool:
    return os.environ.get("RUANA_STRIPE_PAYMENTS_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def get_stripe_api_version() -> str:
    return os.environ.get("STRIPE_API_VERSION", DEFAULT_STRIPE_API_VERSION).strip()


def configure_stripe() -> Optional[Any]:
    """Devuelve el módulo stripe configurado o None si no hay clave."""
    settings = get_settings()
    secret = (settings.stripe_secret_key or "").strip()
    if not secret:
        return None
    from core.runtime_environment import is_production, is_test_context
    from core.startup_validation import validate_stripe_mode_and_keys

    mode = (os.environ.get("RUANA_STRIPE_MODE") or "").strip().lower()
    if not mode and is_test_context():
        mode = "test"
    validate_stripe_mode_and_keys(
        stripe_mode=mode,
        stripe_secret_key=secret,
        production=is_production(),
    )
    stripe = _stripe_module()
    stripe.api_key = secret
    stripe.api_version = get_stripe_api_version()
    return stripe


def create_checkout_session(
    *,
    amount_cents: int,
    currency: str,
    contacto_id: int,
    success_url: str,
    cancel_url: str,
    customer_email: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    params: Dict[str, Any] = {
        "mode": "payment",
        "line_items": [
            {
                "price_data": {
                    "currency": currency.lower(),
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": f"Encargo RUANA #{contacto_id}",
                    },
                },
                "quantity": 1,
            }
        ],
        "payment_intent_data": {
            "metadata": {
                "contacto_id": str(contacto_id),
                "tipo": "encargo_ruana",
            },
        },
        "metadata": {
            "contacto_id": str(contacto_id),
            "tipo": "encargo_ruana",
        },
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if customer_email:
        params["customer_email"] = customer_email
    kwargs: Dict[str, Any] = {}
    if idempotency_key:
        kwargs["idempotency_key"] = idempotency_key
    session = stripe.checkout.Session.create(**params, **kwargs)
    return dict(session)


def create_transfer(
    *,
    amount_cents: int,
    currency: str,
    destination_account_id: str,
    contacto_id: int,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    params: Dict[str, Any] = {
        "amount": amount_cents,
        "currency": currency.lower(),
        "destination": destination_account_id,
        "metadata": {
            "contacto_id": str(contacto_id),
            "tipo": "pago_profesional_ruana",
        },
    }
    kwargs: Dict[str, Any] = {}
    if idempotency_key:
        kwargs["idempotency_key"] = idempotency_key
    transfer = stripe.Transfer.create(**params, **kwargs)
    return dict(transfer)


def create_connect_account(*, email: Optional[str] = None, country: str = "ES") -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    params: Dict[str, Any] = {
        "type": "express",
        "country": country,
        "capabilities": {
            "transfers": {"requested": True},
        },
    }
    if email:
        params["email"] = email
    account = stripe.Account.create(**params)
    return dict(account)


def create_account_link(*, account_id: str, refresh_url: str, return_url: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return dict(link)


def construct_webhook_event(payload: bytes, sig_header: str) -> Any:
    stripe = configure_stripe()
    settings = get_settings()
    if stripe is None or not settings.stripe_webhook_secret:
        raise RuntimeError("Stripe webhook no configurado")
    return stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.stripe_webhook_secret,
    )


def retrieve_transfer(transfer_id: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.Transfer.retrieve(transfer_id))


def retrieve_transfer_by_idempotency_metadata(
    *,
    contacto_id: int,
    idempotency_key: str,
    amount_cents: Optional[int] = None,
    currency: str = "eur",
    destination_account_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Recupera transferencia tras timeout reintentando create con la misma idempotency key.

    Stripe devuelve el mismo objeto si la transferencia ya fue creada.
    """
    if not idempotency_key or destination_account_id is None or amount_cents is None:
        return None
    try:
        return create_transfer(
            amount_cents=amount_cents,
            currency=currency,
            destination_account_id=destination_account_id,
            contacto_id=contacto_id,
            idempotency_key=idempotency_key,
        )
    except Exception:
        return None


def retrieve_account(account_id: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.Account.retrieve(account_id))


def create_refund(
    *,
    amount_cents: int,
    payment_intent_id: Optional[str] = None,
    charge_id: Optional[str] = None,
    reason: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Crea Refund en Stripe con idempotency key estable."""
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    if amount_cents <= 0:
        raise ValueError("amount_cents debe ser > 0")
    if not payment_intent_id and not charge_id:
        raise ValueError("payment_intent_id o charge_id obligatorio")
    params: Dict[str, Any] = {"amount": amount_cents}
    if payment_intent_id:
        params["payment_intent"] = payment_intent_id
    if charge_id:
        params["charge"] = charge_id
    if reason:
        params["reason"] = reason
    if metadata:
        params["metadata"] = {str(k): str(v) for k, v in metadata.items()}
    kwargs: Dict[str, Any] = {}
    if idempotency_key:
        kwargs["idempotency_key"] = idempotency_key
    refund = stripe.Refund.create(**params, **kwargs)
    return dict(refund)


def retrieve_refund_by_idempotency(
    *,
    amount_cents: int,
    payment_intent_id: Optional[str] = None,
    charge_id: Optional[str] = None,
    idempotency_key: str,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Recupera refund tras timeout reintentando con la misma idempotency key."""
    if not idempotency_key:
        return None
    try:
        return create_refund(
            amount_cents=amount_cents,
            payment_intent_id=payment_intent_id,
            charge_id=charge_id,
            reason=reason,
            idempotency_key=idempotency_key,
            metadata=metadata,
        )
    except Exception:
        return None


def retrieve_dispute(dispute_id: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.Dispute.retrieve(dispute_id))


def retrieve_charge(charge_id: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.Charge.retrieve(charge_id))


def retrieve_payment_intent(payment_intent_id: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.PaymentIntent.retrieve(payment_intent_id))


def retrieve_balance_transaction(balance_transaction_id: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.BalanceTransaction.retrieve(balance_transaction_id))


def update_dispute_evidence(
    dispute_id: str,
    *,
    evidence: Dict[str, str],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Actualiza evidencia de disputa (solo acción administrativa)."""
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    kwargs: Dict[str, Any] = {}
    if idempotency_key:
        kwargs["idempotency_key"] = idempotency_key
    safe = {k: str(v) for k, v in evidence.items() if v}
    result = stripe.Dispute.modify(dispute_id, evidence=safe, **kwargs)
    return dict(result)


def submit_dispute_evidence(dispute_id: str) -> Dict[str, Any]:
    """Envía evidencia a Stripe (solo acción administrativa)."""
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.Dispute.submit_evidence(dispute_id))


# --- Lecturas seguras FASE 07 (solo observación, sin mutación) ---

class StripeReadError(Exception):
    def __init__(self, code: str, message: str = "", http_status: int = 0):
        super().__init__(message or code)
        self.code = code
        self.http_status = http_status


def _classify_stripe_exception(exc: Exception) -> StripeReadError:
    msg = str(exc).lower()
    http_status = int(getattr(exc, "http_status", 0) or 0)
    if http_status == 404 or "no such" in msg or "not found" in msg:
        return StripeReadError("missing", str(exc)[:500], http_status)
    if http_status == 429 or "rate limit" in msg:
        return StripeReadError("rate_limit", str(exc)[:500], http_status)
    if http_status >= 500 or "timeout" in msg or "timed out" in msg:
        return StripeReadError("server_error", str(exc)[:500], http_status)
    if "connection" in msg or "network" in msg:
        return StripeReadError("unavailable", str(exc)[:500], http_status)
    return StripeReadError("error", str(exc)[:500], http_status)


def safe_stripe_read(fn, *args, **kwargs) -> Dict[str, Any]:
    """Ejecuta lectura Stripe y devuelve {status, data, error_code, http_status}."""
    try:
        data = fn(*args, **kwargs)
        return {"status": "ok", "data": data, "error_code": "", "http_status": 200}
    except StripeReadError as e:
        status = "missing" if e.code == "missing" else "pending" if e.code in ("rate_limit", "server_error") else "error"
        if e.code == "unavailable":
            status = "unavailable"
        return {"status": status, "data": None, "error_code": e.code, "http_status": e.http_status}
    except Exception as e:
        classified = _classify_stripe_exception(e)
        status = "missing" if classified.code == "missing" else "pending" if classified.code in ("rate_limit", "server_error") else "error"
        if classified.code == "unavailable":
            status = "unavailable"
        return {"status": status, "data": None, "error_code": classified.code, "http_status": classified.http_status}


def retrieve_payment_intent_safe(payment_intent_id: str) -> Dict[str, Any]:
    return safe_stripe_read(retrieve_payment_intent, payment_intent_id)


def retrieve_charge_safe(charge_id: str) -> Dict[str, Any]:
    return safe_stripe_read(retrieve_charge, charge_id)


def retrieve_balance_transaction_safe(balance_transaction_id: str) -> Dict[str, Any]:
    return safe_stripe_read(retrieve_balance_transaction, balance_transaction_id)


def retrieve_transfer_safe(transfer_id: str) -> Dict[str, Any]:
    return safe_stripe_read(retrieve_transfer, transfer_id)


def retrieve_account_safe(account_id: str) -> Dict[str, Any]:
    return safe_stripe_read(retrieve_account, account_id)


def retrieve_refund(refund_id: str) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    return dict(stripe.Refund.retrieve(refund_id))


def retrieve_refund_safe(refund_id: str) -> Dict[str, Any]:
    return safe_stripe_read(retrieve_refund, refund_id)


def retrieve_dispute_safe(dispute_id: str) -> Dict[str, Any]:
    return safe_stripe_read(retrieve_dispute, dispute_id)


def list_payment_intent_charges(payment_intent_id: str, *, limit: int = 10) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    result = stripe.Charge.list(payment_intent=payment_intent_id, limit=limit)
    return {"data": [dict(c) for c in (result.get("data") or [])]}


def list_payment_intent_charges_safe(payment_intent_id: str, *, limit: int = 10) -> Dict[str, Any]:
    return safe_stripe_read(list_payment_intent_charges, payment_intent_id, limit=limit)


def list_refunds(
    *,
    payment_intent_id: str = "",
    charge_id: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    stripe = configure_stripe()
    if stripe is None:
        raise RuntimeError("Stripe no configurado (falta STRIPE_SECRET_KEY)")
    params: Dict[str, Any] = {"limit": limit}
    if payment_intent_id:
        params["payment_intent"] = payment_intent_id
    if charge_id:
        params["charge"] = charge_id
    result = stripe.Refund.list(**params)
    return {"data": [dict(r) for r in (result.get("data") or [])]}


def list_refunds_safe(
    *,
    payment_intent_id: str = "",
    charge_id: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    return safe_stripe_read(list_refunds, payment_intent_id=payment_intent_id, charge_id=charge_id, limit=limit)
