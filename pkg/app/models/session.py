from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index

from pkg.extensions import db


def _utc_now_naive() -> datetime:
    # Store UTC timestamps as naive values for compatibility with existing schema.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampSoftDeleteMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utc_now_naive, onupdate=_utc_now_naive)
    deleted_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)

    def soft_delete(self) -> None:
        self.deleted_at = _utc_now_naive()
        self.is_deleted = True


class PaymentUser(TimestampSoftDeleteMixin, db.Model):
    __tablename__ = "payment_users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    legacy_user_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    email = db.Column(db.String(180), nullable=False, unique=True)
    full_name = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    sessions = db.relationship("PaymentGamingSession", back_populates="user", lazy="dynamic")


class GamingStation(TimestampSoftDeleteMixin, db.Model):
    __tablename__ = "gaming_stations"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = db.Column(db.String(40), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    branch = db.Column(db.String(40), nullable=False, index=True)
    tuya_switch_code = db.Column(db.String(40), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    sessions = db.relationship("PaymentGamingSession", back_populates="station", lazy="dynamic")


class PaymentGamingSession(TimestampSoftDeleteMixin, db.Model):
    __tablename__ = "payment_gaming_sessions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("payment_users.id", ondelete="RESTRICT"), nullable=False, index=True)
    station_id = db.Column(db.String(36), db.ForeignKey("gaming_stations.id", ondelete="RESTRICT"), nullable=False, index=True)

    game_id = db.Column(db.Integer, nullable=False, index=True)
    branch = db.Column(db.String(40), nullable=False, index=True)
    duration_minutes = db.Column(db.Integer, nullable=False)
    amount_kobo = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="NGN")

    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    payment_reference = db.Column(db.String(64), nullable=True, unique=True)
    legacy_session_id = db.Column(db.Integer, nullable=True, unique=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("PaymentUser", back_populates="sessions")
    station = db.relationship("GamingStation", back_populates="sessions")

    __table_args__ = (
        CheckConstraint("duration_minutes >= 10", name="ck_payment_session_duration_min"),
        CheckConstraint("amount_kobo >= 100", name="ck_payment_session_amount_kobo"),
        CheckConstraint(
            "status IN ('pending','active','ended','cancelled','failed')",
            name="ck_payment_session_status",
        ),
        Index("ix_payment_session_branch_status", "branch", "status"),
    )
