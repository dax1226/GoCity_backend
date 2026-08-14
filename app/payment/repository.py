"""Payment-domain persistence layer.

All DB reads/writes for wallets and transactions go through these functions.
Nothing here raises HTTP exceptions — that is the router's job.

Public API
──────────
    get_or_create_wallet(db, user_id)           → UserWallet
    get_balance_rupees(db, user_id)             → float
    credit_wallet(db, wallet, amount_paise)     → UserWallet  (mutates + commits)
    debit_wallet(db, wallet, amount_paise)      → UserWallet  (mutates + commits)
    create_pending_transaction(...)             → PaymentTransaction
    mark_transaction_succeeded(...)             → PaymentTransaction
    mark_transaction_failed(...)                → PaymentTransaction
    get_transaction_by_order_id(...)            → PaymentTransaction | None
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.payment import PaymentTransaction, UserWallet
from app.enums.payment_status import PaymentStatus, TransactionType


# ─────────────────────────────────────────────────────────────────────────────
# Wallet helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_wallet(db: Session, user_id: int) -> UserWallet:
    """Return the user's wallet, creating one with zero balance if absent."""
    wallet = db.query(UserWallet).filter(UserWallet.user_id == user_id).first()
    if wallet is None:
        wallet = UserWallet(user_id=user_id, balance_paise=0, currency="INR")
        db.add(wallet)
        db.flush()  # assign wallet.id without a full commit
    return wallet


def get_balance_rupees(db: Session, user_id: int) -> float:
    """Return the user's wallet balance converted to rupees (float)."""
    wallet = db.query(UserWallet).filter(UserWallet.user_id == user_id).first()
    if wallet is None:
        return 0.0
    return wallet.balance_paise / 100.0


def credit_wallet(db: Session, wallet: UserWallet, amount_paise: int) -> UserWallet:
    """Add *amount_paise* to the wallet balance and persist.

    Commits the transaction so the updated balance is immediately visible to
    other requests.
    """
    wallet.balance_paise += amount_paise
    wallet.updated_at = datetime.utcnow()
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


def debit_wallet(db: Session, wallet: UserWallet, amount_paise: int) -> UserWallet:
    """Subtract *amount_paise* from the wallet balance and persist.

    Does NOT enforce a minimum balance — callers must check
    wallet.balance_paise >= amount_paise before calling this if they want to
    prevent overdrafts.
    """
    wallet.balance_paise -= amount_paise
    wallet.updated_at = datetime.utcnow()
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


# ─────────────────────────────────────────────────────────────────────────────
# Transaction helpers
# ─────────────────────────────────────────────────────────────────────────────

def create_pending_transaction(
    db: Session,
    wallet_id: int,
    amount_paise: int,
    razorpay_order_id: str,
    currency: str = "INR",
    booking_id: Optional[int] = None,
    description: Optional[str] = None,
    is_stub: bool = False,
) -> PaymentTransaction:
    """Insert a PENDING CREDIT transaction when a Razorpay order is created.

    The row is flushed (not committed) so the caller can bundle it with the
    wallet update in one atomic commit.
    """
    txn = PaymentTransaction(
        wallet_id=wallet_id,
        booking_id=booking_id,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=None,
        amount_paise=amount_paise,
        currency=currency,
        type=TransactionType.CREDIT,
        status=PaymentStatus.PENDING,
        description=description or "Wallet top-up",
        is_stub=1 if is_stub else 0,
    )
    db.add(txn)
    db.flush()
    return txn


def mark_transaction_succeeded(
    db: Session,
    txn: PaymentTransaction,
    razorpay_payment_id: str,
) -> PaymentTransaction:
    """Update the transaction to SUCCEEDED after signature verification."""
    txn.status = PaymentStatus.SUCCEEDED
    txn.razorpay_payment_id = razorpay_payment_id
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def mark_transaction_failed(
    db: Session,
    txn: PaymentTransaction,
) -> PaymentTransaction:
    """Mark the transaction FAILED (bad signature or Razorpay error)."""
    txn.status = PaymentStatus.FAILED
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def get_transaction_by_order_id(
    db: Session,
    razorpay_order_id: str,
) -> Optional[PaymentTransaction]:
    """Look up a transaction by its Razorpay order id.

    Used during verify to find the PENDING row created at order time so we can
    update its status and credit the wallet.
    """
    return (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.razorpay_order_id == razorpay_order_id)
        .order_by(PaymentTransaction.created_at.desc())
        .first()
    )
