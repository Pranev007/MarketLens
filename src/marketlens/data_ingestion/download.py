"""Fetching the Olist dataset.

The Brazilian E-Commerce Public Dataset by Olist lives on Kaggle, which
requires an account to download. Two routes are supported:

1. **Kaggle API** - used automatically when ``~/.kaggle/kaggle.json`` exists or
   ``KAGGLE_USERNAME``/``KAGGLE_KEY`` are set. This gets the canonical current
   snapshot and is the preferred route.
2. **Public GitHub mirror** - used otherwise, so the project runs for someone
   who has cloned it without a Kaggle account.

The mirror is verified against the published row counts after download, and any
table that does not match is reported rather than silently accepted. The
reviews table on the mirror is an earlier Olist snapshot (100,000 rows against
the current 99,224) that contains duplicate reviews; the cleaning layer resolves
those and reports how many it removed.

Licence: the dataset is published under CC BY-NC-SA 4.0. It is not committed to
this repository - it is downloaded on demand and gitignored.
"""

from __future__ import annotations

import logging
import os
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import urllib.request

from marketlens.config import OLIST_DIR

logger = logging.getLogger(__name__)

KAGGLE_DATASET = "olistbr/brazilian-ecommerce"

MIRROR_BASE = (
    "https://raw.githubusercontent.com/"
    "spdrio/Brazilian-E-Commerce-Public-Dataset-by-Olist/master/files"
)

#: Row counts published for the dataset, used to verify a download.
#: order_reviews is the one table that differs between snapshots - see the
#: module docstring - so it carries both known values.
EXPECTED_ROWS: dict[str, int | tuple[int, ...]] = {
    "olist_customers_dataset": 99_441,
    "olist_orders_dataset": 99_441,
    "olist_order_items_dataset": 112_650,
    "olist_order_payments_dataset": 103_886,
    "olist_order_reviews_dataset": (99_224, 100_000),
    "olist_products_dataset": 32_951,
    "olist_sellers_dataset": 3_095,
    "product_category_name_translation": 71,
}

#: Tables the pipeline actually uses. The geolocation table is not downloaded:
#: it is the largest file in the dataset and is only needed for mapping
#: latitude/longitude, which this project does not do.
REQUIRED_FILES: tuple[str, ...] = tuple(EXPECTED_ROWS)


def kaggle_credentials_available() -> bool:
    """True when the Kaggle API can authenticate."""
    if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
        return True
    return (Path.home() / ".kaggle" / "kaggle.json").exists()


def files_present(directory: Path | None = None) -> bool:
    """True when every required CSV is already on disk."""
    target = directory or OLIST_DIR
    return all((target / f"{name}.csv").exists() for name in REQUIRED_FILES)


def download(directory: Path | None = None, force: bool = False) -> Path:
    """Ensure the Olist CSVs are present, downloading them if needed."""
    target = directory or OLIST_DIR
    target.mkdir(parents=True, exist_ok=True)

    if files_present(target) and not force:
        logger.info("Olist files already present in %s", target)
        return target

    if kaggle_credentials_available():
        logger.info("Kaggle credentials found - downloading from Kaggle")
        try:
            _download_from_kaggle(target)
            _verify(target)
            return target
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail
            logger.warning("Kaggle download failed (%s); falling back to the mirror", exc)

    logger.info("Downloading from the public mirror")
    _download_from_mirror(target)
    _verify(target)
    return target


def _download_from_kaggle(target: Path) -> None:
    """Download and unpack the dataset using the Kaggle API."""
    from kaggle.api.kaggle_api_extended import KaggleApi  # imported lazily

    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(KAGGLE_DATASET, path=str(target), quiet=False)

    archive = target / "brazilian-ecommerce.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
        archive.unlink()

    # Kaggle may unpack into a subdirectory; flatten if so.
    for name in REQUIRED_FILES:
        if not (target / f"{name}.csv").exists():
            found = next(target.rglob(f"{name}.csv"), None)
            if found:
                shutil.move(str(found), target / f"{name}.csv")


def _download_from_mirror(target: Path) -> None:
    """Download each CSV individually from the public mirror."""
    for name in REQUIRED_FILES:
        destination = target / f"{name}.csv"
        url = f"{MIRROR_BASE}/{name}.csv"
        logger.info("  fetching %s", name)
        with urllib.request.urlopen(url, timeout=180) as response:
            destination.write_bytes(response.read())


def _verify(target: Path) -> None:
    """Check row counts against the published dataset."""
    logger.info("Verifying downloaded files")
    problems: list[str] = []
    for name, expected in EXPECTED_ROWS.items():
        path = target / f"{name}.csv"
        if not path.exists():
            problems.append(f"{name}: missing")
            continue
        rows = len(pd.read_csv(path))
        allowed = expected if isinstance(expected, tuple) else (expected,)
        status = "ok" if rows in allowed else "UNEXPECTED"
        if rows not in allowed:
            problems.append(f"{name}: {rows:,} rows, expected {allowed}")
        logger.info("  %-40s %8s rows  %s", name, f"{rows:,}", status)

    if problems:
        raise ValueError(
            "Downloaded data does not match the published dataset:\n  "
            + "\n  ".join(problems)
        )
    logger.info("All files match the published row counts.")
