"""Payment Pydantic schemas (Razorpay).

Moved here from app/payment/routes.py during the folder restructure so the
router file only declares HTTP routes — request/response shapes live with
the rest of the schemas.
"""

from pydantic import BaseModel, Field


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
