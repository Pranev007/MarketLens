"""Run the whole pipeline end to end.

    python -m marketlens.pipeline              # download, clean, analyse
    python -m marketlens.pipeline --with-db    # also build and query PostgreSQL

The individual stages remain independently runnable; this exists so a fresh
clone can go from nothing to a full set of reports with one command.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from marketlens.utils.logging_config import configure_logging

logger = logging.getLogger(__name__)


def _stage(name: str, function) -> int:
    logger.info("=" * 70)
    logger.info("STAGE: %s", name)
    logger.info("=" * 70)
    started = time.perf_counter()
    code = function() or 0
    logger.info("%s finished in %.1fs (exit %s)", name, time.perf_counter() - started, code)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MarketLens pipeline.")
    parser.add_argument(
        "--with-db", action="store_true",
        help="Also load PostgreSQL and execute every SQL analysis query.",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Reuse the CSVs already in data/raw/olist instead of checking for them.",
    )
    args = parser.parse_args(argv)

    configure_logging()

    from marketlens.analytics import __main__ as analytics_main
    from marketlens.data_ingestion import __main__ as ingestion_main
    from marketlens.data_processing import __main__ as processing_main

    if not args.skip_download:
        _stage("Download the Olist dataset", ingestion_main.main)

    code = _stage("Clean and validate", processing_main.main)
    if code:
        logger.error("Data quality checks failed; stopping.")
        return code

    if args.with_db:
        from marketlens.data_processing import load_to_postgres, run_sql_analysis

        code = _stage("Load PostgreSQL", load_to_postgres.main)
        if code:
            return code
        code = _stage("Run SQL analysis", run_sql_analysis.main)
        if code:
            return code

    code = _stage("Python analysis and reports", analytics_main.main)
    if code:
        return code

    logger.info("=" * 70)
    logger.info("Pipeline complete. See reports/ for output.")
    logger.info("Launch the dashboard with:  streamlit run dashboard/app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
