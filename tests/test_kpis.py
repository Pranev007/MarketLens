"""Tests for headline KPI calculations against hand-computed expected values.

The fixture ``tiny_dataset`` contains four orders whose KPIs were calculated on
paper before the test was written. Asserting against hand-computed values ensures
a broken formula fails against arithmetic rather than against a previous run of
the same code.
"""

from __future__ import annotations

import pytest

from marketlens.analytics.kpis import calculate_headline_kpis, kpi_table
from marketlens.data_processing.datasets import AnalysisData


def test_order_counts_match_fixture(tiny_dataset, expected):
    kpis = calculate_headline_kpis(tiny_dataset)
    assert kpis.total_orders == expected["total_orders"]
    assert kpis.delivered_orders == expected["completed_orders"]
    assert kpis.cancelled_orders == expected["cancelled_orders"]
    assert kpis.cancellation_rate == pytest.approx(expected["cancellation_rate"])


def test_revenue_and_freight_match_fixture(tiny_dataset, expected):
    kpis = calculate_headline_kpis(tiny_dataset)
    assert kpis.product_revenue == pytest.approx(expected["gross_revenue"])
    assert kpis.freight_revenue == pytest.approx(expected["total_freight"])
    assert kpis.gmv == pytest.approx(expected["gross_revenue"] + expected["total_freight"])


def test_customer_metrics_match_fixture(tiny_dataset, expected):
    kpis = calculate_headline_kpis(tiny_dataset)
    assert kpis.unique_customers == expected["unique_customers"]
    assert kpis.revenue_per_customer == pytest.approx(expected["revenue_per_customer"])
    assert kpis.repeat_purchase_rate == pytest.approx(expected["repeat_purchase_rate"])


def test_delivery_and_reviews_match_fixture(tiny_dataset, expected):
    kpis = calculate_headline_kpis(tiny_dataset)
    assert kpis.late_delivery_rate == pytest.approx(expected["late_delivery_rate"])
    assert kpis.negative_review_rate == pytest.approx(expected["negative_review_rate"])


def test_zero_denominators_do_not_raise(tiny_tables):
    """An empty selection should produce zeros, not a ZeroDivisionError."""
    empty = {name: frame.iloc[0:0] for name, frame in tiny_tables.items()}
    kpis = calculate_headline_kpis(AnalysisData(empty, apply_window=False))
    assert kpis.total_orders == 0
    assert kpis.cancellation_rate == 0.0
    assert kpis.avg_order_value == 0.0
    assert kpis.late_delivery_rate == 0.0


def test_kpi_table_renders_every_metric(tiny_dataset):
    kpis = calculate_headline_kpis(tiny_dataset)
    table = kpi_table(kpis)
    assert len(table) >= 20
    assert "KPI" in table.columns
    assert "Value" in table.columns
