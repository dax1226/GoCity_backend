"""Payment lifecycle enum.

Placeholder — no payment-status column exists on the Booking or any wallet
model yet. Razorpay flows in app/payment/router.py currently signal success
via the boolean `verified` field on the verify response. When a wallet or
transactions table lands, switch those flows to use this enum.
"""

import enum


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
