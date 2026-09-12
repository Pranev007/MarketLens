"""Entry point: clean the raw Olist extract and validate the result.

    python -m marketlens.data_processing

Reads ``data/raw/olist/*.csv``, applies the cleaning rules, runs the
data-quality checks, and writes the analysis-ready tables to
``data/processed`` as Parquet plus a Markdown report to ``reports/``.
"""

from __future__ import annotations

import logging
import sys

import pandas as pd

from marketlens.config import OLIST_DIR, PROCESSED_DIR, REPORTS_DIR, ensure_directories
from marketlens.data_ingestion.download import download, files_present
from marketlens.data_processing.cleaning import clean_dataset
from marketlens.data_processing.validation import format_report, validate_dataset
from marketlens.utils.logging_config import configure_logging

logger = logging.getLogger(__name__)

#: Source file -> the name the pipeline uses for it.
SOURCE_FILES: dict[str, str] = {
    "olist_customers_dataset": "customers",
    "olist_sellers_dataset": "sellers",
    "olist_products_dataset": "products",
    "olist_orders_dataset": "orders",
    "olist_order_items_dataset": "order_items",
    "olist_order_payments_dataset": "order_payments",
    "olist_order_reviews_dataset": "order_reviews",
    "product_category_name_translation": "category_translation",
}


def load_raw() -> dict[str, pd.DataFrame]:
    """Read the raw Olist CSVs, downloading them first if they are absent."""
    if not files_present():
        logger.info("Olist files not found - downloading")
        download()
    return {
        name: pd.read_csv(OLIST_DIR / f"{filename}.csv")
        for filename, name in SOURCE_FILES.items()
    }


def main() -> int:
    configure_logging()
    ensure_directories()

    raw = load_raw()
    logger.info("Raw extract: %s", {t: f"{len(df):,}" for t, df in raw.items()})

    logger.info("Cleaning...")
    result = clean_dataset(raw)

    logger.info("Validating...")
    checks = validate_dataset(result.tables)

    for name, frame in result.tables.items():
        path = PROCESSED_DIR / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        logger.info("Wrote %-16s %8s rows -> %s", name, f"{len(frame):,}", path.name)

    result.log.to_csv(PROCESSED_DIR / "cleaning_log.csv", index=False)
    checks.to_csv(PROCESSED_DIR / "data_quality_checks.csv", index=False)

    report_path = REPORTS_DIR / "data_quality_report.md"
    report_path.write_text(
        format_report(checks, result.log, result.row_counts), encoding="utf-8"
    )
    logger.info("Wrote data-quality report -> %s", report_path.name)

    failures = int((checks["status"] == "FAIL").sum())
    if failures:
        logger.error("%s validation check(s) FAILED - see %s", failures, report_path.name)
        print(checks[checks["status"] == "FAIL"].to_string(index=False))
        return 1
    logger.info("All %s validation checks passed.", len(checks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
