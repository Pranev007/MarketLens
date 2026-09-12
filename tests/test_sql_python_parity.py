"""SQL and Python must produce the same numbers.

The dashboard reads through the Pandas layer while the SQL files are what a
reviewer actually opens, so the two have to agree.

These tests execute the real query files against PostgreSQL and compare the
results against the Python analytics. They are skipped when no database is
reachable, so the rest of the suite still runs on a machine without one.
"""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import text

from marketlens.analytics import (
    cohorts,
    customers as customer_analytics,
    delivery,
    products,
    revenue as revenue_analytics,
)
from marketlens.analytics.kpis import calculate_headline_kpis
from marketlens.config import SQL_DIR
from marketlens.data_processing.database import split_query_file

pytestmark = pytest.mark.db

MONEY_TOLERANCE = 0.05
RATE_TOLERANCE = 1e-4


def run_query(engine, filename: str, number: str) -> pd.DataFrame:
    """Execute one labelled query from a query file."""
    blocks = {n: sql for n, _, sql in split_query_file(SQL_DIR / filename)}
    assert number in blocks, f"Query {number} not found in {filename}"
    return pd.read_sql_query(text(blocks[number]), engine)


@pytest.fixture(scope="module")
def sql_kpis(db_engine):
    return run_query(db_engine, "revenue_analysis.sql", "01").iloc[0]


@pytest.fixture(scope="module")
def python_kpis(full_dataset):
    return calculate_headline_kpis(full_dataset)


# ---------------------------------------------------------------------------
# Headline KPIs
# ---------------------------------------------------------------------------


def test_order_counts_match(sql_kpis, python_kpis):
    assert int(sql_kpis["total_orders"]) == python_kpis.total_orders
    assert int(sql_kpis["delivered_orders"]) == python_kpis.delivered_orders
    assert int(sql_kpis["cancelled_orders"]) == python_kpis.cancelled_orders


def test_customer_counts_match(sql_kpis, python_kpis):
    assert int(sql_kpis["unique_customers"]) == python_kpis.unique_customers


def test_revenue_matches(sql_kpis, python_kpis):
    assert float(sql_kpis["product_revenue"]) == pytest.approx(
        python_kpis.product_revenue, abs=MONEY_TOLERANCE
    )
    assert float(sql_kpis["freight_revenue"]) == pytest.approx(
        python_kpis.freight_revenue, abs=MONEY_TOLERANCE
    )
    assert float(sql_kpis["gmv"]) == pytest.approx(
        python_kpis.gmv, abs=MONEY_TOLERANCE
    )


# ---------------------------------------------------------------------------
# Monthly series
# ---------------------------------------------------------------------------


def test_monthly_revenue_matches(db_engine, full_dataset):
    sql = run_query(db_engine, "revenue_analysis.sql", "02")
    python = revenue_analytics.monthly_revenue(full_dataset)

    assert len(sql) == len(python)
    sql = sql.assign(month=pd.to_datetime(sql["month"])).set_index("month")
    python = python.set_index("order_month")
    assert list(sql.index) == list(python.index)

    for month in sql.index:
        assert float(sql.loc[month, "product_revenue"]) == pytest.approx(
            float(python.loc[month, "product_revenue"]), abs=MONEY_TOLERANCE
        ), month
        assert int(sql.loc[month, "orders"]) == int(python.loc[month, "orders"]), month


# ---------------------------------------------------------------------------
# First-delivery experience
#
# This cut went unguarded for a while and drifted three separate ways: an
# unstable DISTINCT ON in SQL, a pandas groupby "first" that skipped nulls and
# stitched together a first order that never existed, and a 90-day window
# measured in floored days on one side and timestamps on the other. All three
# were invisible in the headline KPIs, so they need their own test.
# ---------------------------------------------------------------------------


def test_first_delivery_experience_matches(db_engine, full_dataset):
    sql = run_query(db_engine, "retention_analysis.sql", "11").set_index("first_experience")
    python = cohorts.retention_by_first_experience(full_dataset).set_index("first_experience")

    for experience in ("First delivery on time", "First delivery late"):
        assert experience in python.index, experience
        sql_row, py_row = sql.loc[experience], python.loc[experience]

        assert int(sql_row["customers"]) == int(py_row["customers"]), experience
        assert int(sql_row["returned"]) == round(
            float(py_row["repeat_rate"]) * int(py_row["customers"])
        ), experience
        assert float(sql_row["repeat_90d_pct"]) == pytest.approx(
            100.0 * float(py_row["repeat_rate"]), abs=1e-3
        ), experience
        assert float(sql_row["avg_first_review"]) == pytest.approx(
            float(py_row["avg_first_review"]), abs=1e-3
        ), experience


def test_first_order_selection_is_deterministic(db_engine):
    """Q20 must return the same rows twice - it did not before the tie-break."""
    first = run_query(db_engine, "retention_analysis.sql", "11")
    second = run_query(db_engine, "retention_analysis.sql", "11")
    pd.testing.assert_frame_equal(first, second)


def test_severe_delay_impact_matches(db_engine, full_dataset):
    """The delivery finding, checked in both implementations.

    This is the number quoted outside the repo, so it is worth more than an
    insight generator's word: SQL computes it with FILTER aggregates, Pandas
    computes it with boolean masks, and the two have to land on the same place.
    """
    sql = run_query(db_engine, "delivery_reviews_analysis.sql", "24").iloc[0]
    python = delivery.severe_delay_impact(full_dataset)
    attribution = delivery.one_star_attribution(full_dataset)

    assert int(sql["on_time_orders"]) == python["on_time_orders"]
    assert int(sql["late_orders"]) == python["any_late_orders"]
    assert int(sql["over_a_week_late"]) == python["severe_orders"]

    assert float(sql["on_time_score"]) == pytest.approx(python["on_time_score"], abs=1e-3)
    assert float(sql["late_score"]) == pytest.approx(python["any_late_score"], abs=1e-3)
    assert float(sql["over_a_week_score"]) == pytest.approx(
        python["severe_score"], abs=1e-3
    )
    assert float(sql["drop_when_over_a_week"]) == pytest.approx(
        python["drop_severe"], abs=0.01
    )

    assert float(sql["pct_of_late_rated_one_star"]) == pytest.approx(
        100 * attribution["one_star_share_of_late"], abs=0.1
    )
    assert float(sql["pct_of_one_star_that_was_late"]) == pytest.approx(
        100 * attribution["late_share_of_one_star"], abs=0.1
    )
    assert float(sql["pct_of_one_star_slower_than_median"]) == pytest.approx(
        100 * attribution["slow_share_of_one_star"], abs=0.1
    )

# ---------------------------------------------------------------------------
# Query file execution sanity test
# ---------------------------------------------------------------------------


QUERY_FILES = (
    "revenue_analysis.sql",
    "product_analysis.sql",
    "customer_analysis.sql",
    "retention_analysis.sql",
    "delivery_reviews_analysis.sql",
)


@pytest.mark.parametrize("filename", QUERY_FILES)
def test_every_query_executes(db_engine, filename):
    """A regression guard: every labelled query must run and return rows."""
    blocks = split_query_file(SQL_DIR / filename)
    assert blocks, f"No labelled queries found in {filename}"
    for number, title, sql in blocks:
        frame = pd.read_sql_query(text(sql), db_engine)
        assert len(frame) > 0, f"Q{number} ({title}) in {filename} returned no rows"


def test_repository_has_at_least_twenty_queries():
    total = sum(len(split_query_file(SQL_DIR / name)) for name in QUERY_FILES)
    assert total >= 20, f"Only {total} analysis queries found"
