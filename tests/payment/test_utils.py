import hmac
import hashlib
import unittest
from unittest.mock import Mock, patch

from app.payment.utils import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    RedisReplayGuard,
    ReplayGuard,
    verify_paystack_signature,
)


class PaymentUtilsTestCase(unittest.TestCase):
    def test_verify_paystack_signature(self):
        secret = "secret123"
        raw = b'{"event":"charge.success"}'
        signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha512).hexdigest()
        self.assertTrue(verify_paystack_signature(raw, secret, signature))
        self.assertFalse(verify_paystack_signature(raw, secret, "bad-signature"))

    def test_replay_guard(self):
        guard = ReplayGuard(ttl_seconds=60)
        self.assertFalse(guard.seen("event-a"))
        self.assertTrue(guard.seen("event-a"))

    def test_in_memory_rate_limiter(self):
        limiter = InMemoryRateLimiter(limit=2, window_seconds=60)
        key = "127.0.0.1"
        self.assertTrue(limiter.allow(key))
        self.assertTrue(limiter.allow(key))
        self.assertFalse(limiter.allow(key))

    @patch("redis.Redis.from_url")
    def test_redis_replay_guard_uses_fallback_on_error(self, redis_from_url):
        redis_client = Mock()
        redis_client.set.side_effect = RuntimeError("redis unavailable")
        redis_from_url.return_value = redis_client

        fallback = ReplayGuard(ttl_seconds=60)
        guard = RedisReplayGuard("redis://localhost:6379/0", fallback_guard=fallback, fail_closed=True)

        self.assertFalse(guard.seen("evt-1"))
        self.assertTrue(guard.seen("evt-1"))

    @patch("redis.Redis.from_url")
    def test_redis_replay_guard_fail_closed_without_fallback(self, redis_from_url):
        redis_client = Mock()
        redis_client.set.side_effect = RuntimeError("redis unavailable")
        redis_from_url.return_value = redis_client

        guard = RedisReplayGuard("redis://localhost:6379/0", fallback_guard=None, fail_closed=True)
        self.assertTrue(guard.seen("evt-2"))

    @patch("redis.Redis.from_url")
    def test_redis_rate_limiter_uses_fallback_on_error(self, redis_from_url):
        redis_client = Mock()
        redis_client.incr.side_effect = RuntimeError("redis unavailable")
        redis_from_url.return_value = redis_client

        fallback = InMemoryRateLimiter(limit=1, window_seconds=60)
        limiter = RedisRateLimiter("redis://localhost:6379/0", limit=1, window_seconds=60, fallback_limiter=fallback)

        self.assertTrue(limiter.allow("key-a"))
        self.assertFalse(limiter.allow("key-a"))


if __name__ == "__main__":
    unittest.main()
