"""add composite index for payment log source and created

Revision ID: f70bc3e88dd1
Revises: 28b908edf9be
Create Date: 2026-07-19 16:44:51.358952

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f70bc3e88dd1'
down_revision = '28b908edf9be'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_payment_log_source_created", "payment_logs", ["source", "created_at"], unique=False)


def downgrade():
    op.drop_index("ix_payment_log_source_created", table_name="payment_logs")
