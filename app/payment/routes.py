"""
Razorpay payment endpoints.

Two routes:
    POST /api/payment/razorpay/order   — create an order on Razorpay, return its id + amount
    POST /api/payment/razorpay/verify  — verify the signature returned by Razorpay Checkout

These are wired up but the frontend does not call them yet (intentionally
"don't use in current phase"). When you're ready to go live:

1. `pip install razorpay`
2. Add to GoCity_backend/.env:
       RAZORPAY_KEY_ID="rzp_test_..."
       RAZORPAY_KEY_SECRET="..."
3. From the Add Money screen, POST to /razorpay/order, open Checkout with the
   returned key + order_id, then POST the signed result to /razorpay/verify.

If RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are missing, both endpoints return a
deterministic stub so the rest of the app keeps working in dev.
"""

import hashlib
import hmac
import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.user.auth import get_current_user
from app.models import User


router = APIRouter()


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────
class CreateOrderRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in rupees (integer)")
    currency: str = "INR"


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int       # in paise (Razorpay returns paise)
    currency: str
    key_id: str
    is_stub: bool     # true when Razorpay keys are missing


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    amount: int = Field(..., gt=0, description="Amount in rupees (integer)")


class VerifyPaymentResponse(BaseModel):
    verified: bool
    credited_amount: int
    new_balance: int  # placeholder until the wallet model is added
    is_stub: bool


# ─────────────────────────────────────────────
# Razorpay client (lazy, optional)
# ─────────────────────────────────────────────
def _get_keys() -> tuple[str | None, str | None]:
    return os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")


def _get_client():
    """Lazy-import razorpay SDK. Returns None if package or keys missing."""
    key_id, key_secret = _get_keys()
    if not key_id or not key_secret:
        return None
    try:
        import razorpay  # type: ignore
    except ImportError:
        return None
    return razorpay.Client(auth=(key_id, key_secret))


def _verify_signature_local(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    """Manual HMAC-SHA256 verification — used when the razorpay SDK is not installed."""
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────
@router.post("/razorpay/order", response_model=CreateOrderResponse)
def create_order(
    payload: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Razorpay order so the mobile app can launch Checkout."""
    amount_paise = payload.amount * 100  # Razorpay works in paise
    key_id, _ = _get_keys()
    client = _get_client()

    # Stub mode — no real Razorpay call. Lets the frontend integrate against a
    # predictable response while the merchant account is being set up.
    if client is None:
        return CreateOrderResponse(
            order_id=f"order_stub_{uuid.uuid4().hex[:14]}",
            amount=amount_paise,
            currency=payload.currency,
            key_id=key_id or "rzp_test_stub",
            is_stub=True,
        )

    try:
        order = client.order.create(
            {
                "amount": amount_paise,
                "currency": payload.currency,
                "receipt": f"rcpt_{current_user.id}_{int(time.time())}",
                "payment_capture": 1,
            }
        )
    except Exception as e:  # razorpay.errors.BadRequestError etc.
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e}")

    return CreateOrderResponse(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=key_id,
        is_stub=False,
    )


@router.post("/razorpay/verify", response_model=VerifyPaymentResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify the Checkout callback signature and (later) credit the wallet."""
    _, key_secret = _get_keys()

    # Stub mode: always succeed so the frontend can test the happy path.
    if not key_secret:
        return VerifyPaymentResponse(
            verified=True,
            credited_amount=payload.amount,
            new_balance=0,  # wallet model not added yet
            is_stub=True,
        )

    client = _get_client()
    try:
        if client is not None:
            client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": payload.razorpay_order_id,
                    "razorpay_payment_id": payload.razorpay_payment_id,
                    "razorpay_signature": payload.razorpay_signature,
                }
            )
            ok = True
        else:
            ok = _verify_signature_local(
                payload.razorpay_order_id,
                payload.razorpay_payment_id,
                payload.razorpay_signature,
                key_secret,
            )
    except Exception:
        ok = False

    if not ok:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # TODO: When the wallet model is added, credit `payload.amount` to the
    # current user's balance here and return the new balance.
    return VerifyPaymentResponse(
        verified=True,
        credited_amount=payload.amount,
        new_balance=0,
        is_stub=False,
    )
