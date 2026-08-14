"""Razorpay payment endpoints.

Two routes
──────────
    POST /api/payment/razorpay/order
        Create a Razorpay order. The mobile app uses the returned key_id +
        order_id to open Razorpay Checkout.  A PENDING PaymentTransaction row
        is written immediately so we have a record even if the user abandons.

    POST /api/payment/razorpay/verify
        Verify the HMAC-SHA256 signature returned by Checkout. On success:
          - the PaymentTransaction is marked SUCCEEDED
          - the user's wallet is credited (paise)
          - new_balance (rupees) is returned to the caller

Going live checklist
────────────────────
    1.  pip install razorpay
    2.  Set in .env:
            RAZORPAY_KEY_ID=rzp_live_...
            RAZORPAY_KEY_SECRET=...
    3.  From the "Add Money" screen POST to /api/payment/razorpay/order,
        open Checkout with the returned key_id + order_id, then POST
        the signed callback to /api/payment/razorpay/verify.

Stub mode
─────────
    When RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are absent both endpoints
    return a deterministic fake response (is_stub=True) so the rest of the
    app keeps working during development.  Stub responses still write real
    rows to user_wallets and payment_transactions so the admin panel can
    display them.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.user.service import get_current_user
from app.models.user import User
from app.schemas.payment_schema import (
    CreateOrderRequest,
    CreateOrderResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from app.payment import service as payment_service
from app.payment import repository as payment_repo

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/payment/razorpay/order
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/razorpay/order", response_model=CreateOrderResponse)
def create_order(
    payload: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Razorpay order and record a PENDING transaction.

    amount is in *rupees* (integer). Razorpay receives the value in paise
    internally; the response also returns paise so the frontend doesn't need
    to convert.
    """
    amount_paise = payload.amount * 100
    stub = payment_service.is_stub_mode()

    # ── Stub mode ────────────────────────────────────────────────────────────
    if stub:
        order_id = f"order_stub_{uuid.uuid4().hex[:14]}"

        wallet = payment_repo.get_or_create_wallet(db, current_user.id)
        payment_repo.create_pending_transaction(
            db,
            wallet_id=wallet.id,
            amount_paise=amount_paise,
            razorpay_order_id=order_id,
            currency=payload.currency,
            description="Wallet top-up (stub)",
            is_stub=True,
        )
        db.commit()

        return CreateOrderResponse(
            order_id=order_id,
            amount=amount_paise,
            currency=payload.currency,
            key_id=settings.razorpay_key_id or "rzp_test_stub",
            is_stub=True,
        )

    # ── Live mode ─────────────────────────────────────────────────────────────
    receipt = payment_service.build_receipt(current_user.id)
    try:
        order = payment_service.create_razorpay_order(
            amount_rupees=payload.amount,
            currency=payload.currency,
            receipt=receipt,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {exc}")

    wallet = payment_repo.get_or_create_wallet(db, current_user.id)
    payment_repo.create_pending_transaction(
        db,
        wallet_id=wallet.id,
        amount_paise=amount_paise,
        razorpay_order_id=order["id"],
        currency=order["currency"],
        description="Wallet top-up",
        is_stub=False,
    )
    db.commit()

    return CreateOrderResponse(
        order_id=order["id"],
        amount=order["amount"],   # already in paise from Razorpay
        currency=order["currency"],
        key_id=settings.razorpay_key_id,
        is_stub=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/payment/razorpay/verify
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/razorpay/verify", response_model=VerifyPaymentResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify the Checkout callback signature and credit the user's wallet.

    Flow:
        1. Look up the PENDING transaction by razorpay_order_id.
        2. Verify the HMAC-SHA256 signature (or trust it in stub mode).
        3. Credit the wallet and mark the transaction SUCCEEDED.
        4. Return the new balance in rupees.

    A 404 is returned if no matching PENDING transaction exists — this guards
    against replaying an already-verified order.
    """
    stub = payment_service.is_stub_mode()

    # Locate the PENDING transaction written during /order
    txn = payment_repo.get_transaction_by_order_id(db, payload.razorpay_order_id)
    if txn is None:
        raise HTTPException(
            status_code=404,
            detail="No pending transaction found for this order id.",
        )

    # ── Signature verification ────────────────────────────────────────────────
    verified = payment_service.verify_razorpay_signature(
        order_id=payload.razorpay_order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
    )

    if not verified:
        payment_repo.mark_transaction_failed(db, txn)
        raise HTTPException(status_code=400, detail="Invalid payment signature.")

    # ── Credit wallet ─────────────────────────────────────────────────────────
    wallet = payment_repo.get_or_create_wallet(db, current_user.id)
    payment_repo.mark_transaction_succeeded(db, txn, payload.razorpay_payment_id)
    wallet = payment_repo.credit_wallet(db, wallet, txn.amount_paise)

    new_balance_rupees = round(wallet.balance_paise / 100, 2)

    return VerifyPaymentResponse(
        verified=True,
        credited_amount=payload.amount,          # rupees, as sent by the client
        new_balance=new_balance_rupees,
        is_stub=stub,
    )
