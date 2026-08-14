"""Payment-domain service layer.

All Razorpay client construction, HMAC verification, and wallet-crediting
orchestration lives here.  The router only handles HTTP concerns.

Public API
──────────
    get_razorpay_client()       → razorpay.Client | None
    create_razorpay_order(...)  → dict with order_id / amount / currency
    verify_razorpay_signature(...)  → bool
    is_stub_mode()              → bool  (True when keys are absent)
"""

import hashlib
import hmac
import time
from typing import Optional

from app.core.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Razorpay client — lazy, optional
# ─────────────────────────────────────────────────────────────────────────────

def is_stub_mode() -> bool:
    """Return True when Razorpay credentials are absent.

    In stub mode every payment endpoint returns a deterministic fake response
    so the mobile app and admin panel keep working without a live merchant
    account.
    """
    return not settings.razorpay_enabled


def get_razorpay_client():
    """Lazy-import the razorpay SDK and return an authenticated client.

    Returns None when:
      - RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET is missing, OR
      - the `razorpay` pip package is not installed.

    Callers must check for None and fall back to stub mode.
    """
    if not settings.razorpay_enabled:
        return None
    try:
        import razorpay  # type: ignore
    except ImportError:
        return None
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Order creation
# ─────────────────────────────────────────────────────────────────────────────

def create_razorpay_order(
    amount_rupees: int,
    currency: str,
    receipt: str,
) -> dict:
    """Create a Razorpay order and return the raw order dict.

    Amount is accepted in *rupees* and converted to paise internally because
    callers think in rupees (matches the API contract).

    Raises:
        RuntimeError: if called while in stub mode.
        Exception:    any razorpay SDK / network error (let the router decide
                      the HTTP status code).
    """
    client = get_razorpay_client()
    if client is None:
        raise RuntimeError("create_razorpay_order called in stub mode")

    return client.order.create(
        {
            "amount": amount_rupees * 100,  # paise
            "currency": currency,
            "receipt": receipt,
            "payment_capture": 1,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Signature verification
# ─────────────────────────────────────────────────────────────────────────────

def _verify_signature_hmac(
    order_id: str,
    payment_id: str,
    signature: str,
    secret: str,
) -> bool:
    """Manual HMAC-SHA256 check — used when the SDK is not installed."""
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_razorpay_signature(
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    """Verify the Razorpay Checkout callback signature.

    Tries the SDK first (preferred — maintained by Razorpay); falls back to
    the manual HMAC check if the SDK is absent.

    Returns False (rather than raising) on any verification failure so the
    router can return a clean 400 response.
    """
    key_secret = settings.razorpay_key_secret
    if not key_secret:
        # Stub mode — treat as verified so the frontend happy-path works.
        return True

    client = get_razorpay_client()
    try:
        if client is not None:
            client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
            return True
        # SDK not installed — verify manually.
        return _verify_signature_hmac(order_id, payment_id, signature, key_secret)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Receipt helper
# ─────────────────────────────────────────────────────────────────────────────

def build_receipt(user_id: int) -> str:
    """Generate a unique, human-readable Razorpay receipt string."""
    return f"rcpt_{user_id}_{int(time.time())}"
