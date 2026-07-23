import unittest
from unittest.mock import Mock, patch

from flask import Flask

from app.payment.services import PaystackGateway


class PaystackGatewayMockTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["PAYSTACK_TIMEOUT_SECONDS"] = 3

    @patch("app.payment.services.requests.request")
    def test_initialize_transaction_success(self, request_mock):
        fake_response = Mock()
        fake_response.status_code = 200
        fake_response.content = b"x"
        fake_response.json.return_value = {
            "status": True,
            "data": {"authorization_url": "https://paystack.test", "access_code": "abc"},
        }
        request_mock.return_value = fake_response

        with self.app.app_context():
            gateway = PaystackGateway(secret_key="sk_test")
            result = gateway.initialize_transaction(
                email="player@example.com",
                amount_kobo=10000,
                reference="GSX-ref-1",
                callback_url="https://example.com/payments/callback",
                metadata={"a": 1},
            )

        self.assertIn("authorization_url", result)

    @patch("app.payment.services.requests.request")
    def test_verify_transaction_success(self, request_mock):
        fake_response = Mock()
        fake_response.status_code = 200
        fake_response.content = b"x"
        fake_response.json.return_value = {"status": True, "data": {"status": "success", "amount": 10000}}
        request_mock.return_value = fake_response

        with self.app.app_context():
            gateway = PaystackGateway(secret_key="sk_test")
            result = gateway.verify_transaction("GSX-ref-2")

        self.assertEqual(result["status"], "success")

    @patch("app.payment.services.requests.request")
    def test_initialize_transaction_reports_malformed_gateway_response(self, request_mock):
        fake_response = Mock()
        fake_response.status_code = 502
        fake_response.content = b"<html>Bad gateway</html>"
        fake_response.text = "<html>Bad gateway</html>"
        fake_response.json.side_effect = ValueError("No JSON object could be decoded")
        request_mock.return_value = fake_response

        with self.app.app_context():
            gateway = PaystackGateway(secret_key="sk_test")
            with self.assertRaises(Exception) as exc_ctx:
                gateway.initialize_transaction(
                    email="player@example.com",
                    amount_kobo=10000,
                    reference="GSX-ref-3",
                    callback_url="https://example.com/payments/callback",
                    metadata={"a": 1},
                )

        self.assertIn("Paystack response", str(exc_ctx.exception))


if __name__ == "__main__":
    unittest.main()
