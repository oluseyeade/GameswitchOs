from __future__ import annotations

import logging
from typing import Any

from pkg.app.models.payment import Payment
from pkg.app.payment.services import PaymentError, PaymentService
from pkg.app.payment.utils import ReplayGuard, SupportsReplayGuard, json_dumps, verify_paystack_signature


class WebhookProcessor:
    def __init__(
        self,
        payment_service: PaymentService,
        secret_key: str,
        replay_guard: SupportsReplayGuard | None = None,
    ) -> None:
        self.payment_service = payment_service
        self.secret_key = secret_key
        self.replay_guard = replay_guard or ReplayGuard(ttl_seconds=900, max_items=8000)
        self.log = getattr(payment_service, "log", logging.getLogger("payments"))

    def _minimal_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        return {
            "event": payload.get("event"),
            "id": payload.get("id"),
            "data": {
                "id": data.get("id"),
                "reference": data.get("reference"),
                "status": data.get("status"),
                "amount": data.get("amount"),
                "currency": data.get("currency"),
                "paid_at": data.get("paid_at"),
                "channel": data.get("channel"),
                "customer": {
                    "email": customer.get("email"),
                },
            },
        }

    def process(self, *, raw_body: bytes, signature: str, payload: dict[str, Any]) -> tuple[bool, str, int]:
        if not verify_paystack_signature(raw_body, self.secret_key, signature):
            self.log.warning("Rejected Paystack webhook due to invalid signature")
            return False, "Invalid webhook signature", 401

        event = str(payload.get("event") or "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        reference = str(data.get("reference") or "")

        # Replay key includes event+reference+provider event id when available.
        provider_id = str(data.get("id") or payload.get("id") or "")
        replay_key = f"{event}:{reference}:{provider_id}"
        if self.replay_guard.seen(replay_key):
            self.log.info("Duplicate Paystack webhook ignored: event=%s reference=%s provider_id=%s", event, reference, provider_id)
            return True, "Duplicate webhook ignored", 200

        if not reference:
            return False, "Missing payment reference", 400

        try:
            payment = Payment.query.filter_by(reference=reference, is_deleted=False).first()
            if not payment:
                return False, "Unknown payment reference", 404

            payment.webhook_payload_json = json_dumps(self._minimal_webhook_payload(payload))
            self.log.info("Processing Paystack webhook: event=%s reference=%s provider_id=%s", event, reference, provider_id)

            if event == "charge.success":
                self.payment_service.verify_transaction(reference, trigger="webhook", allow_activation=True)
                return True, "Webhook processed", 200

            if event in {"charge.failed", "charge.abandoned"}:
                payment.status = "failed"
                self.payment_service._log_payment(
                    payment,
                    "payment_failed",
                    "Webhook reported failed payment",
                    severity="warning",
                    payload={"event": event},
                )
                from pkg.extensions import db

                db.session.commit()
                return True, "Failure webhook processed", 200

            self.payment_service._log_payment(
                payment,
                "webhook_received",
                "Webhook received for unsupported event",
                payload={"event": event},
            )
            from pkg.extensions import db

            db.session.commit()
            return True, "Webhook acknowledged", 200
        except PaymentError as exc:
            return False, str(exc), exc.status_code
