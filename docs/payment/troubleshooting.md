# Troubleshooting Guide

## Payment stays pending

Checks:

- Verify webhook URL is reachable publicly.
- Confirm `X-Paystack-Signature` is validated with correct secret key.
- Confirm `/payments/status/<reference>?refresh=true` returns gateway status.

## Duplicate or replay webhook warnings

- Expected when Paystack retries delivery.
- Replay guard intentionally suppresses duplicate events.

## Session not activating after success

Checks:

- Inspect `payment_logs` for `session_activated`.
- Check Tuya credentials and device online state.
- Confirm gaming station is not already active.

## CSRF failures on initialize

- Ensure checkout page token is sent via `X-CSRF-Token`.
- Re-open checkout page to refresh stale session cookies.

## Rate-limit errors

- Too many requests from same client IP in a short window.
- Back off and retry.
