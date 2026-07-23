# Payment API Documentation

## Endpoints

- POST /payments/initialize
- GET /payments/callback
- POST /payments/webhook
- GET /payments/history
- GET /payments/status/<reference>
- GET /payments/invoice/<reference>

## POST /payments/initialize

Request JSON:

```json
{
  "game_id": 1,
  "duration_minutes": 60,
  "station_code": "station1"
}
```

Headers:

- Content-Type: application/json
- X-CSRF-Token: <token>
- Idempotency-Key: <uuid>

Response:

```json
{
  "ok": true,
  "data": {
    "reference": "GSX-...",
    "authorization_url": "https://checkout.paystack.com/...",
    "access_code": "...",
    "amount_kobo": 5000,
    "currency": "NGN",
    "status": "pending"
  }
}
```

## GET /payments/callback

- Verifies transaction status server-side.
- Never trusts callback parameters for final activation.
- Returns HTML result pages.

## POST /payments/webhook

Headers:

- X-Paystack-Signature: sha512 signature

Behavior:

- Verifies signature
- Applies replay detection
- Calls verify endpoint
- Activates session only after successful verification

## GET /payments/history

- Returns user-owned payment records.
- Supports `?format=json` for API output.

## GET /payments/status/<reference>

- Returns payment + activation state.
- Supports `?refresh=true` for extra verify refresh.

## GET /payments/invoice/<reference>

- Returns HTML invoice page for owned reference.
