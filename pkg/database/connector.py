import os
from pathlib import Path
from urllib.parse import quote_plus

import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from pkg.extensions import db

# Install PyMySQL as MySQLdb globally so any legacy mysqldb/mysqlconnector references transparently use PyMySQL
pymysql.install_as_MySQLdb()


def normalize_mysql_scheme(url_str: str) -> str:
    """Normalize database connection schemes to use mysql+pymysql."""
    if not url_str:
        return ""
    url_str = url_str.strip()
    if url_str.startswith("mysql://"):
        url_str = url_str.replace("mysql://", "mysql+pymysql://", 1)
    elif url_str.startswith("mysql+mysqlconnector://"):
        url_str = url_str.replace("mysql+mysqlconnector://", "mysql+pymysql://", 1)
    elif url_str.startswith("mysql+mysqldb://"):
        url_str = url_str.replace("mysql+mysqldb://", "mysql+pymysql://", 1)
    return url_str


def build_database_uri() -> str:
    """Build and validate a SQLAlchemy database URI using PyMySQL.
    
    Priority order:
    1. Railway / Cloud environment database URLs:
       MYSQL_URL, DATABASE_URL, MYSQLURL, MYSQLPRIVATEURL, MYSQL_PRIVATE_URL,
       DATABASE_PRIVATE_URL, DATABASE_PUBLIC_URL, MYSQL_PUBLIC_URL, RAILWAY_MYSQL_URL
    2. Individual MySQL environment variables:
       (MYSQLHOST / MYSQL_HOST / DB_HOST / MYSQL_HOSTNAME) + (MYSQLPASSWORD / MYSQL_PASSWORD / DB_PASSWORD)
    3. Explicit SQLALCHEMY_DATABASE_URI
    4. Local development default settings (127.0.0.1)
    """
    database_url = (
        os.getenv("MYSQL_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("MYSQLURL")
        or os.getenv("MYSQLPRIVATEURL")
        or os.getenv("MYSQL_PRIVATE_URL")
        or os.getenv("DATABASE_PRIVATE_URL")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("MYSQL_PUBLIC_URL")
        or os.getenv("RAILWAY_MYSQL_URL")
        or ""
    ).strip()

    if database_url:
        database_url = normalize_mysql_scheme(database_url)
        url = make_url(database_url)
        if url.drivername in ("mysql", "mysqlconnector", "mysqldb"):
            url = url.set(drivername="mysql+pymysql")

        if not url.drivername.startswith("mysql"):
            raise RuntimeError(
                f"Unsupported database scheme: {url.drivername}. Only MySQL databases (mysql+pymysql) are supported."
            )

        return str(url)

    # Check individual MySQL environment variables
    host = (
        os.getenv("MYSQLHOST")
        or os.getenv("MYSQL_HOST")
        or os.getenv("DB_HOST")
        or os.getenv("MYSQL_HOSTNAME")
    )
    password = (
        os.getenv("MYSQLPASSWORD")
        or os.getenv("MYSQL_PASSWORD")
        or os.getenv("DB_PASSWORD")
    )

    if host:
        user = quote_plus(
            os.getenv("MYSQLUSER")
            or os.getenv("MYSQL_USER")
            or os.getenv("DB_USER")
            or "root"
        )
        pass_encoded = quote_plus(password or "")
        port = int(
            os.getenv("MYSQLPORT")
            or os.getenv("MYSQL_PORT")
            or os.getenv("DB_PORT")
            or "3306"
        )
        database = quote_plus(
            os.getenv("MYSQLDATABASE")
            or os.getenv("MYSQL_DATABASE")
            or os.getenv("DB_NAME")
            or os.getenv("DB_DATABASE")
            or "railway"
        )
        return f"mysql+pymysql://{user}:{pass_encoded}@{host}:{port}/{database}"

    # Check explicit SQLALCHEMY_DATABASE_URI
    database_url = os.getenv("SQLALCHEMY_DATABASE_URI", "").strip()
    if database_url:
        database_url = normalize_mysql_scheme(database_url)
        url = make_url(database_url)
        if url.drivername in ("mysql", "mysqlconnector", "mysqldb"):
            url = url.set(drivername="mysql+pymysql")
        return str(url)

    import logging
    logging.warning(
        "No production MySQL environment variables (MYSQL_URL, DATABASE_URL, or MYSQLHOST) were detected. "
        "Defaulting connection to local 127.0.0.1:3306."
    )

    # Local fallback
    settings = get_connection_settings()
    user = quote_plus(settings["user"])
    password = quote_plus(settings["password"])
    host_str = settings["host"]
    port_int = settings["port"]
    database_str = quote_plus(settings["database"])
    return f"mysql+pymysql://{user}:{password}@{host_str}:{port_int}/{database_str}"


def get_connection_settings() -> dict:
    database_url = (
        os.getenv("MYSQL_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("MYSQLURL")
        or os.getenv("MYSQLPRIVATEURL")
        or os.getenv("MYSQL_PRIVATE_URL")
        or os.getenv("DATABASE_PRIVATE_URL")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("MYSQL_PUBLIC_URL")
        or os.getenv("RAILWAY_MYSQL_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or ""
    ).strip()

    if database_url:
        database_url = normalize_mysql_scheme(database_url)
        url = make_url(database_url)
        driver = url.drivername or "mysql+pymysql"
        if driver in ("mysql", "mysqlconnector", "mysqldb"):
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
        "host": os.getenv("MYSQLHOST") or os.getenv("MYSQL_HOST") or os.getenv("DB_HOST") or "127.0.0.1",
        "port": int(os.getenv("MYSQLPORT") or os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306"),
        "database": os.getenv("MYSQLDATABASE") or os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME") or "gameswitchos_demo",
        "user": os.getenv("MYSQLUSER") or os.getenv("MYSQL_USER") or os.getenv("DB_USER") or "root",
        "password": os.getenv("MYSQLPASSWORD") or os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD") or "",
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
    target_uri = normalize_mysql_scheme(database_uri) if database_uri else build_database_uri()
    engine = create_engine(target_uri)
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
    # Ensure URI is built dynamically and normalized to use mysql+pymysql
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
