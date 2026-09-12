"""Tests for the Olist analytics modules.

Tests structural properties, reconciliation properties (e.g. monthly revenue sums
to total revenue, category revenue reconciles, cohort matrix bounds), and function
contracts across the Python analytics layer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from marketlens.analytics import (
    cohorts,
    customers as customer_analytics,
    delivery,
    products,
    revenue as revenue_analytics,
)


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------


def test_monthly_revenue_reconciles_to_total(tiny_dataset, expected):
    monthly = revenue_analytics.monthly_revenue(tiny_dataset)
    assert monthly["product_revenue"].sum() == pytest.approx(expected["gross_revenue"])
    assert monthly["orders"].sum() == expected["revenue_orders"]


def test_monthly_revenue_excludes_cancelled_orders(tiny_dataset):
    """O3 is cancelled on 2017-03-15 and must not count in March order totals."""
    monthly = revenue_analytics.monthly_revenue(tiny_dataset).set_index("order_month")
    march = monthly.loc[pd.Timestamp("2017-03-01")]
    assert march["orders"] == 1
    assert march["product_revenue"] == pytest.approx(200.0)


def test_growth_columns_are_derived_correctly(tiny_dataset):
    monthly = revenue_analytics.monthly_revenue(tiny_dataset)
    growth = revenue_analytics.revenue_growth(monthly)
    assert pd.isna(growth["mom_revenue_growth"].iloc[0])
    assert growth["running_revenue"].iloc[-1] == pytest.approx(
        growth["product_revenue"].sum()
    )
    assert growth["running_revenue"].is_monotonic_increasing


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


def test_category_revenue_reconciles_to_total(full_dataset):
    performance = products.category_performance(full_dataset)
    total = full_dataset.revenue_lines["price"].sum()
    assert performance["product_revenue"].sum() == pytest.approx(total, abs=0.5)
    assert performance["pct_of_revenue"].sum() == pytest.approx(1.0, abs=0.01)


def test_category_performance_is_sorted_by_revenue(full_dataset):
    performance = products.category_performance(full_dataset)
    assert performance["product_revenue"].is_monotonic_decreasing


def test_top_products_returns_at_most_n(full_dataset):
    top = products.top_products(full_dataset, limit=10)
    assert len(top) <= 10


def test_seller_performance_returns_valid_metrics(full_dataset):
    sellers = products.seller_performance(full_dataset)
    assert "product_revenue" in sellers.columns
    assert "orders" in sellers.columns
    assert (sellers["product_revenue"] >= 0).all()


# ---------------------------------------------------------------------------
# Customers & RFM
# ---------------------------------------------------------------------------


def test_rfm_scores_are_within_range(full_dataset):
    rfm = customer_analytics.rfm_segments(full_dataset)
    for column in ("r_score", "f_score", "m_score"):
        assert rfm[column].between(1, 5).all()
    assert rfm["segment"].notna().all()


def test_every_customer_lands_in_exactly_one_segment(full_dataset):
    rfm = customer_analytics.rfm_segments(full_dataset)
    profile = customer_analytics.segment_profile(rfm)
    assert profile["customers"].sum() == len(rfm)
    assert profile["pct_of_customers"].sum() == pytest.approx(1.0)
    assert profile["pct_of_revenue"].sum() == pytest.approx(1.0)


def test_revenue_concentration_is_monotonic(full_dataset):
    concentration = customer_analytics.revenue_concentration(full_dataset)
    assert concentration["cumulative_pct_of_revenue"].is_monotonic_increasing


# ---------------------------------------------------------------------------
# Cohorts
# ---------------------------------------------------------------------------


def test_cohort_matrix_starts_at_one_hundred_percent(full_dataset):
    matrix = cohorts.cohort_retention_matrix(full_dataset)
    assert (matrix[0] == 100).all()


def test_cohort_retention_never_exceeds_one_hundred(full_dataset):
    matrix = cohorts.cohort_retention_matrix(full_dataset)
    values = matrix.to_numpy(dtype=float)
    assert np.nanmax(values) <= 100.0 + 1e-9


# ---------------------------------------------------------------------------
# Delivery & Freight
# ---------------------------------------------------------------------------


def test_delivery_overview_metrics(tiny_dataset, expected):
    overview = delivery.delivery_overview(tiny_dataset)
    assert overview["delivered_orders"] == expected["completed_orders"]
    assert overview["late_rate"] == pytest.approx(expected["late_delivery_rate"])


def test_severe_delay_falls_further_than_the_headline_gap(full_dataset):
    """A serious delay hurts more than the on-time/late split suggests.

    This is the project's headline operational finding, so it gets an explicit
    guard rather than being left to the insight generator.
    """
    severe = delivery.severe_delay_impact(full_dataset)

    assert severe["on_time_score"] > severe["any_late_score"] > severe["severe_score"]
    assert severe["drop_severe"] > severe["drop_any_late"]
    assert severe["severe_orders"] < severe["any_late_orders"]
    # Scores are on a 1-5 scale, so no gap can exceed 4 points.
    assert 0 < severe["drop_severe"] < 4


def test_one_star_attribution_reports_both_directions(full_dataset):
    """The two readings of "delays cause one-star reviews" are different numbers.

    Of late orders, the share rated one star; and of one-star orders, the share
    that shipped slowly. Conflating them is the easiest way to overstate this
    finding, so both are computed and both are bounded.
    """
    attribution = delivery.one_star_attribution(full_dataset)

    for key in ("one_star_share_of_late", "late_share_of_one_star",
                "slow_share_of_one_star"):
        assert 0 <= attribution[key] <= 1, key
    # A one-star order is far more likely to have been slow than to have
    # formally missed the padded promise.
    assert attribution["slow_share_of_one_star"] > attribution["late_share_of_one_star"]
    assert (attribution["avg_delivery_days_one_star"]
            > attribution["avg_delivery_days_overall"])


# ---------------------------------------------------------------------------
# Regional logistics
# ---------------------------------------------------------------------------


def test_regional_revenue_reconciles(full_dataset):
    regions = delivery.regional_performance(full_dataset)
    total = full_dataset.revenue_lines["price"].sum()
    assert regions["product_revenue"].sum() == pytest.approx(total, abs=0.5)
    assert regions["pct_of_revenue"].sum() == pytest.approx(1.0, abs=0.01)


def test_seller_region_share_sums_to_one(full_dataset):
    sellers = delivery.seller_region_share(full_dataset)
    assert sellers["pct_of_revenue"].sum() == pytest.approx(1.0, abs=0.01)
