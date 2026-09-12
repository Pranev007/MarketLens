"""Entry point: download the Olist dataset into ``data/raw/olist``.

    python -m marketlens.data_ingestion

Uses the Kaggle API when credentials are available, otherwise a public mirror.
Verifies row counts against the published dataset either way.
"""

from __future__ import annotations

import logging
import sys

from marketlens.config import ensure_directories
from marketlens.data_ingestion.download import (
    download,
    files_present,
    kaggle_credentials_available,
)
from marketlens.utils.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    ensure_directories()

    logger.info(
        "Kaggle credentials: %s",
        "found" if kaggle_credentials_available() else "not found (will use the mirror)",
    )
    try:
        target = download()
    except Exception as exc:  # noqa: BLE001
        logger.error("Download failed: %s", exc)
        return 1

    logger.info("Olist dataset ready in %s", target)
    return 0 if files_present() else 1


if __name__ == "__main__":
    sys.exit(main())
