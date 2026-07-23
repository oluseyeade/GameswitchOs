import getpass
import os
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv
from pymysql.err import OperationalError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connector import (
    create_database_if_missing,
    load_schema,
    verify_sqlalchemy_connection,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify or explicitly provision the GameSwitchOS MySQL database.")
    parser.add_argument(
        "--provision",
        action="store_true",
        help="Explicitly create the configured database if missing and load the baseline schema.",
    )
    args = parser.parse_args()
    load_dotenv()
    try:
        database_name = os.getenv("MYSQL_DATABASE", "gameswitchos_demo")
        if args.provision:
            database_name = create_database_if_missing()
            load_schema()
        verification = verify_sqlalchemy_connection()
    except OperationalError as error:
        if error.args and error.args[0] == 1045:
            password = getpass.getpass("MySQL password: ")
            os.environ["MYSQL_PASSWORD"] = password
            if args.provision:
                database_name = create_database_if_missing()
                load_schema()
                verification = verify_sqlalchemy_connection()
        else:
            raise
            print(f"database:{database_name}")
            print(f"driver:{verification['driver']}")
            print(f"dialect:{verification['dialect']}")
            print(f"select-1:{verification['select_1']}")
            print(f"server-version:{verification['version']}")


if __name__ == "__main__":
    main()
