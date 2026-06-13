"""Driver wallet ledger + driver-to-customer ratings.

The wallet is an append-only ledger: every row stores the signed amount
(positive = credit, negative = debit) and the running balance after the
transaction. The current balance is simply the balance_after of the most
recent row (or 0.0 with no rows).
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text

from app.core.database import Base

# Ledger transaction types (free-form String column for SQLite/Postgres parity):
#   RIDE_CREDIT       — online fare collected by GoCity, owed to the driver
#   ORDER_DEDUCTION   — GoCity commission deducted from a completed ride
#   INCENTIVE_CREDIT  — bonus/incentive added
#   PENALTY_DEDUCTION — policy violation fine
WALLET_TRANSACTION_TYPES = {
    "RIDE_CREDIT",
    "ORDER_DEDUCTION",
    "INCENTIVE_CREDIT",
    "PENALTY_DEDUCTION",
}


class DriverWalletTransaction(Base):
    __tablename__ = "driver_wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(32), nullable=False)
    amount = Column(Float, nullable=False)  # positive = credit, negative = debit
    balance_after = Column(Float, nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DriverCustomerRating(Base):
    __tablename__ = "driver_customer_ratings"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stars = Column(SmallInteger, nullable=False)  # 1–5
    tags = Column(String(255), nullable=True)  # comma-separated tag labels
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
