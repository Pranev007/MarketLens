"""Entry point: execute every analysis query against PostgreSQL.

    python -m marketlens.data_processing.run_sql_analysis

Runs all labelled queries in ``sql/*.sql``, writes each result to
``reports/sql_results/`` as CSV, and prints a pass/fail summary. This doubles
as a regression check: if a query stops running, this is what catches it.
"""

from __future__ import annotations

import logging
import sys
import time

from marketlens.config import DATABASE, REPORTS_DIR, SQL_DIR
from marketlens.data_processing.database import (
    database_available,
    get_engine,
    split_query_file,
)
from marketlens.utils.logging_config import configure_logging

logger = logging.getLogger(__name__)

#: Query files in the order they tell the analytical story.
QUERY_FILES = (
    "revenue_analysis.sql",
    "product_analysis.sql",
    "customer_analysis.sql",
    "retention_analysis.sql",
    "delivery_reviews_analysis.sql",
)


def main() -> int:
    configure_logging()

    if not database_available():
        logger.error(
            "Cannot reach PostgreSQL at %s:%s - run "
            "`python -m marketlens.data_processing.load_to_postgres` first.",
            DATABASE.host, DATABASE.port,
        )
        return 1

    import pandas as pd
    from sqlalchemy import text

    engine = get_engine()
    output_dir = REPORTS_DIR / "sql_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    total = failures = 0
    for filename in QUERY_FILES:
        path = SQL_DIR / filename
        if not path.exists():
            logger.error("Missing query file: %s", filename)
            failures += 1
            continue

        blocks = split_query_file(path)
        logger.info("%s (%s queries)", filename, len(blocks))
        for number, title, sql in blocks:
            total += 1
            started = time.perf_counter()
            try:
                frame = pd.read_sql_query(text(sql), engine)
            except Exception as exc:  # noqa: BLE001 - report and keep going
                failures += 1
                logger.error("  Q%s %-45s FAILED: %s", number, title[:45], str(exc)[:160])
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000
            frame.to_csv(output_dir / f"q{number}_{_slug(title)}.csv", index=False)
            logger.info("  Q%s %-45s %5s rows  %6.0f ms",
                        number, title[:45], f"{len(frame):,}", elapsed_ms)

    logger.info("%s/%s queries succeeded; results in %s",
                total - failures, total, output_dir)
    return 1 if failures else 0


def _slug(title: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in title]
    return "".join(keep).strip("_").replace("__", "_")[:60]


if __name__ == "__main__":
    sys.exit(main())
