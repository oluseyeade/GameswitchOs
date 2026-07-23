from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index

from extensions import db


def _utc_now_naive() -> datetime:
    # Store UTC timestamps as naive values for compatibility with existing schema.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Payment(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference = db.Column(db.String(64), nullable=False, unique=True, index=True)
    provider = db.Column(db.String(30), nullable=False, default="paystack")

    user_id = db.Column(db.String(36), db.ForeignKey("payment_users.id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_session_id = db.Column(
        db.String(36),
        db.ForeignKey("payment_gaming_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    amount_kobo = db.Column(db.Integer, nullable=False)
    expected_amount_kobo = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="NGN")

    status = db.Column(db.String(20), nullable=False, default="initialized", index=True)
    gateway_status = db.Column(db.String(40), nullable=True)

    access_code = db.Column(db.String(120), nullable=True)
    authorization_url = db.Column(db.String(255), nullable=True)
    provider_transaction_id = db.Column(db.String(80), nullable=True)

    paid_at = db.Column(db.DateTime, nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    verify_attempts = db.Column(db.Integer, nullable=False, default=0)

    callback_payload_json = db.Column(db.Text, nullable=True)
    webhook_payload_json = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)

    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utc_now_naive, onupdate=_utc_now_naive)

    logs = db.relationship("PaymentLog", back_populates="payment", lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("amount_kobo >= 100", name="ck_payment_amount_kobo"),
        CheckConstraint("expected_amount_kobo >= 100", name="ck_payment_expected_amount_kobo"),
        CheckConstraint(
            "status IN ('initialized','pending','success_pending_webhook','completed','success','failed','abandoned','refunded')",
            name="ck_payment_status",
        ),
        Index("ix_payment_user_status", "user_id", "status"),
        Index("ix_payment_created_at", "created_at"),
        Index("ix_payment_provider_status", "provider", "status"),
    )


class PaymentLog(db.Model):
    __tablename__ = "payment_logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_id = db.Column(db.String(36), db.ForeignKey("payment_transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    reference = db.Column(db.String(64), nullable=False, index=True)

    event_type = db.Column(db.String(60), nullable=False, index=True)
    source = db.Column(db.String(32), nullable=False, default="system", index=True)
    message = db.Column(db.String(255), nullable=False)
    severity = db.Column(db.String(16), nullable=False, default="info", index=True)

    request_id = db.Column(db.String(120), nullable=True, index=True)
    remote_ip = db.Column(db.String(80), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    payload_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now_naive)

    payment = db.relationship(Payment, back_populates="logs")

    __table_args__ = (
        Index("ix_payment_log_reference_created", "reference", "created_at"),
        Index("ix_payment_log_source_created", "source", "created_at"),
    )
