"""Tests for the dashboard's data layer and view renderers.

Tests the filter model, filtering behaviour on the Olist dataset, and verifies
that all 6 Streamlit view pages are importable and callable.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.data_access import Filters, apply_filters  # noqa: E402
from marketlens.analytics.kpis import calculate_headline_kpis  # noqa: E402


@pytest.fixture(scope="module")
def full_range(full_dataset) -> tuple[date, date]:
    return (
        full_dataset.orders["order_purchase_timestamp"].min().date(),
        full_dataset.orders["order_purchase_timestamp"].max().date(),
    )


# ---------------------------------------------------------------------------
# The filter model
# ---------------------------------------------------------------------------


def test_filters_are_hashable(full_range):
    """They are used as a Streamlit cache key, so they must hash."""
    start, end = full_range
    filters = Filters(start_date=start, end_date=end, category_groups=("Health & Beauty",))
    assert hash(filters) == hash(
        Filters(start_date=start, end_date=end, category_groups=("Health & Beauty",))
    )
    assert hash(filters) != hash(Filters(start_date=start, end_date=end))


def test_is_active_reflects_non_date_filters(full_range):
    start, end = full_range
    assert not Filters(start_date=start, end_date=end).is_active
    assert Filters(start_date=start, end_date=end, regions=("Southeast",)).is_active


# ---------------------------------------------------------------------------
# Filtering behaviour
# ---------------------------------------------------------------------------


def test_no_filters_returns_the_whole_dataset(full_dataset, full_range):
    start, end = full_range
    filtered = apply_filters(Filters(start_date=start, end_date=end))
    assert len(filtered.lines) == len(full_dataset.lines)

    unfiltered_kpis = calculate_headline_kpis(full_dataset)
    filtered_kpis = calculate_headline_kpis(filtered)
    assert filtered_kpis.product_revenue == pytest.approx(unfiltered_kpis.product_revenue)
    assert filtered_kpis.delivered_orders == unfiltered_kpis.delivered_orders

    # Order counts, not just revenue. The filters select on order LINES, and
    # 739 orders in the window carry no line items - among them all 602
    # 'unavailable' ones. Selecting on lines alone dropped every one of them,
    # so the dashboard showed 98,353 orders and zero unavailable against the
    # report's 99,092 and 602, with revenue identical either way. Asserting
    # only on revenue is what let that through.
    assert filtered_kpis.total_orders == unfiltered_kpis.total_orders
    assert filtered_kpis.cancelled_orders == unfiltered_kpis.cancelled_orders
    assert filtered_kpis.unavailable_orders == unfiltered_kpis.unavailable_orders
    assert filtered_kpis.unique_customers == unfiltered_kpis.unique_customers


def test_category_filter_narrows_to_that_category(full_dataset, full_range):
    start, end = full_range
    filtered = apply_filters(
        Filters(start_date=start, end_date=end, category_groups=("Health & Beauty",))
    )
    assert set(filtered.lines["category_group"]) == {"Health & Beauty"}

    expected = full_dataset.lines[
        (full_dataset.lines["category_group"] == "Health & Beauty") & full_dataset.lines["is_revenue"]
    ]["price"].sum()
    assert calculate_headline_kpis(filtered).product_revenue == pytest.approx(expected)
    assert len(filtered.lines) < len(full_dataset.lines)


def test_region_filter_narrows_to_that_region(full_dataset, full_range):
    start, end = full_range
    filtered = apply_filters(
        Filters(start_date=start, end_date=end, regions=("Southeast",))
    )
    assert set(filtered.lines["customer_region"]) == {"Southeast"}
    assert set(filtered.customers["customer_region"]) == {"Southeast"}


def test_date_filter_narrows_the_window(full_dataset, full_range):
    start, _ = full_range
    cutoff = date(2017, 6, 30)
    filtered = apply_filters(Filters(start_date=start, end_date=cutoff))
    assert filtered.lines["order_purchase_timestamp"].max().date() <= cutoff
    assert filtered.lines["order_purchase_timestamp"].min().date() >= start


def test_impossible_filter_yields_an_empty_but_usable_dataset(full_dataset, full_range):
    """The pages check for this and show a warning; it must not raise."""
    start, end = full_range
    filtered = apply_filters(
        Filters(start_date=start, end_date=end,
                category_groups=("Health & Beauty",), states=("AC",))
    )
    assert filtered.lines.empty or len(filtered.lines) < len(full_dataset.lines)
    kpis = calculate_headline_kpis(filtered)
    assert kpis.total_orders >= 0


def test_every_dashboard_page_is_importable():
    """A broken import would only surface when a user clicked that page."""
    from dashboard.app import PAGES

    assert len(PAGES) == 5
    for name, render in PAGES.items():
        assert callable(render), name


def test_every_dashboard_page_renders(full_dataset, full_range):
    """Actually call each page.

    Importing a view proves nothing about whether it works: the Geography page
    asked ``regional_performance`` for an ``avg_item_price`` column that the
    function never returned, and the only symptom was a KeyError traceback
    where the table should have been. Streamlit runs bare here - the calls are
    no-ops outside a script run - which is enough to exercise every frame the
    view indexes into.
    """
    from dashboard.app import PAGES
    from dashboard.data_access import DashboardData

    start, end = full_range
    dashboard = DashboardData(
        data=full_dataset, full=full_dataset,
        filters=Filters(start_date=start, end_date=end),
    )
    for name, render in PAGES.items():
        try:
            render(dashboard)
        except Exception as error:  # noqa: BLE001 - the failure IS the result
            pytest.fail(f"{name} failed to render: {type(error).__name__}: {error}")
