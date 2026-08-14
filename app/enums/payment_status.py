"""Payment lifecycle enums.

PaymentStatus — tracks where a single Razorpay transaction sits in its
lifecycle.  Used on the PaymentTransaction ORM model.

TransactionType — direction of the ledger entry.  CREDIT increases the
wallet balance; DEBIT decreases it (ride deduction, refund out, etc.).
"""

import enum


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"         # Order created, awaiting Checkout completion
    PROCESSING = "PROCESSING"   # Checkout done, signature verification in flight
    SUCCEEDED = "SUCCEEDED"     # Signature verified, wallet credited
    FAILED = "FAILED"           # Signature mismatch or Razorpay error
    REFUNDED = "REFUNDED"       # Amount returned to user


class TransactionType(str, enum.Enum):
    CREDIT = "CREDIT"   # Money added to wallet (top-up, refund, incentive)
    DEBIT = "DEBIT"     # Money removed from wallet (ride payment, penalty)
