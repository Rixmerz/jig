"""SQLite database connection management."""

import sqlite3
from pathlib import Path
from typing import Any

from jig.engines.dcc.config import DB_PATH
from jig.engines.dcc.db.schema import SCHEMA_SQL
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)

_connection: sqlite3.Connection | None = None


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert row to dictionary."""
    fields = [column[0] for column in cursor.description]
    return dict(zip(fields, row))


def init_database(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Initialize the database connection and schema."""
    global _connection

    if _connection is not None:
        return _connection

    path = Path(db_path) if db_path else DB_PATH

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing database at {path}")

    _connection = sqlite3.connect(str(path), check_same_thread=False)
    _connection.row_factory = dict_factory

    # Enable optimizations
    _connection.execute("PRAGMA journal_mode = WAL")
    _connection.execute("PRAGMA foreign_keys = ON")
    _connection.execute("PRAGMA synchronous = NORMAL")

    # Initialize schema
    _connection.executescript(SCHEMA_SQL)
    _connection.commit()

    logger.info("Database initialized successfully")
    return _connection


def get_database() -> sqlite3.Connection:
    """Get the database connection."""
    global _connection

    if _connection is None:
        return init_database()

    return _connection


def close_database() -> None:
    """Close the database connection."""
    global _connection

    if _connection is not None:
        _connection.close()
        _connection = None
        logger.info("Database connection closed")


class get_connection:
    """Context manager for database connection."""

    def __enter__(self) -> sqlite3.Connection:
        return get_database()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Don't close - we maintain a singleton connection
        pass
