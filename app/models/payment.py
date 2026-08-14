"""Payment ORM models.

Two tables:

    user_wallets
        One row per user. Stores the running balance in *paise* (₹1 = 100 paise)
        so we never do floating-point arithmetic on money. The balance is the
        source of truth; it is updated atomically whenever a transaction row is
        inserted.

    payment_transactions
        Append-only ledger of every payment event — Razorpay order creation,
        successful verification, and future refunds. Each row carries:
          - the Razorpay order / payment ids for reconciliation
          - the amount_paise and the direction (CREDIT / DEBIT)
          - a PaymentStatus so the frontend can show "Pending" / "Paid" / etc.
          - an optional booking_id for ride-payment linkage (nullable because
            wallet top-ups are not tied to a booking)

Usage
─────
    from app.models.payment import UserWallet, PaymentTransaction
    from app.enums.payment_status import PaymentStatus, TransactionType
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.enums.payment_status import PaymentStatus, TransactionType


class UserWallet(Base):
    """One wallet per user.  Balance is stored in *paise* (integer) to avoid
    floating-point rounding errors on monetary values."""

    __tablename__ = "user_wallets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_wallet"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Balance in paise.  ₹100 = 10000 paise.
    balance_paise = Column(BigInteger, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="wallet")
    transactions = relationship(
        "PaymentTransaction",
        back_populates="wallet",
        order_by="PaymentTransaction.created_at.desc()",
    )


class PaymentTransaction(Base):
    """Immutable record of every payment event.

    A row is written on:
      - order creation  (status=PENDING,  razorpay_payment_id=None)
      - successful verify (status=SUCCEEDED, razorpay_payment_id filled in)
      - failed verify   (status=FAILED)
      - future: refund  (status=REFUNDED,  type=DEBIT)
    """

    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(
        Integer,
        ForeignKey("user_wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional: link to the booking this payment covers.
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Razorpay identifiers — order_id is set on creation; payment_id on verify.
    razorpay_order_id = Column(String(64), nullable=True, index=True)
    razorpay_payment_id = Column(String(64), nullable=True)

    # Amount in paise.  Always positive; direction is encoded by type.
    amount_paise = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")

    type = Column(Enum(TransactionType), nullable=False, default=TransactionType.CREDIT)
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)

    # Human-readable note — e.g. "Wallet top-up", "Ride payment", "Refund"
    description = Column(String(255), nullable=True)

    # True when both Razorpay keys were absent at transaction time (dev/test mode).
    is_stub = Column(Integer, nullable=False, default=0)  # 0/1 SQLite-safe bool

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    wallet = relationship("UserWallet", back_populates="transactions")
