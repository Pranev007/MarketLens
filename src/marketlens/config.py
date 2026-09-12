"""Central configuration for MarketLens.

Everything that could reasonably differ between machines is driven by
environment variables (loaded from a local ``.env`` when present), so the same
code runs unchanged on a laptop with PostgreSQL installed and on one that only
has the processed files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Repository root = three levels above this file (src/marketlens/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

RAW_DIR = PROJECT_ROOT / "data" / "raw"
OLIST_DIR = RAW_DIR / "olist"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
SQL_DIR = PROJECT_ROOT / "sql"
DOCS_DIR = PROJECT_ROOT / "docs"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_date(name: str, default: str) -> date:
    return date.fromisoformat(os.getenv(name) or default)


@dataclass(frozen=True)
class DatabaseConfig:
    """PostgreSQL connection settings."""

    host: str = field(default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"))
    port: int = field(default_factory=lambda: _env_int("POSTGRES_PORT", 5432))
    database: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "marketlens"))
    user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "postgres"))

    @property
    def url(self) -> str:
        """SQLAlchemy URL, honouring an explicit DATABASE_URL override."""
        explicit = os.getenv("DATABASE_URL")
        if explicit:
            return explicit
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def admin_url(self) -> str:
        """URL for the maintenance database, used to CREATE DATABASE."""
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/postgres"
        )


DATABASE = DatabaseConfig()

#: Where the analytics layer reads from: parquet | postgres | auto
DATA_SOURCE = os.getenv("MARKETLENS_SOURCE", "auto").strip().lower()


# ---------------------------------------------------------------------------
# Reporting window
# ---------------------------------------------------------------------------
# Olist spans September 2016 to October 2018, but the tails are not real
# trading months: September 2016 has 4 orders, December 2016 has 1, and
# October 2018 has 4. Charting those alongside months of 7,000 orders produces
# growth rates in the thousands of percent and makes every trend unreadable.
#
# The reporting window is therefore the contiguous run of complete months -
# January 2017 to August 2018, 20 months holding 99.65% of all orders. Rows
# outside it are still loaded into the database; the analysis layer filters
# them and says so, rather than pretending they do not exist.

ANALYSIS_START: date = _env_date("ANALYSIS_START", "2017-01-01")
ANALYSIS_END: date = _env_date("ANALYSIS_END", "2018-08-31")

#: Set MARKETLENS_FULL_WINDOW=1 to analyse every row including the sparse tails.
USE_FULL_WINDOW: bool = os.getenv("MARKETLENS_FULL_WINDOW", "").strip() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Order status semantics
# ---------------------------------------------------------------------------
# Olist ships eight statuses. Two of them mean the order never became revenue:
#   canceled    - cancelled by the customer or the seller
#   unavailable - the seller could not fulfil it
# The rest are all points along a fulfilment pipeline that ends in delivery.

CANCELLED_STATUS = "canceled"
UNAVAILABLE_STATUS = "unavailable"
COMPLETED_STATUS = "delivered"

#: Statuses that never produce revenue.
NON_REVENUE_STATUSES: tuple[str, ...] = (CANCELLED_STATUS, UNAVAILABLE_STATUS)

#: Statuses that do count towards revenue.
REVENUE_STATUSES: tuple[str, ...] = (
    "delivered", "shipped", "invoiced", "processing", "approved", "created",
)

ALL_STATUSES: tuple[str, ...] = REVENUE_STATUSES + NON_REVENUE_STATUSES

#: A delivery is late when it arrives after the date the customer was promised.
#: Olist gives that promise explicitly in order_estimated_delivery_date.
LATE_DELIVERY_THRESHOLD_DAYS = 0

#: Review scores at or below this are treated as a dissatisfied customer.
NEGATIVE_REVIEW_SCORE = 2


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
#: Olist is a Brazilian marketplace and every amount is in Brazilian reais.
CURRENCY = "BRL"
CURRENCY_SYMBOL = "R$"


def ensure_directories() -> None:
    """Create the output directories the pipeline writes into."""
    for path in (RAW_DIR, OLIST_DIR, PROCESSED_DIR, REPORTS_DIR, FIGURES_DIR):
        path.mkdir(parents=True, exist_ok=True)
