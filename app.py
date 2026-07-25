import logging,os,json
from datetime import datetime



from dotenv import load_dotenv
from flask import Flask, redirect, url_for
from werkzeug.security import generate_password_hash

from auth_helpers import (
    current_user,
    get_redirect_for_role,
    login_required,
    role_required,
    user_can_manage_branch,
)
from config import Config
from database.connector import init_database
from extensions import db, migrate
from app.models import GamingStation, PaymentGamingSession, PaymentLog, PaymentUser
from app.payment import create_payment_blueprint
from models import (
    AuditLog,
    Game,
    GamingSession,
    LoginHistory,
    Notification,
    Payment,
    TuyaCommandHistory,
    TuyaDevice,
    TuyaDeviceStatus,
    TuyaEventLog,
    User,
)
from routes.admin_routes import create_admin_blueprints
from routes.user_routes import create_user_blueprints
from services import EventBus, TuyaPulsarConsumer, TuyaService

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

init_database(app)
migrate.init_app(app, db)

ALLOWED_BRANCHES = {"branch1", "branch2"}
ADMIN_ROLES = {"admin1", "admin2", "superadmin"}


event_bus = EventBus()
tuya_service = TuyaService(
    base_url=app.config.get("TUYA_BASE_URL", "https://openapi.tuya.com"),
    client_id=app.config.get("TUYA_CLIENT_ID", ""),
    client_secret=app.config.get("TUYA_CLIENT_SECRET", ""),
    device_id=app.config.get("TUYA_DEVICE_ID", ""),
    timeout_seconds=app.config.get("TUYA_TIMEOUT_SECONDS", 10),
    max_retries=app.config.get("TUYA_MAX_RETRIES", 3),
    redis_url=app.config.get("REDIS_URL", "") or None,
)


def handle_tuya_pulsar_event(payload: dict) -> None:
    event_type = str(payload.get("eventType") or payload.get("bizCode") or "unknown")
    device_id = str(payload.get("devId") or payload.get("deviceId") or tuya_service.device_id)
    event_id = str(payload.get("id") or payload.get("eventId") or "")

    with app.app_context():
        db.session.add(
            TuyaEventLog(
                device_id=device_id,
                event_type=event_type,
                event_id=event_id,
                payload_json=json.dumps(payload, ensure_ascii=True),
            )
        )
        device = TuyaDevice.query.filter_by(device_id=device_id).first()
        if not device:
            device = TuyaDevice(device_id=device_id)
            db.session.add(device)

        if event_type == "deviceOnline":
            device.is_online = True
        elif event_type == "deviceOffline":
            device.is_online = False
        device.last_seen_at = datetime.utcnow()
        db.session.commit()

        for active in GamingSession.query.filter_by(status="active").all():
            event_bus.publish(
                f"user:{active.user_id}",
                {
                    "type": "tuya_event",
                    "payload": {
                        "event_type": event_type,
                        "device_id": device_id,
                    },
                },
            )


pulsar_consumer = None
if app.config.get("TUYA_PULSAR_ENABLED") and app.config.get("TUYA_PULSAR_BROKER_URL") and app.config.get("TUYA_PULSAR_TOPIC"):
    pulsar_consumer = TuyaPulsarConsumer(
        broker_url=app.config.get("TUYA_PULSAR_BROKER_URL"),
        topic=app.config.get("TUYA_PULSAR_TOPIC"),
        subscription=app.config.get("TUYA_PULSAR_SUBSCRIPTION", "gameswitchos"),
        message_handler=handle_tuya_pulsar_event,
    )
    pulsar_consumer.start()


def seed_default_data() -> None:
    default_accounts = [
        {
            "full_name": "Branch One Admin",
            "email": "admin1@gameswitch.local",
            "phone": "08000000001",
            "role": "admin1",
            "branch": "branch1",
            "password": "Admin123!",
        },
        {
            "full_name": "Branch Two Admin",
            "email": "admin2@gameswitch.local",
            "phone": "08000000002",
            "role": "admin2",
            "branch": "branch2",
            "password": "Admin123!",
        },
        {
            "full_name": "System Superadmin",
            "email": "superadmin@gameswitch.local",
            "phone": "08000000003",
            "role": "superadmin",
            "branch": "branch1",
            "password": "Admin123!",
        },
    ]

    for account in default_accounts:
        exists = User.query.filter_by(email=account["email"]).first()
        if exists:
            continue
        db.session.add(
            User(
                full_name=account["full_name"],
                email=account["email"],
                phone=account["phone"],
                role=account["role"],
                branch=account["branch"],
                password_hash=generate_password_hash(account["password"]),
                is_active=True,
            )
        )

    db.session.commit()


def money(value) -> float:
    return float(value or 0)


@app.context_processor
def inject_auth_user():
    return {"auth_user": current_user()}


@app.route("/")
def root():
    return redirect(url_for("user.welcome"))


user_bp, user_api_bp = create_user_blueprints(
    db=db,
    User=User,
    Game=Game,
    Payment=Payment,
    GamingSession=GamingSession,
    LoginHistory=LoginHistory,
    Notification=Notification,
    ALLOWED_BRANCHES=ALLOWED_BRANCHES,
    ADMIN_ROLES=ADMIN_ROLES,
    current_user=current_user,
    login_required=login_required,
    user_can_manage_branch=user_can_manage_branch,
    get_redirect_for_role=get_redirect_for_role,
    money=money,
    tuya_service=tuya_service,
    event_bus=event_bus,
    TuyaDevice=TuyaDevice,
    TuyaDeviceStatus=TuyaDeviceStatus,
    TuyaCommandHistory=TuyaCommandHistory,
    TuyaEventLog=TuyaEventLog,
    AuditLog=AuditLog,
)

admin_bp, admin_api_bp = create_admin_blueprints(
    db=db,
    User=User,
    Game=Game,
    AuditLog=AuditLog,
    Payment=Payment,
    GamingSession=GamingSession,
    current_user=current_user,
    role_required=role_required,
    user_can_manage_branch=user_can_manage_branch,
    ALLOWED_BRANCHES=ALLOWED_BRANCHES,
    money=money,
)

app.register_blueprint(user_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_api_bp)
app.register_blueprint(admin_api_bp)

payments_bp = create_payment_blueprint(
    db=db,
    legacy_models=type(
        "LegacyModels",
        (),
        {
            "User": User,
            "Game": Game,
            "Payment": Payment,
            "GamingSession": GamingSession,
        },
    )(),
    current_user=current_user,
    login_required=login_required,
    tuya_service=tuya_service,
    event_bus=event_bus,
)
app.register_blueprint(payments_bp)




if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )