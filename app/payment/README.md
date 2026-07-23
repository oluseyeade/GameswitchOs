# Payment Module

This package provides a production-focused Paystack integration for GameSwitchOS.

Main entrypoint:

- `create_payment_blueprint(...)` in `app/payment/routes.py`

Key guarantees:

- Secret key never exposed to frontend.
- Callback params never trusted as final source of truth.
- Webhook signature verified.
- Duplicate and replay webhook events handled.
- Amount and currency verification enforced.
- Session activation only after trusted verification path.
