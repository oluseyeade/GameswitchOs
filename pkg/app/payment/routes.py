from __future__ import annotations

import ipaddress
import json
import os
import secrets
from functools import wraps
from typing import Any

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from pkg.app.models.payment import Payment
from pkg.app.models.session import PaymentUser
from pkg.app.payment.services import LegacyModels, PaymentError, PaymentService
from pkg.app.payment.utils import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    RedisReplayGuard,
    ReplayGuard,
    SupportsRateLimiter,
)
from pkg.app.payment.webhook import WebhookProcessor


def _extract_jwt_subject(
    token: str,
    secret: str,
    *,
    issuer: str | None,
    audience: str | None,
    require_exp: bool,
) -> int | None:
    try:
        jwt = __import__("jwt")

        options: dict[str, Any] = {
            "verify_aud": bool(audience),
            "verify_iss": bool(issuer),
            "require": ["sub", "exp"] if require_exp else ["sub"],
        }
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=audience,
            issuer=issuer,
            options=options,
        )
        subject = payload.get("sub")
        return int(subject) if subject is not None else None
    except Exception:
        return None


def create_payment_blueprint(
    *,
    db: Any,
    legacy_models: LegacyModels,
    current_user: Any,
    login_required: Any,
    tuya_service: Any,
    event_bus: Any,
) -> Blueprint:
    payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

    payment_service = PaymentService(legacy_models=legacy_models, tuya_service=tuya_service, event_bus=event_bus)
    redis_url = os.getenv("REDIS_URL", "")
    init_limit = int(os.getenv("PAYMENT_RATE_LIMIT_INITIALIZE_PER_MIN", "10"))
    status_limit = int(os.getenv("PAYMENT_RATE_LIMIT_STATUS_PER_MIN", "60"))
    replay_ttl = int(os.getenv("PAYMENT_WEBHOOK_REPLAY_TTL_SECONDS", "900"))
    trust_proxy = os.getenv("PAYMENT_TRUST_PROXY", "false").lower() == "true"
    trusted_proxy_ips = {
        value.strip()
        for value in os.getenv("PAYMENT_TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",")
        if value.strip()
    }
    jwt_issuer = os.getenv("JWT_ISSUER", "").strip() or None
    jwt_audience = os.getenv("JWT_AUDIENCE", "").strip() or None
    jwt_require_exp = os.getenv("PAYMENT_JWT_REQUIRE_EXP", "true").lower() == "true"

    limiter_initialize: SupportsRateLimiter
    limiter_status: SupportsRateLimiter
    fallback_initialize = InMemoryRateLimiter(limit=init_limit, window_seconds=60)
    fallback_status = InMemoryRateLimiter(limit=status_limit, window_seconds=60)
    fallback_replay = ReplayGuard(ttl_seconds=replay_ttl, max_items=20000)

    if redis_url:
        limiter_initialize = RedisRateLimiter(
            redis_url,
            limit=init_limit,
            window_seconds=60,
            prefix="pay:rl:init",
            fallback_limiter=fallback_initialize,
        )
        limiter_status = RedisRateLimiter(
            redis_url,
            limit=status_limit,
            window_seconds=60,
            prefix="pay:rl:status",
            fallback_limiter=fallback_status,
        )
        webhook_replay_guard = RedisReplayGuard(
            redis_url,
            ttl_seconds=replay_ttl,
            prefix="pay:webhook:replay",
            fallback_guard=fallback_replay,
            fail_closed=True,
        )
    else:
        limiter_initialize = fallback_initialize
        limiter_status = fallback_status
        webhook_replay_guard = fallback_replay

    def _valid_ip(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    def _client_ip() -> str:
        remote_addr = (request.remote_addr or "").strip()
        if not _valid_ip(remote_addr):
            remote_addr = "0.0.0.0"

        if not trust_proxy:
            return remote_addr

        if trusted_proxy_ips and remote_addr not in trusted_proxy_ips:
            return remote_addr

        forward = request.headers.get("X-Forwarded-For", "")
        if not forward:
            return remote_addr

        candidates = [item.strip() for item in forward.split(",") if item.strip()]
        for candidate in candidates:
            if _valid_ip(candidate):
                return candidate
        return remote_addr

    def _resolve_user() -> Any:
        user = current_user()
        if user:
            return user

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        secret = current_app.config.get("JWT_SECRET_KEY", "")
        if not secret:
            return None
        subject = _extract_jwt_subject(
            token,
            secret,
            issuer=jwt_issuer,
            audience=jwt_audience,
            require_exp=jwt_require_exp,
        )
        if not subject:
            return None
        return legacy_models.User.query.get(subject)

    def _requires_auth(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = _resolve_user()
            if not user:
                if request.accept_mimetypes.best == "application/json" or request.path.startswith("/payments/status"):
                    return jsonify({"ok": False, "message": "Unauthorized"}), 401
                return login_required(lambda: None)()
            return view(user, *args, **kwargs)

        return wrapped

    def _enforce_rate_limit(limiter: SupportsRateLimiter, bucket: str):
        key = f"{bucket}:{_client_ip()}"
        if limiter.allow(key):
            return None
        return jsonify({"ok": False, "message": "Too many requests. Please retry later."}), 429

    def _csrf_token() -> str:
        token = session.get("csrf_token")
        if token:
            return token
        token = secrets.token_urlsafe(24)
        session["csrf_token"] = token
        return token

    def _webhook_testing_warning() -> str | None:
        host = (request.host or "").split(":", 1)[0].strip("[]").lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            message = "Paystack webhooks require a publicly accessible HTTPS endpoint for full testing (use ngrok or Cloudflare Tunnel)."
            current_app.logger.warning(message)
            return message
        return None

    def _validate_csrf() -> bool:
        expected = session.get("csrf_token", "")
        provided = request.headers.get("X-CSRF-Token", "")
        return bool(expected and provided and secrets.compare_digest(expected, provided))

    def _ensure_owner(user: Any, reference: str) -> Payment | None:
        payment = Payment.query.filter_by(reference=reference, is_deleted=False).first()
        if not payment:
            return None
        payment_user = PaymentUser.query.filter_by(id=payment.user_id, is_deleted=False).first()
        if not payment_user:
            return None
        if payment_user.legacy_user_id != user.id and getattr(user, "role", "user") != "superadmin":
            return None
        return payment

    @payments_bp.before_app_request
    def _seed_default_stations_once() -> None:
        if not getattr(current_app, "_payment_stations_seeded", False):
            payment_service.ensure_default_stations()
            current_app._payment_stations_seeded = True

    @payments_bp.get("/checkout")
    @_requires_auth
    def checkout_page(user: Any):
        csrf_token = _csrf_token()
        games = legacy_models.Game.query.filter_by(is_active=True).all()
        return render_template(
            "payment/checkout.html",
            games=games,
            csrf_token=csrf_token,
            auth_user=user,
            webhook_warning=_webhook_testing_warning(),
        )

    @payments_bp.get("/dashboard")
    @_requires_auth
    def dashboard_page(user: Any):
        payment_user = payment_service.ensure_payment_user(user)
        history = payment_service.get_payment_history(payment_user.id, limit=50)
        return render_template("payment/dashboard.html", history=history, auth_user=user)

    @payments_bp.post("/initialize")
    @_requires_auth
    def initialize_payment(user: Any):
        blocked = _enforce_rate_limit(limiter_initialize, "initialize")
        if blocked:
            return blocked

        if not _validate_csrf():
            return jsonify({"ok": False, "message": "Invalid CSRF token"}), 403

        payload = request.get_json(silent=True) or {}
        try:
            callback_url = url_for("payments.payment_callback", _external=True)
            data = payment_service.initialize_transaction(
                legacy_user=user,
                game_id=int(payload.get("game_id") or 0),
                duration_minutes=int(payload.get("duration_minutes") or 0),
                station_code=str(payload.get("station_code") or ""),
                callback_url=callback_url,
                request_id=request.headers.get("Idempotency-Key") or secrets.token_hex(10),
                remote_ip=_client_ip(),
                user_agent=request.headers.get("User-Agent", ""),
            )
            return jsonify({"ok": True, "data": data})
        except PaymentError as exc:
            db.session.rollback()
            current_app.logger.warning("Payment initialization rejected: %s", exc)
            return jsonify({"ok": False, "message": str(exc)}), exc.status_code
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unhandled exception while initializing payment")
            return jsonify({"ok": False, "message": "Unable to initialize payment"}), 500

    @payments_bp.get("/callback")
    @_requires_auth
    def payment_callback(user: Any):
        reference = request.args.get("reference", "").strip()
        if not reference:
            return render_template("payment/failed.html", message="Missing payment reference", auth_user=user), 400

        if not _ensure_owner(user, reference):
            return render_template("payment/failed.html", message="Forbidden payment reference", auth_user=user), 403

        # Callback is not trusted as source of truth. We only verify and wait for webhook to activate session.
        try:
            payment = payment_service.verify_transaction(reference, trigger="callback", allow_activation=False)
        except PaymentError as exc:
            return render_template("payment/failed.html", message=str(exc), auth_user=user), exc.status_code

        if payment.status in {"success", "completed"}:
            return redirect(url_for("payments.payment_result", reference=reference))
        if payment.status in {"pending", "success_pending_webhook"}:
            return render_template("payment/pending.html", reference=reference, auth_user=user)
        if payment.status == "failed":
            return render_template("payment/failed.html", reference=reference, message="Payment failed", auth_user=user)
        return render_template("payment/pending.html", reference=reference, auth_user=user)

    @payments_bp.post("/webhook")
    def webhook_listener():
        raw_body = request.get_data(cache=True, as_text=False)
        payload = request.get_json(silent=True)
        if payload is None:
            try:
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                payload = {}
        signature = request.headers.get("X-Paystack-Signature", "")
        processor = WebhookProcessor(
            payment_service,
            current_app.config.get("PAYSTACK_SECRET_KEY", ""),
            replay_guard=webhook_replay_guard,
        )
        try:
            ok, message, status = processor.process(raw_body=raw_body, signature=signature, payload=payload)
            if not ok:
                current_app.logger.warning("Payment webhook rejected (%s): %s", status, message)
            return jsonify({"ok": ok, "message": message}), status
        except PaymentError as exc:
            db.session.rollback()
            current_app.logger.warning("Webhook payment error: %s", str(exc))
            return jsonify({"ok": False, "message": str(exc)}), exc.status_code
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unhandled exception while processing payment webhook")
            return jsonify({"ok": False, "message": "Webhook processing failed"}), 500

    @payments_bp.get("/history")
    @_requires_auth
    def payment_history(user: Any):
        payment_user = payment_service.ensure_payment_user(user)
        limit = min(int(request.args.get("limit", 30)), 100)
        history = payment_service.get_payment_history(payment_user.id, limit=limit)
        if request.accept_mimetypes.best == "application/json" or request.args.get("format") == "json":
            return jsonify({"ok": True, "history": history})
        return render_template("payment/history.html", history=history, auth_user=user)

    @payments_bp.get("/status/<reference>")
    @_requires_auth
    def payment_status(user: Any, reference: str):
        blocked = _enforce_rate_limit(limiter_status, "status")
        if blocked:
            return blocked

        if not _ensure_owner(user, reference):
            return jsonify({"ok": False, "message": "Forbidden"}), 403

        refresh = request.args.get("refresh", "false").lower() == "true"
        try:
            payload = payment_service.get_payment_status(reference, refresh_from_gateway=refresh)
            return jsonify({"ok": True, "data": payload})
        except PaymentError as exc:
            return jsonify({"ok": False, "message": str(exc)}), exc.status_code

    @payments_bp.get("/result/<reference>")
    @_requires_auth
    def payment_result(user: Any, reference: str):
        if not _ensure_owner(user, reference):
            return jsonify({"ok": False, "message": "Forbidden"}), 403

        try:
            payload = payment_service.get_payment_status(reference, refresh_from_gateway=False)
        except PaymentError as exc:
            return jsonify({"ok": False, "message": str(exc)}), exc.status_code

        status = payload.get("status")
        if status in {"success", "completed"}:
            return render_template("payment/success.html", reference=reference, payload=payload, auth_user=user)
        if status == "failed":
            return render_template("payment/failed.html", reference=reference, message="Payment failed", auth_user=user)
        return render_template("payment/pending.html", reference=reference, payload=payload, auth_user=user)

    @payments_bp.get("/invoice/<reference>")
    @_requires_auth
    def payment_invoice(user: Any, reference: str):
        if not _ensure_owner(user, reference):
            return jsonify({"ok": False, "message": "Forbidden"}), 403

        try:
            invoice = payment_service.get_invoice(reference)
            return render_template("payment/invoice.html", invoice=invoice, auth_user=user)
        except PaymentError as exc:
            return jsonify({"ok": False, "message": str(exc)}), exc.status_code

    @payments_bp.post("/retry/<reference>")
    @_requires_auth
    def retry_payment(user: Any, reference: str):
        payment = _ensure_owner(user, reference)
        if not payment:
            return jsonify({"ok": False, "message": "Forbidden"}), 403

        if payment.status not in {"failed", "abandoned"}:
            return jsonify({"ok": False, "message": "Only failed payments can be retried"}), 409

        return redirect(url_for("payments.checkout_page"))

    return payments_bp
