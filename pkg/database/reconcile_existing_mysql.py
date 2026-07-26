"""Apply only additive, data-preserving changes to the existing MySQL schema.

This utility is intentionally opt-in. It requires a schema-only backup path and
never drops or recreates databases, tables, columns, indexes, or constraints.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pkg.database.connector import get_connection_settings

MIGRATION_FILES = (
    PROJECT_ROOT / "database" / "migrations" / "20260713_tuya_integration.sql",
    PROJECT_ROOT / "database" / "migrations" / "20260719_paystack_module.sql",
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "game"


def _execute_sql_file(cursor, path: Path) -> None:
    if not path.is_file():
        return
    sql = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--")
    )
    statements = [statement.strip() for statement in sql.split(";")]
    for statement in statements:
        if statement:
            cursor.execute(statement)


def _ensure_game_columns(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM games")
    existing = {row[0] for row in cursor.fetchall()}
    columns = {
        "slug": "VARCHAR(120) NULL",
        "description": "TEXT NULL",
        "category": "VARCHAR(80) NULL",
        "console_type": "VARCHAR(80) NULL",
        "status": "VARCHAR(20) NULL",
        "display_order": "INT NULL",
        "cover_image_path": "VARCHAR(255) NULL",
        "banner_image_path": "VARCHAR(255) NULL",
        "is_deleted": "BOOLEAN NULL",
        "archived_at": "DATETIME NULL",
        "deleted_at": "DATETIME NULL",
        "created_at": "DATETIME NULL",
        "updated_at": "DATETIME NULL",
        "created_by": "INT NULL",
        "updated_by": "INT NULL",
    }
    for name, definition in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE games ADD COLUMN {name} {definition}")

    cursor.execute("SELECT id, title, slug FROM games ORDER BY id")
    used_slugs: set[str] = set()
    for game_id, title, slug in cursor.fetchall():
        candidate = _slugify(title)
        if slug and slug not in used_slugs:
            candidate = slug
        base = candidate
        suffix = 2
        while candidate in used_slugs:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(candidate)
        cursor.execute("UPDATE games SET slug = %s WHERE id = %s", (candidate, game_id))

    cursor.execute("UPDATE games SET category = COALESCE(NULLIF(category, ''), 'action')")
    cursor.execute("UPDATE games SET console_type = COALESCE(NULLIF(console_type, ''), 'console')")
    cursor.execute("UPDATE games SET status = CASE WHEN is_active = 1 THEN 'active' ELSE 'inactive' END WHERE status IS NULL OR status = ''")
    cursor.execute("UPDATE games SET display_order = 0 WHERE display_order IS NULL")
    cursor.execute("UPDATE games SET cover_image_path = image_path WHERE cover_image_path IS NULL")
    cursor.execute("UPDATE games SET is_deleted = COALESCE(is_deleted, 0)")
    cursor.execute("UPDATE games SET archived_at = NULL WHERE archived_at IS NULL")
    cursor.execute("UPDATE games SET deleted_at = NULL WHERE deleted_at IS NULL")
    cursor.execute("UPDATE games SET created_at = UTC_TIMESTAMP() WHERE created_at IS NULL")
    cursor.execute("UPDATE games SET updated_at = UTC_TIMESTAMP() WHERE updated_at IS NULL")

    cursor.execute("SHOW INDEX FROM games WHERE Key_name = 'uq_games_slug'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE games ADD UNIQUE KEY uq_games_slug (slug)")

    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'games' "
        "AND CONSTRAINT_NAME = 'fk_games_created_by_users'"
    )
    if not cursor.fetchone():
        cursor.execute(
            "ALTER TABLE games ADD CONSTRAINT fk_games_created_by_users "
            "FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL"
        )

    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'games' "
        "AND CONSTRAINT_NAME = 'fk_games_updated_by_users'"
    )
    if not cursor.fetchone():
        cursor.execute(
            "ALTER TABLE games ADD CONSTRAINT fk_games_updated_by_users "
            "FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile existing MySQL tables without destructive DDL.")
    parser.add_argument("--apply", action="store_true", help="Apply additive reconciliation changes.")
    parser.add_argument("--backup", type=Path, required=True, help="Existing schema-only backup file.")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("Refusing to change the database without --apply.")
    if not args.backup.is_file() or args.backup.stat().st_size == 0:
        raise SystemExit("Refusing to change the database without a non-empty schema backup.")

    load_dotenv()
    settings = get_connection_settings()
    connection = pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        database=settings["database"],
        autocommit=False,
        charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            selected_database = cursor.fetchone()[0]
            if selected_database != settings["database"]:
                raise RuntimeError(f"Connected to {selected_database!r}, expected {settings['database']!r}.")
            for migration_file in MIGRATION_FILES:
                _execute_sql_file(cursor, migration_file)
            _ensure_game_columns(cursor)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"reconciled:{settings['database']}")
    print(f"backup:{args.backup}")
    print(f"completed-at:{datetime.utcnow().isoformat()}Z")


if __name__ == "__main__":
    main()
