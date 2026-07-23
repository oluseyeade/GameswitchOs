import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock

from flask import Flask

from app.payment.webhook import WebhookProcessor


class WebhookProcessorTestCase(unittest.TestCase):
    def setUp(self):
        self.secret = "whsec_test"
        self.service = Mock()
        self.processor = WebhookProcessor(self.service, self.secret)
        self.app = Flask(__name__)

    def _sign(self, body: bytes) -> str:
        return hmac.new(self.secret.encode("utf-8"), body, hashlib.sha512).hexdigest()

    def test_invalid_signature(self):
        body = json.dumps({"event": "charge.success", "data": {"reference": "abc"}}).encode("utf-8")
        ok, message, status = self.processor.process(raw_body=body, signature="bad", payload=json.loads(body.decode("utf-8")))
        self.assertFalse(ok)
        self.assertEqual(status, 401)

    def test_duplicate_event(self):
        payload = {"event": "charge.success", "data": {"reference": "abc", "id": 1}}
        body = json.dumps(payload).encode("utf-8")
        signature = self._sign(body)

        with self.app.app_context():
            from app.models.payment import Payment

            original_query = Payment.query
            try:
                Payment.query = Mock()  # type: ignore[assignment]
                Payment.query.filter_by.return_value.first.return_value = Mock(reference="abc", is_deleted=False)

                first = self.processor.process(raw_body=body, signature=signature, payload=payload)
                second = self.processor.process(raw_body=body, signature=signature, payload=payload)
            finally:
                Payment.query = original_query  # type: ignore[assignment]

        self.assertEqual(first[2], 200)
        self.assertEqual(second[1], "Duplicate webhook ignored")


if __name__ == "__main__":
    unittest.main()
