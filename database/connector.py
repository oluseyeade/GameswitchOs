import os
from pathlib import Path
from urllib.parse import quote_plus

import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from extensions import db


def build_database_uri() -> str:
    database_url = (
        os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()

    if database_url:
        # Railway usually provides mysql://
        if database_url.startswith("mysql://"):
            database_url = database_url.replace(
                "mysql://",
                "mysql+pymysql://",
                1,
            )

        url = make_url(database_url)

        if url.drivername != "mysql+pymysql":
            raise RuntimeError(
                "Database URL must use mysql+pymysql."
            )

        return str(url)
    settings = get_connection_settings()
    if settings["driver"] != "mysql+pymysql":
        raise RuntimeError("DATABASE_DRIVER must be mysql+pymysql; MySQL is the only supported database.")
    if not settings["database"]:
        raise RuntimeError("MYSQL_DATABASE must be configured.")

    user = quote_plus(settings["user"])
    password = quote_plus(settings["password"])
    host = settings["host"]
    port = settings["port"]
    database = quote_plus(settings["database"])
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def get_connection_settings() -> dict:
    database_url = (
    os.getenv("SQLALCHEMY_DATABASE_URI")
    or os.getenv("DATABASE_URL")
    or ""
).strip()
    if database_url:
        url = make_url(database_url)
        driver = url.drivername or "mysql+pymysql"
        if driver == "mysql":
            driver = "mysql+pymysql"
        return {
            "driver": driver,
            "host": url.host or "127.0.0.1",
            "port": url.port or 3306,
            "database": url.database or "",
            "user": url.username or "",
            "password": url.password or "",
        }

    return {
    "driver": "mysql+pymysql",
    "host": os.getenv("MYSQLHOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQLPORT") or os.getenv("MYSQL_PORT", "3306")),
    "database": os.getenv("MYSQLDATABASE") or os.getenv("MYSQL_DATABASE", ""),
    "user": os.getenv("MYSQLUSER") or os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQLPASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
}


def create_database_if_missing() -> str:
    settings = get_connection_settings()
    connection = pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings['database']}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()
    return settings["database"]


def load_schema(schema_path: str | None = None) -> None:
    settings = get_connection_settings()
    sql_path = Path(schema_path or Path(__file__).with_name("schema.sql"))
    statements = [item.strip() for item in sql_path.read_text(encoding="utf-8").split(";") if item.strip()]

    connection = pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        database=settings["database"],
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
    finally:
        connection.close()


def verify_sqlalchemy_connection(database_uri: str | None = None) -> dict[str, str | int | None]:
    engine = create_engine(database_uri or build_database_uri())
    try:
        with engine.connect() as connection:
            row = connection.execute(text("SELECT 1, DATABASE(), VERSION()")).one()
            return {
                "select_1": row[0],
                "database": row[1],
                "version": row[2],
                "driver": engine.url.drivername,
                "dialect": engine.dialect.name,
            }
    finally:
        engine.dispose()


def init_database(app):
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault(
        "SQLALCHEMY_ENGINE_OPTIONS",
        {
            "pool_pre_ping": True,
            "pool_recycle": int(os.getenv("MYSQL_POOL_RECYCLE", "280")),
        },
    )
    db.init_app(app)
    return db
