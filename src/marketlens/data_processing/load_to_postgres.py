"""Entry point: build the PostgreSQL database from the cleaned dataset.

    python -m marketlens.data_processing.load_to_postgres

Creates the schema defined in ``sql/schema.sql`` and bulk-loads the Parquet
files from ``data/processed``. Requires a reachable PostgreSQL instance and a
database that already exists (see the README for the two-line setup).
"""

from __future__ import annotations

import logging
import sys

import pandas as pd

from marketlens.config import DATABASE, PROCESSED_DIR
from marketlens.data_processing.database import (
    LOAD_ORDER,
    create_database_if_missing,
    create_schema,
    get_engine,
    load_tables,
    server_available,
)
from marketlens.utils.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()

    if not server_available():
        logger.error(
            "Cannot reach PostgreSQL at %s:%s. Start the server and check the "
            "credentials in .env (POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_PORT).",
            DATABASE.host, DATABASE.port,
        )
        return 1

    # Saves a manual createdb step on a fresh clone.
    if create_database_if_missing():
        logger.info("Database %s did not exist and was created.", DATABASE.database)

    missing = [t for t in LOAD_ORDER if not (PROCESSED_DIR / f"{t}.parquet").exists()]
    if missing:
        logger.error(
            "Missing processed files: %s. Run `python -m marketlens.data_processing` first.",
            missing,
        )
        return 1

    tables = {t: pd.read_parquet(PROCESSED_DIR / f"{t}.parquet") for t in LOAD_ORDER}
    engine = get_engine()

    logger.info("Creating schema in %s", DATABASE.database)
    create_schema(engine)

    logger.info("Loading data...")
    counts = load_tables(engine, tables)

    logger.info("Row counts in PostgreSQL: %s", {k: f"{v:,}" for k, v in counts.items()})
    mismatched = {t: (len(tables[t]), counts[t]) for t in LOAD_ORDER if len(tables[t]) != counts[t]}
    if mismatched:
        logger.error("Row count mismatch (expected, loaded): %s", mismatched)
        return 1

    logger.info("Database build complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
