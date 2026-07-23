"""extend games catalog foundation

Revision ID: 7a5b2f8d9d21
Revises: f70bc3e88dd1
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a5b2f8d9d21'
down_revision = 'f70bc3e88dd1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("slug", sa.String(length=120), nullable=True))
    op.add_column("games", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("games", sa.Column("category", sa.String(length=80), nullable=True, server_default="action"))
    op.add_column("games", sa.Column("console_type", sa.String(length=80), nullable=True, server_default="console"))
    op.add_column("games", sa.Column("status", sa.String(length=20), nullable=True, server_default="active"))
    op.add_column("games", sa.Column("display_order", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("games", sa.Column("cover_image_path", sa.String(length=255), nullable=True))
    op.add_column("games", sa.Column("banner_image_path", sa.String(length=255), nullable=True))
    op.add_column("games", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("games", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("games", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("updated_by", sa.Integer(), nullable=True))

    op.execute(
        "UPDATE games SET slug = LOWER(REPLACE(title, ' ', '-')) WHERE slug IS NULL OR slug = ''"
    )
    op.execute(
        "UPDATE games SET category = 'action' WHERE category IS NULL OR category = ''"
    )
    op.execute(
        "UPDATE games SET console_type = 'console' WHERE console_type IS NULL OR console_type = ''"
    )
    op.execute(
        "UPDATE games SET status = 'active' WHERE status IS NULL OR status = ''"
    )
    op.execute(
        "UPDATE games SET display_order = 0 WHERE display_order IS NULL"
    )
    op.execute(
        "UPDATE games SET cover_image_path = image_path WHERE cover_image_path IS NULL"
    )
    op.execute(
        "UPDATE games SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
    )
    op.execute(
        "UPDATE games SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"
    )

    op.alter_column("games", "slug", nullable=False)
    op.alter_column("games", "category", nullable=False)
    op.alter_column("games", "console_type", nullable=False)
    op.alter_column("games", "status", nullable=False)
    op.alter_column("games", "display_order", nullable=False)
    op.alter_column("games", "created_at", nullable=False)
    op.alter_column("games", "updated_at", nullable=False)

    op.create_unique_constraint("uq_games_slug", "games", ["slug"])
    op.create_foreign_key(
        "fk_games_created_by_users",
        "games",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_games_updated_by_users",
        "games",
        "users",
        ["updated_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_games_updated_by_users", "games", type_="foreignkey")
    op.drop_constraint("fk_games_created_by_users", "games", type_="foreignkey")
    op.drop_constraint("uq_games_slug", "games", type_="unique")
    op.drop_column("games", "updated_by")
    op.drop_column("games", "created_by")
    op.drop_column("games", "updated_at")
    op.drop_column("games", "created_at")
    op.drop_column("games", "banner_image_path")
    op.drop_column("games", "cover_image_path")
    op.drop_column("games", "display_order")
    op.drop_column("games", "status")
    op.drop_column("games", "console_type")
    op.drop_column("games", "category")
    op.drop_column("games", "description")
    op.drop_column("games", "slug")
