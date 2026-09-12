"""PostgreSQL access: schema creation, bulk loading and query execution.

Loading uses PostgreSQL's ``COPY`` rather than row-by-row inserts. On 119k
order lines that is the difference between a few seconds and a few minutes,
and it is how a real load job would be written.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from marketlens.config import DATABASE, SQL_DIR

logger = logging.getLogger(__name__)

#: Load order matters: parents before children, because of the foreign keys.
LOAD_ORDER: tuple[str, ...] = (
    "customers", "sellers", "products", "orders",
    "order_items", "order_payments", "order_reviews",
)

#: Columns written per table, in the order the schema declares them.
LOAD_COLUMNS: dict[str, list[str]] = {
    "customers": [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state", "customer_region",
    ],
    "sellers": [
        "seller_id", "seller_zip_code_prefix", "seller_city",
        "seller_state", "seller_region",
    ],
    "products": [
        "product_id", "category_pt", "category_en", "category_group",
        "product_name_length", "product_description_length", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm",
        "product_width_cm", "product_volume_cm3",
    ],
    "orders": [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date",
    ],
    "order_items": [
        "order_id", "order_item_id", "product_id", "seller_id",
        "shipping_limit_date", "price", "freight_value",
    ],
    "order_payments": [
        "order_id", "payment_sequential", "payment_type",
        "payment_installments", "payment_value",
    ],
    "order_reviews": [
        "review_id", "order_id", "review_score", "review_comment_title",
        "review_comment_message", "review_creation_date", "review_answer_timestamp",
    ],
}


def get_engine(url: str | None = None, **kwargs) -> Engine:
    """Create a SQLAlchemy engine for the configured database."""
    return create_engine(url or DATABASE.url, future=True, **kwargs)


def database_available(timeout_seconds: int = 3) -> bool:
    """Return True when the configured PostgreSQL instance accepts a query.

    Used by the analytics layer to decide whether to read from the database or
    fall back to the processed files, so the project stays runnable on a
    machine with no PostgreSQL installed.
    """
    try:
        engine = get_engine(connect_args={"connect_timeout": timeout_seconds})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - any failure means "not available"
        logger.debug("PostgreSQL not available: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def server_available(timeout_seconds: int = 3) -> bool:
    """Return True when the PostgreSQL *server* is reachable.

    Distinct from ``database_available``: the server can be running while the
    application database does not exist yet, which is exactly the state a fresh
    clone starts in.
    """
    try:
        engine = get_engine(DATABASE.admin_url, connect_args={"connect_timeout": timeout_seconds})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("PostgreSQL server not reachable: %s", exc)
        return False


def create_database_if_missing() -> bool:
    """Create the application database when it does not already exist.

    Saves a manual ``createdb`` step on a fresh clone. CREATE DATABASE cannot
    run inside a transaction, hence the AUTOCOMMIT isolation level, and it is
    issued against the ``postgres`` maintenance database.

    Returns True when the database was created, False when it already existed.
    """
    if database_available():
        return False

    engine = get_engine(DATABASE.admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": DATABASE.database},
        ).scalar()
        if exists:
            return False
        # The database name comes from configuration, not user input, and
        # cannot be parameterised in DDL - so it is quoted defensively.
        safe_name = DATABASE.database.replace('"', '""')
        connection.execute(text(f'CREATE DATABASE "{safe_name}"'))
    logger.info("Created database %s", DATABASE.database)
    return True


def drop_database_if_exists() -> bool:
    """Drop the application database. Used by the rebuild path and by tests."""
    engine = get_engine(DATABASE.admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        safe_name = DATABASE.database.replace('"', '""')
        connection.execute(text(f'DROP DATABASE IF EXISTS "{safe_name}" WITH (FORCE)'))
    logger.info("Dropped database %s", DATABASE.database)
    return True


def create_schema(engine: Engine, schema_path: Path | None = None) -> None:
    """Drop and recreate the analytical schema from ``sql/schema.sql``."""
    path = schema_path or (SQL_DIR / "schema.sql")
    ddl = path.read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.execute(text(ddl))
    logger.info("Applied schema from %s", path.name)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_tables(engine: Engine, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Bulk-load the cleaned tables into PostgreSQL using COPY.

    Returns the row count actually committed per table, read back from the
    database rather than assumed from the frame length.
    """
    loaded: dict[str, int] = {}
    raw_connection = engine.raw_connection()
    try:
        cursor = raw_connection.cursor()
        for name in LOAD_ORDER:
            frame = tables[name][LOAD_COLUMNS[name]]
            buffer = io.StringIO()
            frame.to_csv(buffer, index=False, header=False, na_rep="\\N")
            buffer.seek(0)
            columns = ", ".join(LOAD_COLUMNS[name])
            cursor.copy_expert(
                f"COPY {name} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
                buffer,
            )
            logger.info("Loaded %-13s %8s rows", name, f"{len(frame):,}")
        raw_connection.commit()

        for name in LOAD_ORDER:
            cursor.execute(f"SELECT COUNT(*) FROM {name}")
            loaded[name] = cursor.fetchone()[0]
        cursor.close()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        raw_connection.close()

    # ANALYZE lets the planner choose sensible plans for the analysis queries.
    with engine.begin() as connection:
        connection.execute(text("ANALYZE"))
    return loaded


def read_table(engine: Engine, name: str) -> pd.DataFrame:
    """Read a whole table into a DataFrame."""
    return pd.read_sql_table(name, engine)


def read_query(engine: Engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a single SQL statement and return the result as a DataFrame."""
    return pd.read_sql_query(text(sql), engine, params=params)


# ---------------------------------------------------------------------------
# Running the analysis query files
# ---------------------------------------------------------------------------

#: Analysis queries are separated by a banner comment carrying the query name:
#:     -- ============ QUERY 07: Top products by revenue ============
_QUERY_HEADER = re.compile(r"^--\s*=+\s*QUERY\s+(\d+):\s*(.+?)\s*=*$", re.MULTILINE)


def split_query_file(path: Path) -> list[tuple[str, str, str]]:
    """Split an analysis SQL file into (number, title, sql) blocks.

    Keeping each business question in its own labelled block means the file
    stays readable as a document, while still being executable statement by
    statement from Python and from psql.
    """
    content = path.read_text(encoding="utf-8")
    matches = list(_QUERY_HEADER.finditer(content))
    blocks: list[tuple[str, str, str]] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sql = content[start:end].strip().rstrip(";")
        if sql:
            blocks.append((match.group(1), match.group(2), sql))
    return blocks


def run_query_file(engine: Engine, path: Path) -> list[tuple[str, str, pd.DataFrame]]:
    """Execute every labelled query in a file and return their results."""
    results = []
    for number, title, sql in split_query_file(path):
        frame = pd.read_sql_query(text(sql), engine)
        results.append((number, title, frame))
    return results
