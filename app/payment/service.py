"""Payment-domain service helpers.

Stub. The Razorpay client construction (_get_client, _get_keys) and the
manual HMAC signature verification (_verify_signature_local) currently
live inline in app/payment/router.py. They will move here, alongside the
wallet-crediting flow, when the wallet model lands.

Cross-cutting payment orchestration (refunds, retries, settlement) lives
in app/services/payment_service.py.
"""
