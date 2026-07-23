import hashlib
import hmac
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Blueprint, Flask, session

from app.payment.routes import create_payment_blueprint
from extensions import db


class LegacyUser(db.Model):
    __tablename__ = "legacy_users_e2e"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    phone = db.Column(db.String(40), nullable=True)
    branch = db.Column(db.String(30), nullable=False, default="branch1")
    role = db.Column(db.String(30), nullable=False, default="user")
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class LegacyGame(db.Model):
    __tablename__ = "legacy_games_e2e"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    price_per_hour = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class LegacyPayment(db.Model):
    __tablename__ = "legacy_payments_e2e"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    game_id = db.Column(db.Integer, nullable=False)
    branch = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    provider_ref = db.Column(db.String(120), nullable=True)


class LegacyGamingSession(db.Model):
    __tablename__ = "legacy_sessions_e2e"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    game_id = db.Column(db.Integer, nullable=False)
    branch = db.Column(db.String(30), nullable=False)
    plug_id = db.Column(db.String(100), nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False)
    remaining_seconds = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    payment_id = db.Column(db.Integer, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)


class FakeTuya:
    def station_power_on(self, station, request_id=None):
        return {"ok": True, "station": station, "request_id": request_id}


class FakeEventBus:
    def publish(self, channel, payload):
        return None


class PaymentE2EFlowTestCase(unittest.TestCase):
    def setUp(self):
        test_database_uri = os.getenv("TEST_DATABASE_URI", "")
        if not test_database_uri.startswith("mysql+pymysql://"):
            self.skipTest("Set TEST_DATABASE_URI to a dedicated MySQL test database to run this integration test.")
        project_root = Path(__file__).resolve().parents[2]
        self.app = Flask(
            __name__,
            template_folder=str(project_root / "templates"),
            static_folder=str(project_root / "static"),
        )
        self.app.config.update(
            SECRET_KEY="e2e-secret",
            SQLALCHEMY_DATABASE_URI=test_database_uri,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            PAYSTACK_SECRET_KEY="sk_test_e2e",
            REDIS_URL="",
        )

        db.init_app(self.app)

        with self.app.app_context():
            # Import payment models so SQLAlchemy registers all mapped tables.
            import app.models  # noqa: F401

            db.create_all()

            user = LegacyUser(
                full_name="E2E Tester",
                email="e2e@example.com",
                branch="branch1",
                role="user",
                is_active=True,
            )
            game = LegacyGame(title="FIFA", price_per_hour=5000, is_active=True)
            db.session.add_all([user, game])
            db.session.commit()
            self.user_id = user.id
            self.game_id = game.id

            def current_user():
                uid = session.get("user_id")
                if not uid:
                    return None
                return db.session.get(LegacyUser, uid)

            def login_required(view_func):
                def wrapped(*args, **kwargs):
                    user_row = current_user()
                    if not user_row:
                        from flask import jsonify

                        return jsonify({"ok": False, "message": "Unauthorized"}), 401
                    return view_func(*args, **kwargs)

                return wrapped

            legacy_models = type(
                "LegacyModels",
                (),
                {
                    "User": LegacyUser,
                    "Game": LegacyGame,
                    "Payment": LegacyPayment,
                    "GamingSession": LegacyGamingSession,
                },
            )()

            user_bp = Blueprint("user", __name__, url_prefix="/user")

            @user_bp.route("/welcome")
            def welcome():
                return "ok"

            @user_bp.route("/available-games")
            def available_games():
                return "ok"

            @user_bp.route("/session")
            def session_page():
                return "ok"

            @user_bp.route("/login")
            def login():
                return "ok"

            @user_bp.route("/register")
            def register():
                return "ok"

            @user_bp.route("/logout")
            def logout():
                return "ok"

            self.app.register_blueprint(user_bp)

            bp = create_payment_blueprint(
                db=db,
                legacy_models=legacy_models,
                current_user=current_user,
                login_required=login_required,
                tuya_service=FakeTuya(),
                event_bus=FakeEventBus(),
            )
            self.app.register_blueprint(bp)

        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    @patch("app.payment.services.PaystackGateway.verify_transaction")
    @patch("app.payment.services.PaystackGateway.initialize_transaction")
    def test_full_payment_flow(self, init_mock, verify_mock):
        init_mock.return_value = {
            "authorization_url": "https://paystack.local/checkout",
            "access_code": "ac_e2e",
        }
        verify_mock.return_value = {
            "id": 12345,
            "status": "success",
            "amount": 500000,
            "currency": "NGN",
            "paid_at": "2026-07-19T12:30:00Z",
        }

        with self.client as client:
            with client.session_transaction() as sess:
                sess["user_id"] = self.user_id
                sess["user_role"] = "user"
                sess["user_branch"] = "branch1"

            checkout = client.get("/payments/checkout")
            self.assertEqual(checkout.status_code, 200)

            with client.session_transaction() as sess:
                csrf = sess.get("csrf_token")
            self.assertTrue(csrf)

            init_resp = client.post(
                "/payments/initialize",
                json={
                    "game_id": self.game_id,
                    "duration_minutes": 60,
                    "station_code": "station1",
                },
                headers={
                    "X-CSRF-Token": csrf,
                    "Idempotency-Key": "e2e-flow-key",
                },
            )
            self.assertEqual(init_resp.status_code, 200)
            init_payload = init_resp.get_json()
            self.assertTrue(init_payload["ok"])
            reference = init_payload["data"]["reference"]

            callback = client.get(f"/payments/callback?reference={reference}")
            self.assertEqual(callback.status_code, 200)

            webhook_payload = {
                "event": "charge.success",
                "data": {
                    "id": 12345,
                    "reference": reference,
                },
            }
            raw = json.dumps(webhook_payload, separators=(",", ":")).encode("utf-8")
            signature = hmac.new(
                self.app.config["PAYSTACK_SECRET_KEY"].encode("utf-8"),
                raw,
                hashlib.sha512,
            ).hexdigest()

            webhook = client.post(
                "/payments/webhook",
                data=raw,
                content_type="application/json",
                headers={"X-Paystack-Signature": signature},
            )
            self.assertEqual(webhook.status_code, 200, webhook.get_data(as_text=True))
            self.assertTrue(webhook.get_json()["ok"])

            status = client.get(f"/payments/status/{reference}")
            self.assertEqual(status.status_code, 200)
            status_payload = status.get_json()["data"]
            self.assertEqual(status_payload["status"], "completed")
            self.assertEqual(status_payload["session"]["status"], "active")
            self.assertIsNotNone(status_payload["session"]["legacy_session_id"])


if __name__ == "__main__":
    unittest.main()
