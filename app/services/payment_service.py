"""Payment service — orchestrates wallet credits, refunds, and settlement.

Placeholder. The Razorpay create-order / verify-signature plumbing lives in
app/payment/router.py and app/payment/service.py. This module is for the
flows that span beyond Razorpay: wallet credit on verified payment,
refunds on cancelled rides, and (later) payout to drivers.
"""
