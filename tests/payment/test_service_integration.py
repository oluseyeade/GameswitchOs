import unittest
import os
from dataclasses import dataclass
from types import SimpleNamespace

from flask import Flask

from app.models.payment import Payment
from app.models.session import GamingStation, PaymentGamingSession, PaymentUser
from app.payment.services import PaymentError, PaymentService
from extensions import db


class LegacyUser(db.Model):
    __tablename__ = "legacy_users_test"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    phone = db.Column(db.String(40), nullable=True)
    branch = db.Column(db.String(30), nullable=False, default="branch1")
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class LegacyGame(db.Model):
    __tablename__ = "legacy_games_test"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    price_per_hour = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class LegacyPayment(db.Model):
    __tablename__ = "legacy_payments_test"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    game_id = db.Column(db.Integer, nullable=False)
    branch = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    provider_ref = db.Column(db.String(120), nullable=True)


class LegacyGamingSession(db.Model):
    __tablename__ = "legacy_sessions_test"

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


@dataclass
class LegacyModels:
    User: object
    Game: object
    Payment: object
    GamingSession: object


class FakeGateway:
    def initialize_transaction(self, **kwargs):
        return {
            "authorization_url": "https://paystack.local/checkout",
            "access_code": "ac_test",
        }

    def verify_transaction(self, reference):
        return {
            "id": 1001,
            "status": "success",
            "amount": 500000,
            "currency": "NGN",
        }


class FakeTuya:
    def station_power_on(self, station, request_id=None):
        return {"ok": True, "station": station, "request_id": request_id}


class FakeEventBus:
    def publish(self, channel, payload):
        return None


class PaymentServiceIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        test_database_uri = os.getenv("TEST_DATABASE_URI", "")
        if not test_database_uri.startswith("mysql+pymysql://"):
            self.skipTest("Set TEST_DATABASE_URI to a dedicated MySQL test database to run this integration test.")
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI=test_database_uri,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            PAYSTACK_SECRET_KEY="sk_test",
        )
        db.init_app(self.app)

        with self.app.app_context():
            db.create_all()
            user = LegacyUser(full_name="Tester", email="tester@example.com", branch="branch1")
            game = LegacyGame(title="FIFA", price_per_hour=5000, is_active=True)
            db.session.add(user)
            db.session.add(game)
            db.session.commit()

            self.user_id = user.id
            self.game_id = game.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_initialize_then_webhook_verify_activation(self):
        legacy = LegacyModels(
            User=LegacyUser,
            Game=LegacyGame,
            Payment=LegacyPayment,
            GamingSession=LegacyGamingSession,
        )

        with self.app.app_context():
            service = PaymentService(legacy_models=legacy, tuya_service=FakeTuya(), event_bus=FakeEventBus())
            service._gateway = lambda: FakeGateway()  # type: ignore[method-assign]
            service.ensure_default_stations()

            user = db.session.get(LegacyUser, self.user_id)
            init = service.initialize_transaction(
                legacy_user=user,
                game_id=self.game_id,
                duration_minutes=60,
                station_code="station1",
                callback_url="https://example.com/payments/callback",
                request_id="req-1",
                remote_ip="127.0.0.1",
                user_agent="pytest",
            )

            self.assertIn("reference", init)
            reference = init["reference"]

            payment = service.verify_transaction(reference, trigger="webhook", allow_activation=True)
            self.assertEqual(payment.status, "completed")

            session_row = PaymentGamingSession.query.filter_by(payment_reference=reference).first()
            self.assertIsNotNone(session_row)
            self.assertEqual(session_row.status, "active")

            duplicate = service.verify_transaction(reference, trigger="webhook", allow_activation=True)
            self.assertEqual(duplicate.status, "completed")
            self.assertEqual(PaymentGamingSession.query.filter_by(payment_reference=reference).count(), 1)

            legacy_session = db.session.get(LegacyGamingSession, session_row.legacy_session_id)
            self.assertIsNotNone(legacy_session)

            payment_user = PaymentUser.query.filter_by(legacy_user_id=self.user_id).first()
            self.assertIsNotNone(payment_user)

            payment_row = Payment.query.filter_by(reference=reference).first()
            self.assertIsNotNone(payment_row)

    def test_history_surfaces_completed_when_session_is_active(self):
        legacy = LegacyModels(
            User=LegacyUser,
            Game=LegacyGame,
            Payment=LegacyPayment,
            GamingSession=LegacyGamingSession,
        )

        with self.app.app_context():
            service = PaymentService(legacy_models=legacy, tuya_service=FakeTuya(), event_bus=FakeEventBus())
            service.ensure_default_stations()

            payment_user = PaymentUser(
                legacy_user_id=self.user_id,
                email="tester@example.com",
                full_name="Tester",
                is_active=True,
            )
            db.session.add(payment_user)
            db.session.flush()

            station = GamingStation.query.filter_by(code="station1").first()
            session_row = PaymentGamingSession(
                user_id=payment_user.id,
                station_id=station.id,
                game_id=self.game_id,
                branch="branch1",
                duration_minutes=60,
                amount_kobo=500000,
                currency="NGN",
                status="active",
                payment_reference="GSX-history-test",
                legacy_session_id=77,
                started_at=service._utc_now_naive() if hasattr(service, "_utc_now_naive") else None,
            )
            db.session.add(session_row)
            db.session.flush()

            payment = Payment(
                reference="GSX-history-test",
                provider="paystack",
                user_id=payment_user.id,
                payment_session_id=session_row.id,
                amount_kobo=500000,
                expected_amount_kobo=500000,
                currency="NGN",
                status="success_pending_webhook",
                gateway_status="success",
            )
            db.session.add(payment)
            db.session.commit()

            history = service.get_payment_history(payment_user.id, limit=10)
            self.assertEqual(history[0]["status"], "completed")
            self.assertEqual(history[0]["status_label"], "Completed")

    def test_initialize_rejects_station_from_another_branch(self):
        legacy = LegacyModels(
            User=LegacyUser,
            Game=LegacyGame,
            Payment=LegacyPayment,
            GamingSession=LegacyGamingSession,
        )

        with self.app.app_context():
            service = PaymentService(legacy_models=legacy, tuya_service=FakeTuya(), event_bus=FakeEventBus())
            service._gateway = lambda: FakeGateway()  # type: ignore[method-assign]
            service.ensure_default_stations()

            user = db.session.get(LegacyUser, self.user_id)
            with self.assertRaises(PaymentError) as exc_ctx:
                service.initialize_transaction(
                    legacy_user=user,
                    game_id=self.game_id,
                    duration_minutes=60,
                    station_code="station2",
                    callback_url="https://example.com/payments/callback",
                    request_id="req-branch-check",
                    remote_ip="127.0.0.1",
                    user_agent="pytest",
                )

            self.assertEqual(exc_ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
