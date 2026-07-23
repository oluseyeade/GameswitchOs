import os

from dotenv import load_dotenv

from database.connector import build_database_uri


load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("MYSQL_POOL_RECYCLE", "280")),
    }
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_SIZE_MB", "8")) * 1024 * 1024
    GAME_UPLOAD_FOLDER = os.getenv("GAME_UPLOAD_FOLDER", "static/uploads/games")
    GAME_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

    # Tuya cloud settings (backend only; never expose in templates/frontend).
    TUYA_BASE_URL = os.getenv("TUYA_BASE_URL", "https://openapi.tuya.com")
    TUYA_CLIENT_ID = os.getenv("TUYA_CLIENT_ID", "")
    TUYA_CLIENT_SECRET = os.getenv("TUYA_CLIENT_SECRET", "")
    TUYA_DEVICE_ID = os.getenv("TUYA_DEVICE_ID", "")
    TUYA_TIMEOUT_SECONDS = int(os.getenv("TUYA_TIMEOUT_SECONDS", "10"))
    TUYA_MAX_RETRIES = int(os.getenv("TUYA_MAX_RETRIES", "3"))
    TUYA_EVENT_SECRET = os.getenv("TUYA_EVENT_SECRET", "")
    TUYA_PULSAR_ENABLED = os.getenv("TUYA_PULSAR_ENABLED", "false").lower() == "true"
    TUYA_PULSAR_BROKER_URL = os.getenv("TUYA_PULSAR_BROKER_URL", "")
    TUYA_PULSAR_TOPIC = os.getenv("TUYA_PULSAR_TOPIC", "")
    TUYA_PULSAR_SUBSCRIPTION = os.getenv("TUYA_PULSAR_SUBSCRIPTION", "gameswitchos")
    REDIS_URL = os.getenv("REDIS_URL", "")

    # Paystack payment configuration
    PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")
    PAYSTACK_TIMEOUT_SECONDS = int(os.getenv("PAYSTACK_TIMEOUT_SECONDS", "15"))
    PAYSTACK_MAX_RETRIES = int(os.getenv("PAYSTACK_MAX_RETRIES", "3"))
    PAYMENT_RATE_LIMIT_INITIALIZE_PER_MIN = int(os.getenv("PAYMENT_RATE_LIMIT_INITIALIZE_PER_MIN", "10"))
    PAYMENT_RATE_LIMIT_STATUS_PER_MIN = int(os.getenv("PAYMENT_RATE_LIMIT_STATUS_PER_MIN", "60"))
    PAYMENT_WEBHOOK_REPLAY_TTL_SECONDS = int(os.getenv("PAYMENT_WEBHOOK_REPLAY_TTL_SECONDS", "900"))
    PAYMENT_TRUST_PROXY = os.getenv("PAYMENT_TRUST_PROXY", "false").lower() == "true"
    PAYMENT_TRUSTED_PROXY_IPS = os.getenv("PAYMENT_TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    PAYMENT_JWT_REQUIRE_EXP = os.getenv("PAYMENT_JWT_REQUIRE_EXP", "true").lower() == "true"

    # Optional JWT validation for API clients.
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
    JWT_ISSUER = os.getenv("JWT_ISSUER", "")
    JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "")

    # Session/cookie security defaults (set SECURE=true in production HTTPS).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PREFERRED_URL_SCHEME = "https" if SESSION_COOKIE_SECURE else "http"
