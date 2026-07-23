# Payment Module Architecture

## Overview

The Paystack module is implemented with Flask Blueprint + service-layer orchestration and webhook-first payment finalization.

```mermaid
flowchart LR
  UI[Bootstrap Checkout UI] --> R1[/POST /payments/initialize/]
  R1 --> S1[PaymentService.initialize_transaction]
  S1 --> PG[PaystackGateway.initialize]
  PG --> PS[Paystack Checkout]
  PS --> CB[/GET /payments/callback/]
  PS --> WH[/POST /payments/webhook/]
  WH --> WP[WebhookProcessor]
  WP --> S2[PaymentService.verify_transaction]
  S2 --> DB[(PostgreSQL)]
  S2 --> ACT[activate_session_for_payment]
  ACT --> TUYA[TuyaService.station_power_on]
  ACT --> LEGACY[Legacy gaming_sessions]
  LEGACY --> TIMER[Session timer API]
```

## Components

- app/payment/routes.py: HTTP surface, auth checks, CSRF checks, rate limits.
- app/payment/services.py: business logic, Paystack calls, verification, activation.
- app/payment/webhook.py: signature validation, replay guard, webhook event processing.
- app/models/payment.py: payment and audit log entities.
- app/models/session.py: payment user/station/session entities.

## Design Principles

- Route handlers remain thin.
- Domain logic is isolated in PaymentService.
- Webhook drives final activation.
- Existing session control APIs are reused for countdown/timer lifecycle.
