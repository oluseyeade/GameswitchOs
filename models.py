from datetime import datetime

from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="user")
    branch = db.Column(db.String(30), nullable=False, default="branch1")
    avatar_url = db.Column(db.String(255), nullable=True)
    total_spent = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    price_per_hour = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(80), nullable=False, default="action")
    console_type = db.Column(db.String(80), nullable=False, default="console")
    status = db.Column(db.String(20), nullable=False, default="active")
    display_order = db.Column(db.Integer, nullable=False, default=0)
    cover_image_path = db.Column(db.String(255), nullable=True)
    banner_image_path = db.Column(db.String(255), nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    @property
    def game_name(self) -> str:
        return self.title

    @property
    def hourly_price(self):
        return self.price_per_hour

    @hourly_price.setter
    def hourly_price(self, value):
        self.price_per_hour = value

    @property
    def cover_image(self) -> str | None:
        path = self.cover_image_path or self.image_path
        if path and path.startswith("static/"):
            return path[len("static/"):]
        return path

    @property
    def is_available(self) -> bool:
        return self.is_active and self.status == "active"


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    branch = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    provider_ref = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class GamingSession(db.Model):
    __tablename__ = "gaming_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    branch = db.Column(db.String(30), nullable=False)
    plug_id = db.Column(db.String(100), nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False)
    remaining_seconds = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class LoginHistory(db.Model):
    __tablename__ = "login_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    login_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(60), nullable=True)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    branch = db.Column(db.String(30), nullable=True)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class TuyaDevice(db.Model):
    __tablename__ = "tuya_devices"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=True)
    product_id = db.Column(db.String(120), nullable=True)
    category = db.Column(db.String(80), nullable=True)
    is_online = db.Column(db.Boolean, nullable=False, default=False)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TuyaDeviceStatus(db.Model):
    __tablename__ = "tuya_device_status"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(120), db.ForeignKey("tuya_devices.device_id"), nullable=False)
    code = db.Column(db.String(120), nullable=False)
    value_text = db.Column(db.String(255), nullable=True)
    value_bool = db.Column(db.Boolean, nullable=True)
    value_number = db.Column(db.Float, nullable=True)
    last_updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("device_id", "code", name="uq_tuya_status_device_code"),)


class TuyaCommandHistory(db.Model):
    __tablename__ = "tuya_command_history"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(120), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("gaming_sessions.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    request_id = db.Column(db.String(120), unique=True, nullable=False)
    station = db.Column(db.String(30), nullable=True)
    command_json = db.Column(db.Text, nullable=False)
    success = db.Column(db.Boolean, nullable=False, default=False)
    response_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class TuyaEventLog(db.Model):
    __tablename__ = "tuya_event_logs"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(120), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    event_id = db.Column(db.String(120), nullable=True)
    payload_json = db.Column(db.Text, nullable=False)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(120), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
