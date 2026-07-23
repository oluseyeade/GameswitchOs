"""add paystack payment module tables

Revision ID: 525accd07150
Revises: 
Create Date: 2026-07-19 16:34:42.416283

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '525accd07150'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("legacy_user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("full_name", sa.String(length=180), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("legacy_user_id"),
    )
    op.create_index("ix_payment_users_legacy_user_id", "payment_users", ["legacy_user_id"], unique=False)
    op.create_index("ix_payment_users_is_active", "payment_users", ["is_active"], unique=False)
    op.create_index("ix_payment_users_is_deleted", "payment_users", ["is_deleted"], unique=False)

    op.create_table(
        "gaming_stations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("branch", sa.String(length=40), nullable=False),
        sa.Column("tuya_switch_code", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_gaming_stations_branch", "gaming_stations", ["branch"], unique=False)
    op.create_index("ix_gaming_stations_is_active", "gaming_stations", ["is_active"], unique=False)
    op.create_index("ix_gaming_stations_is_deleted", "gaming_stations", ["is_deleted"], unique=False)

    op.create_table(
        "payment_gaming_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("station_id", sa.String(length=36), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("branch", sa.String(length=40), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("amount_kobo", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="NGN"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("payment_reference", sa.String(length=64), nullable=True),
        sa.Column("legacy_session_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("amount_kobo >= 100", name="ck_payment_session_amount_kobo"),
        sa.CheckConstraint("duration_minutes >= 10", name="ck_payment_session_duration_min"),
        sa.CheckConstraint("status IN ('pending','active','ended','cancelled','failed')", name="ck_payment_session_status"),
        sa.ForeignKeyConstraint(["station_id"], ["gaming_stations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["payment_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_session_id"),
        sa.UniqueConstraint("payment_reference"),
    )
    op.create_index("ix_payment_gaming_sessions_user_id", "payment_gaming_sessions", ["user_id"], unique=False)
    op.create_index("ix_payment_gaming_sessions_station_id", "payment_gaming_sessions", ["station_id"], unique=False)
    op.create_index("ix_payment_gaming_sessions_game_id", "payment_gaming_sessions", ["game_id"], unique=False)
    op.create_index("ix_payment_gaming_sessions_branch", "payment_gaming_sessions", ["branch"], unique=False)
    op.create_index("ix_payment_gaming_sessions_status", "payment_gaming_sessions", ["status"], unique=False)
    op.create_index("ix_payment_gaming_sessions_is_deleted", "payment_gaming_sessions", ["is_deleted"], unique=False)
    op.create_index("ix_payment_session_branch_status", "payment_gaming_sessions", ["branch", "status"], unique=False)

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False, server_default="paystack"),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("payment_session_id", sa.String(length=36), nullable=True),
        sa.Column("amount_kobo", sa.Integer(), nullable=False),
        sa.Column("expected_amount_kobo", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="NGN"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="initialized"),
        sa.Column("gateway_status", sa.String(length=40), nullable=True),
        sa.Column("access_code", sa.String(length=120), nullable=True),
        sa.Column("authorization_url", sa.String(length=255), nullable=True),
        sa.Column("provider_transaction_id", sa.String(length=80), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verify_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("callback_payload_json", sa.Text(), nullable=True),
        sa.Column("webhook_payload_json", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount_kobo >= 100", name="ck_payment_amount_kobo"),
        sa.CheckConstraint("expected_amount_kobo >= 100", name="ck_payment_expected_amount_kobo"),
        sa.CheckConstraint(
            "status IN ('initialized','pending','success_pending_webhook','completed','success','failed','abandoned','refunded')",
            name="ck_payment_status",
        ),
        sa.ForeignKeyConstraint(["payment_session_id"], ["payment_gaming_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["payment_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_payment_transactions_reference", "payment_transactions", ["reference"], unique=True)
    op.create_index("ix_payment_transactions_user_id", "payment_transactions", ["user_id"], unique=False)
    op.create_index("ix_payment_transactions_payment_session_id", "payment_transactions", ["payment_session_id"], unique=False)
    op.create_index("ix_payment_transactions_status", "payment_transactions", ["status"], unique=False)
    op.create_index("ix_payment_transactions_is_deleted", "payment_transactions", ["is_deleted"], unique=False)
    op.create_index("ix_payment_user_status", "payment_transactions", ["user_id", "status"], unique=False)
    op.create_index("ix_payment_created_at", "payment_transactions", ["created_at"], unique=False)
    op.create_index("ix_payment_provider_status", "payment_transactions", ["provider", "status"], unique=False)

    op.create_table(
        "payment_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("remote_ip", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payment_transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_logs_payment_id", "payment_logs", ["payment_id"], unique=False)
    op.create_index("ix_payment_logs_reference", "payment_logs", ["reference"], unique=False)
    op.create_index("ix_payment_logs_event_type", "payment_logs", ["event_type"], unique=False)
    op.create_index("ix_payment_logs_severity", "payment_logs", ["severity"], unique=False)
    op.create_index("ix_payment_logs_request_id", "payment_logs", ["request_id"], unique=False)
    op.create_index("ix_payment_log_reference_created", "payment_logs", ["reference", "created_at"], unique=False)


def downgrade():
    op.drop_index("ix_payment_log_reference_created", table_name="payment_logs")
    op.drop_index("ix_payment_logs_request_id", table_name="payment_logs")
    op.drop_index("ix_payment_logs_severity", table_name="payment_logs")
    op.drop_index("ix_payment_logs_event_type", table_name="payment_logs")
    op.drop_index("ix_payment_logs_reference", table_name="payment_logs")
    op.drop_index("ix_payment_logs_payment_id", table_name="payment_logs")
    op.drop_table("payment_logs")

    op.drop_index("ix_payment_provider_status", table_name="payment_transactions")
    op.drop_index("ix_payment_created_at", table_name="payment_transactions")
    op.drop_index("ix_payment_user_status", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_is_deleted", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_status", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_payment_session_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_user_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_reference", table_name="payment_transactions")
    op.drop_table("payment_transactions")

    op.drop_index("ix_payment_session_branch_status", table_name="payment_gaming_sessions")
    op.drop_index("ix_payment_gaming_sessions_is_deleted", table_name="payment_gaming_sessions")
    op.drop_index("ix_payment_gaming_sessions_status", table_name="payment_gaming_sessions")
    op.drop_index("ix_payment_gaming_sessions_branch", table_name="payment_gaming_sessions")
    op.drop_index("ix_payment_gaming_sessions_game_id", table_name="payment_gaming_sessions")
    op.drop_index("ix_payment_gaming_sessions_station_id", table_name="payment_gaming_sessions")
    op.drop_index("ix_payment_gaming_sessions_user_id", table_name="payment_gaming_sessions")
    op.drop_table("payment_gaming_sessions")

    op.drop_index("ix_gaming_stations_is_deleted", table_name="gaming_stations")
    op.drop_index("ix_gaming_stations_is_active", table_name="gaming_stations")
    op.drop_index("ix_gaming_stations_branch", table_name="gaming_stations")
    op.drop_table("gaming_stations")

    op.drop_index("ix_payment_users_is_deleted", table_name="payment_users")
    op.drop_index("ix_payment_users_is_active", table_name="payment_users")
    op.drop_index("ix_payment_users_legacy_user_id", table_name="payment_users")
    op.drop_table("payment_users")
