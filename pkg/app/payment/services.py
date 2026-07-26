from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from flask import current_app

from pkg.app.models.payment import Payment, PaymentLog
from pkg.app.models.session import GamingStation, PaymentGamingSession, PaymentUser
from pkg.app.payment.utils import generate_reference, json_dumps, kobo_from_naira, mask_email, sanitize_for_logs
from pkg.extensions import db


def _utc_now_naive() -> datetime:
    # Keep DB-compatible naive UTC timestamps while avoiding datetime.utcnow().
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PaymentError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class LegacyModels:
    User: Any
    Game: Any
    Payment: Any
    GamingSession: Any


class PaystackGateway:
    def __init__(self, secret_key: str, base_url: str = "https://api.paystack.co") -> None:
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = int(current_app.config.get("PAYSTACK_TIMEOUT_SECONDS", 15))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def _request_with_retry(self, *, method: str, path: str, data: str | None = None) -> dict[str, Any]:
        retries = int(current_app.config.get("PAYSTACK_MAX_RETRIES", 3))
        max_retries = max(retries, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=f"{self.base_url}{path}",
                    headers=self._headers(),
                    data=data,
                    timeout=self.timeout,
                )

                try:
                    parsed = response.json() if response.content else {}
                except ValueError as parse_error:
                    status_prefix = f"HTTP {response.status_code} " if getattr(response, "status_code", None) else ""
                    detail = (getattr(response, "text", "") or "").strip()
                    current_app.logger.warning(
                        "Paystack response could not be decoded as JSON for %s%s: %s",
                        status_prefix,
                        path,
                        detail[:200] if detail else "empty-body",
                    )
                    raise PaymentError(
                        "Paystack response could not be decoded as JSON. Please verify your Paystack gateway configuration and try again later.",
                        status_code=502,
                    ) from parse_error

                # Retry transient gateway/network pressure.
                if response.status_code in {408, 409, 425, 429, 500, 502, 503, 504} and attempt < max_retries:
                    time.sleep(min(2 ** (attempt - 1), 5))
                    continue

                if response.status_code >= 400 or not parsed.get("status"):
                    message = parsed.get("message") or "Paystack request failed"
                    raise PaymentError(message, status_code=502)

                return parsed["data"]
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                time.sleep(min(2 ** (attempt - 1), 5))

        if last_error:
            raise PaymentError("Paystack request failed due to network error", status_code=502) from last_error
        raise PaymentError("Paystack request failed", status_code=502)

    def initialize_transaction(
        self,
        *,
        email: str,
        amount_kobo: int,
        reference: str,
        callback_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "email": email,
            "amount": amount_kobo,
            "currency": "NGN",
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        return self._request_with_retry(
            method="POST",
            path="/transaction/initialize",
            data=json_dumps(payload),
        )

    def verify_transaction(self, reference: str) -> dict[str, Any]:
        return self._request_with_retry(
            method="GET",
            path=f"/transaction/verify/{reference}",
        )


class PaymentService:
    def __init__(
        self,
        *,
        legacy_models: LegacyModels,
        tuya_service: Any,
        event_bus: Any,
    ) -> None:
        self.legacy = legacy_models
        self.tuya_service = tuya_service
        self.event_bus = event_bus
        self.log = logging.getLogger("payments")

    def _minimal_verify_payload(self, verified: dict[str, Any]) -> dict[str, Any]:
        customer = verified.get("customer") if isinstance(verified.get("customer"), dict) else {}
        return {
            "id": verified.get("id"),
            "reference": verified.get("reference"),
            "status": verified.get("status"),
            "amount": verified.get("amount"),
            "currency": verified.get("currency"),
            "paid_at": verified.get("paid_at"),
            "gateway_response": verified.get("gateway_response"),
            "channel": verified.get("channel"),
            "customer": {
                "email": mask_email(str(customer.get("email") or "")),
            },
        }

    def _gateway(self) -> PaystackGateway:
        secret = current_app.config.get("PAYSTACK_SECRET_KEY", "")
        if not secret:
            raise PaymentError("Paystack secret key is not configured", status_code=503)
        return PaystackGateway(secret_key=secret, base_url=current_app.config.get("PAYSTACK_BASE_URL", "https://api.paystack.co"))

    def _normalize_payment_status(self, status: str | None) -> str:
        value = str(status or "").strip().lower()
        return value or "unknown"

    def _effective_payment_status(self, payment: Payment) -> str:
        normalized = self._normalize_payment_status(payment.status)
        gateway_status = self._normalize_payment_status(payment.gateway_status)
        if normalized in {"completed", "success"}:
            return "completed"
        if normalized == "success_pending_webhook" and gateway_status == "success":
            return "completed"
        if normalized == "pending" and gateway_status == "success":
            return "completed"
        return normalized or "unknown"

    def _payment_status_label(self, status: str | None) -> str:
        normalized = self._normalize_payment_status(status)
        if normalized in {"completed", "success"}:
            return "Completed"
        if normalized == "success_pending_webhook":
            return "Completed"
        if normalized == "pending":
            return "Pending"
        if normalized == "failed":
            return "Failed"
        if normalized == "abandoned":
            return "Abandoned"
        if normalized == "refunded":
            return "Refunded"
        return normalized.replace("_", " ").title()

    def _log_payment(
        self,
        payment: Payment,
        event_type: str,
        message: str,
        *,
        severity: str = "info",
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
        remote_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        db.session.add(
            PaymentLog(
                payment_id=payment.id,
                reference=payment.reference,
                event_type=event_type,
                message=message,
                severity=severity,
                payload_json=json_dumps(payload or {}),
                request_id=request_id,
                remote_ip=remote_ip,
                user_agent=(user_agent or "")[:255] or None,
            )
        )

        log_payload = {
            "event": event_type,
            "reference": payment.reference,
            "payment_id": payment.id,
            "severity": severity,
            "message": message,
        }
        if payload:
            log_payload["payload"] = sanitize_for_logs(payload)
        getattr(self.log, "warning" if severity in {"warning", "error"} else "info")(json_dumps(log_payload))

    def _station_to_switch(self, station_code: str) -> str:
        key = station_code.strip().lower()
        if key in {"station1", "plug-001", "switch1", "1"}:
            return "station1"
        if key in {"station2", "plug-002", "switch2", "2"}:
            return "station2"
        raise PaymentError("Invalid station code", status_code=400)

    def _station_to_legacy_plug(self, station_code: str) -> str:
        station = self._station_to_switch(station_code)
        return "plug-001" if station == "station1" else "plug-002"

    def ensure_payment_user(self, legacy_user: Any) -> PaymentUser:
        entity = PaymentUser.query.filter_by(legacy_user_id=legacy_user.id).first()
        if entity:
            return entity

        entity = PaymentUser(
            legacy_user_id=legacy_user.id,
            email=legacy_user.email,
            full_name=legacy_user.full_name,
            phone=getattr(legacy_user, "phone", None),
            is_active=bool(getattr(legacy_user, "is_active", True)),
        )
        db.session.add(entity)
        db.session.flush()
        return entity

    def ensure_default_stations(self) -> None:
        defaults = [
            ("station1", "Gaming Station 1", "switch_1", "branch1"),
            ("station2", "Gaming Station 2", "switch_2", "branch2"),
        ]
        changed = False
        for code, name, switch_code, branch in defaults:
            row = GamingStation.query.filter_by(code=code).first()
            if row:
                continue
            db.session.add(
                GamingStation(
                    code=code,
                    name=name,
                    tuya_switch_code=switch_code,
                    branch=branch,
                    is_active=True,
                )
            )
            changed = True
        if changed:
            db.session.commit()

    def initialize_transaction(
        self,
        *,
        legacy_user: Any,
        game_id: int,
        duration_minutes: int,
        station_code: str,
        callback_url: str,
        request_id: str,
        remote_ip: str,
        user_agent: str,
    ) -> dict[str, Any]:
        if duration_minutes < 10:
            raise PaymentError("Minimum duration is 10 minutes")

        previous_log = (
            PaymentLog.query.filter_by(request_id=request_id, event_type="payment_created")
            .order_by(PaymentLog.created_at.desc())
            .first()
        )
        if previous_log:
            existing = Payment.query.filter_by(id=previous_log.payment_id, is_deleted=False).first()
            if existing and existing.status in {"initialized", "pending", "success_pending_webhook"}:
                self._log_payment(
                    existing,
                    "duplicate_payment",
                    "Duplicate initialize request reused existing pending payment",
                    severity="warning",
                    payload={"request_id": request_id},
                    request_id=request_id,
                    remote_ip=remote_ip,
                    user_agent=user_agent,
                )
                db.session.commit()
                return {
                    "reference": existing.reference,
                    "authorization_url": existing.authorization_url,
                    "access_code": existing.access_code,
                    "amount_kobo": existing.amount_kobo,
                    "currency": existing.currency,
                    "status": existing.status,
                }

        game = db.session.get(self.legacy.Game, game_id)
        if not game or not getattr(game, "is_active", False):
            raise PaymentError("Selected game is unavailable", status_code=404)

        station = (
            GamingStation.query.with_for_update()
            .filter_by(code=station_code, is_active=True, is_deleted=False)
            .first()
        )
        if not station:
            raise PaymentError(
                f"Gaming station '{station_code}' does not exist or is currently inactive", status_code=404
            )

        if (
            getattr(legacy_user, "role", "user") != "superadmin"
            and getattr(legacy_user, "branch", None)
            and station.branch
            and str(station.branch) != str(legacy_user.branch)
        ):
            self.log.warning(
                json_dumps(
                    {
                        "event": "station_branch_mismatch",
                        "user_id": legacy_user.id,
                        "user_branch": getattr(legacy_user, "branch", None),
                        "station_code": station.code,
                        "station_branch": station.branch,
                        "reason": f"Station {station.code} ({station.branch}) does not belong to user's branch ({legacy_user.branch})",
                    }
                )
            )
            raise PaymentError(
                f"Selected station '{station.name}' belongs to branch '{station.branch}' and is not available for your branch ('{legacy_user.branch}')",
                status_code=403,
            )

        existing_active = PaymentGamingSession.query.filter_by(
            station_id=station.id, status="active", is_deleted=False
        ).first()
        if existing_active:
            self.log.warning(
                json_dumps(
                    {
                        "event": "station_already_occupied",
                        "user_id": legacy_user.id,
                        "station_code": station.code,
                        "active_session_id": existing_active.id,
                        "reason": "Station is already occupied by an active gaming session",
                    }
                )
            )
            raise PaymentError(
                f"Selected station '{station.name}' is currently occupied by an active gaming session", status_code=409
            )

        payment_user = self.ensure_payment_user(legacy_user)

        amount_naira = float(game.price_per_hour) * (duration_minutes / 60)
        amount_kobo = kobo_from_naira(amount_naira)
        reference = generate_reference(prefix="GSX")

        payment_session = PaymentGamingSession(
            user_id=payment_user.id,
            station_id=station.id,
            game_id=game.id,
            branch=legacy_user.branch,
            duration_minutes=duration_minutes,
            amount_kobo=amount_kobo,
            currency="NGN",
            status="pending",
            payment_reference=reference,
        )
        db.session.add(payment_session)
        db.session.flush()

        payment = Payment(
            reference=reference,
            provider="paystack",
            user_id=payment_user.id,
            payment_session_id=payment_session.id,
            amount_kobo=amount_kobo,
            expected_amount_kobo=amount_kobo,
            currency="NGN",
            status="initialized",
            metadata_json=json_dumps(
                {
                    "legacy_user_id": legacy_user.id,
                    "game_id": game.id,
                    "duration_minutes": duration_minutes,
                    "station_code": station.code,
                    "request_id": request_id,
                }
            ),
        )
        db.session.add(payment)
        db.session.flush()

        metadata = {
            "reference": reference,
            "legacy_user_id": legacy_user.id,
            "station_code": station.code,
            "duration_minutes": duration_minutes,
            "game_id": game.id,
        }

        gateway = self._gateway()
        data = gateway.initialize_transaction(
            email=legacy_user.email,
            amount_kobo=amount_kobo,
            reference=reference,
            callback_url=callback_url,
            metadata=metadata,
        )

        payment.access_code = data.get("access_code")
        payment.authorization_url = data.get("authorization_url")
        payment.status = "pending"

        self._log_payment(
            payment,
            "payment_created",
            "Payment transaction initialized",
            payload={"amount_kobo": amount_kobo, "user": mask_email(legacy_user.email)},
            request_id=request_id,
            remote_ip=remote_ip,
            user_agent=user_agent,
        )

        db.session.commit()

        return {
            "reference": reference,
            "authorization_url": payment.authorization_url,
            "access_code": payment.access_code,
            "amount_kobo": amount_kobo,
            "currency": payment.currency,
            "status": payment.status,
        }

    def verify_transaction(self, reference: str, *, trigger: str, allow_activation: bool) -> Payment:
        payment = Payment.query.filter_by(reference=reference, is_deleted=False).first()
        if not payment:
            raise PaymentError("Transaction not found", status_code=404)

        payment.verify_attempts += 1
        gateway = self._gateway()
        verified = gateway.verify_transaction(reference)

        self._log_payment(
            payment,
            "payment_verify_request",
            "Paystack verification request received",
            payload={"trigger": trigger, "reference": reference},
            request_id=str(uuid.uuid4()),
        )

        payment.provider_transaction_id = str(verified.get("id") or "") or payment.provider_transaction_id
        payment.gateway_status = str(verified.get("status") or "").lower() or payment.gateway_status
        payment.callback_payload_json = json_dumps(self._minimal_verify_payload(verified))
        payment.verified_at = _utc_now_naive()

        amount_kobo = int(verified.get("amount") or 0)
        currency = str(verified.get("currency") or "").upper()
        provider_status = str(verified.get("status") or "").lower()

        if amount_kobo != payment.expected_amount_kobo or currency != payment.currency:
            payment.status = "failed"
            self._log_payment(
                payment,
                "fraud_attempt",
                "Payment verification mismatch detected",
                severity="error",
                payload={
                    "expected_amount_kobo": payment.expected_amount_kobo,
                    "received_amount_kobo": amount_kobo,
                    "expected_currency": payment.currency,
                    "received_currency": currency,
                    "trigger": trigger,
                },
            )
            db.session.commit()
            raise PaymentError("Payment verification mismatch", status_code=409)

        if provider_status == "success":
            if self._normalize_payment_status(payment.status) in {"completed", "success"}:
                self._log_payment(
                    payment,
                    "duplicate_payment",
                    "Duplicate verification ignored for already successful payment",
                    severity="warning",
                    payload={"trigger": trigger},
                )
                db.session.commit()
                return payment

            payment.amount_kobo = amount_kobo
            payment.status = "completed" if trigger == "webhook" else "success_pending_webhook"
            paid_at = verified.get("paid_at")
            if paid_at:
                try:
                    payment.paid_at = datetime.fromisoformat(str(paid_at).replace("Z", "+00:00"))
                    if payment.paid_at.tzinfo is not None:
                        payment.paid_at = payment.paid_at.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    payment.paid_at = _utc_now_naive()
            else:
                payment.paid_at = _utc_now_naive()

            self._log_payment(
                payment,
                "payment_verification",
                "Payment verification successful",
                payload={"trigger": trigger, "amount_kobo": amount_kobo},
            )

            if trigger == "webhook":
                current_app.logger.info(
                    "Paystack charge.success verified for reference=%s; payment marked completed",
                    payment.reference,
                )

            if allow_activation and trigger == "webhook":
                self.activate_session_for_payment(payment)

            db.session.commit()
            return payment

        payment.status = "failed"
        self._log_payment(
            payment,
            "verification_failed",
            "Payment verification returned non-success status",
            severity="warning",
            payload={"trigger": trigger, "gateway_status": provider_status},
        )
        db.session.commit()
        return payment

    def activate_session_for_payment(self, payment: Payment) -> None:
        session_row = (
            PaymentGamingSession.query.with_for_update()
            .filter_by(id=payment.payment_session_id, is_deleted=False)
            .first()
        )
        if not session_row:
            raise PaymentError("Linked session not found", status_code=404)

        if session_row.status == "active":
            return

        if session_row.status in {"ended", "cancelled", "failed"}:
            raise PaymentError("Session cannot be activated in current status", status_code=409)

        payment_user = db.session.get(PaymentUser, payment.user_id)
        if not payment_user:
            raise PaymentError("Payment user not found", status_code=404)

        legacy_user = db.session.get(self.legacy.User, payment_user.legacy_user_id)
        if not legacy_user:
            raise PaymentError("Legacy user account no longer exists", status_code=404)

        station = (
            GamingStation.query.with_for_update()
            .filter_by(id=session_row.station_id, is_active=True, is_deleted=False)
            .first()
        )
        if not station:
            raise PaymentError("Gaming station missing or inactive", status_code=404)

        existing_active = PaymentGamingSession.query.filter_by(
            station_id=station.id, status="active", is_deleted=False
        ).first()
        if existing_active and existing_active.id != session_row.id:
            raise PaymentError(
                f"Gaming station '{station.code}' was occupied by another session while waiting for payment verification",
                status_code=409,
            )

        # Duplicate-safe guard for external side effects.
        if session_row.legacy_session_id is not None:
            session_row.status = "active"
            session_row.started_at = session_row.started_at or _utc_now_naive()
            return

        station_code = self._station_to_switch(station.code)
        request_id = str(uuid.uuid4())
        power_on_triggered = False
        try:
            self.tuya_service.station_power_on(station_code, request_id=request_id)
            power_on_triggered = True

            legacy_payment = self.legacy.Payment.query.filter_by(provider_ref=payment.reference).first()
            if not legacy_payment:
                legacy_payment = self.legacy.Payment(
                    user_id=legacy_user.id,
                    game_id=session_row.game_id,
                    branch=session_row.branch,
                    amount=payment.amount_kobo / 100,
                    status="successful",
                    provider_ref=payment.reference,
                )
                db.session.add(legacy_payment)
                db.session.flush()

            duration_seconds = int(session_row.duration_minutes) * 60
            legacy_session = self.legacy.GamingSession(
                user_id=legacy_user.id,
                game_id=session_row.game_id,
                branch=session_row.branch,
                plug_id=self._station_to_legacy_plug(station.code),
                duration_seconds=duration_seconds,
                remaining_seconds=duration_seconds,
                status="active",
                payment_id=legacy_payment.id,
                started_at=_utc_now_naive(),
            )
            db.session.add(legacy_session)
            db.session.flush()

            session_row.status = "active"
            session_row.started_at = _utc_now_naive()
            session_row.legacy_session_id = legacy_session.id

            self._log_payment(
                payment,
                "session_activated",
                "Gaming session activated after successful payment",
                payload={"legacy_session_id": legacy_session.id, "station": station.code},
            )

            channel = f"user:{legacy_user.id}"
            self.event_bus.publish(
                channel,
                {
                    "type": "payment_success",
                    "payload": {
                        "reference": payment.reference,
                        "legacy_session_id": legacy_session.id,
                        "station": station.code,
                        "status": "active",
                    },
                },
            )
        except Exception:
            if power_on_triggered:
                try:
                    self.tuya_service.station_power_off(station_code, request_id=str(uuid.uuid4()))
                except Exception as power_off_error:
                    current_app.logger.exception(
                        "Failed to roll back station power state after payment activation failure: %s",
                        power_off_error,
                    )
            current_app.logger.exception(
                "Failed to activate gaming session for payment reference=%s station=%s",
                payment.reference,
                station.code,
            )
            raise

    def get_payment_status(self, reference: str, *, refresh_from_gateway: bool = False) -> dict[str, Any]:
        payment = Payment.query.filter_by(reference=reference, is_deleted=False).first()
        if not payment:
            raise PaymentError("Transaction not found", status_code=404)

        if refresh_from_gateway and self._normalize_payment_status(payment.status) not in {"completed", "failed"}:
            payment = self.verify_transaction(reference, trigger="status_poll", allow_activation=False)

        session_row = PaymentGamingSession.query.filter_by(id=payment.payment_session_id, is_deleted=False).first()
        effective_status = self._effective_payment_status(payment)

        return {
            "reference": payment.reference,
            "status": effective_status,
            "status_label": self._payment_status_label(effective_status),
            "gateway_status": payment.gateway_status,
            "amount_kobo": payment.amount_kobo,
            "currency": payment.currency,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
            "verified_at": payment.verified_at.isoformat() if payment.verified_at else None,
            "session": {
                "id": session_row.id if session_row else None,
                "status": session_row.status if session_row else None,
                "legacy_session_id": session_row.legacy_session_id if session_row else None,
            },
        }

    def get_payment_history(self, payment_user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = (
            Payment.query.filter_by(user_id=payment_user_id, is_deleted=False)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "reference": row.reference,
                "status": self._effective_payment_status(row),
                "status_label": self._payment_status_label(self._effective_payment_status(row)),
                "amount_kobo": row.amount_kobo,
                "currency": row.currency,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    def get_invoice(self, reference: str) -> dict[str, Any]:
        payment = Payment.query.filter_by(reference=reference, is_deleted=False).first()
        if not payment:
            raise PaymentError("Transaction not found", status_code=404)

        session_row = PaymentGamingSession.query.filter_by(id=payment.payment_session_id, is_deleted=False).first()
        station = db.session.get(GamingStation, session_row.station_id) if session_row else None
        effective_status = self._effective_payment_status(payment)

        return {
            "reference": payment.reference,
            "status": effective_status,
            "status_label": self._payment_status_label(effective_status),
            "amount_naira": payment.amount_kobo / 100,
            "currency": payment.currency,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
            "station": station.name if station else None,
            "duration_minutes": session_row.duration_minutes if session_row else None,
        }
