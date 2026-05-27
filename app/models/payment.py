"""Payment ORM models.

Placeholder — no wallet, transaction, or payment-method tables exist yet.
Razorpay-backed flows currently live in app/payment/router.py and credit
nothing on success (`new_balance` is hard-coded to 0).

When the wallet lands, define:
    class Wallet(Base): user_id, balance_paise, currency, updated_at
    class Transaction(Base): wallet_id, type, amount_paise, status, gateway_ref
and import them from app/models/__init__.py so create_all picks them up.
"""
