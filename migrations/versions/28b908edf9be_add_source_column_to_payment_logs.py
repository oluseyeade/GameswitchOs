"""add source column to payment logs

Revision ID: 28b908edf9be
Revises: 525accd07150
Create Date: 2026-07-19 16:43:04.702206

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '28b908edf9be'
down_revision = '525accd07150'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "payment_logs",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="system"),
    )
    op.create_index("ix_payment_logs_source", "payment_logs", ["source"], unique=False)


def downgrade():
    op.drop_index("ix_payment_logs_source", table_name="payment_logs")
    op.drop_column("payment_logs", "source")
