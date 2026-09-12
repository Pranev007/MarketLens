"""Headline KPI calculations.

Every definition here matches ``sql/revenue_analysis.sql`` query 01 exactly.
The parity between the two is asserted in ``tests/test_sql_python_parity.py``,
which is the point: a dashboard number and a SQL number that disagree is worse
than having neither.

Definitions, stated once:

    product revenue    = SUM(price) over orders that are not cancelled or
                         unavailable
    freight revenue    = SUM(freight_value) over the same orders
    GMV                = product revenue + freight revenue
    AOV                = product revenue / distinct revenue-bearing orders
    units              = COUNT of order_items rows (there is no quantity column)
    unique customers   = COUNT(DISTINCT customer_unique_id), never customer_id
    repeat rate        = customers with 2+ orders / customers with 1+ order
    late delivery rate = delivered orders arriving after the promised date /
                         delivered orders that have a delivery date

There is no cost data anywhere in Olist, so gross margin is not reported. The
freight ratio is used instead: it is the one cost the dataset does expose.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from marketlens.config import CANCELLED_STATUS, NEGATIVE_REVIEW_SCORE, UNAVAILABLE_STATUS
from marketlens.data_processing.datasets import AnalysisData


@dataclass(frozen=True)
class HeadlineKPIs:
    """The numbers that belong at the top of an executive summary."""

    total_orders: int
    delivered_orders: int
    cancelled_orders: int
    unavailable_orders: int
    cancellation_rate: float
    unfulfilled_rate: float

    unique_customers: int
    customer_accounts: int
    repeat_purchase_rate: float
    revenue_per_customer: float

    product_revenue: float
    freight_revenue: float
    gmv: float
    freight_ratio: float
    avg_order_value: float
    avg_items_per_order: float
    avg_item_price: float

    active_sellers: int
    products_sold: int

    on_time_delivery_rate: float
    late_delivery_rate: float
    avg_delivery_days: float
    median_delivery_days: float
    delivery_date_coverage: float

    avg_review_score: float
    negative_review_rate: float
    review_coverage: float

    period_start: pd.Timestamp
    period_end: pd.Timestamp

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_headline_kpis(data: AnalysisData) -> HeadlineKPIs:
    """Compute every headline KPI in one pass over the fact table."""
    orders = data.order_summary
    revenue_orders = data.revenue_orders
    revenue_lines = data.revenue_lines
    delivered = data.delivered_orders  # delivered AND has a delivery date

    total_orders = len(orders)
    cancelled = int((orders["order_status"] == CANCELLED_STATUS).sum())
    unavailable = int((orders["order_status"] == UNAVAILABLE_STATUS).sum())
    delivered_count = int(orders["is_delivered"].sum())

    product_revenue = float(revenue_lines["price"].sum())
    freight_revenue = float(revenue_lines["freight_value"].sum())
    gmv = product_revenue + freight_revenue

    orders_per_customer = revenue_orders.groupby("customer_unique_id").size()
    unique_customers = int(revenue_orders["customer_unique_id"].nunique())

    all_delivered = orders[orders["is_delivered"]]
    reviewed = revenue_orders[revenue_orders["review_score"].notna()]

    return HeadlineKPIs(
        total_orders=total_orders,
        delivered_orders=delivered_count,
        cancelled_orders=cancelled,
        unavailable_orders=unavailable,
        cancellation_rate=_divide(cancelled, total_orders),
        # Cancelled and unavailable both mean the customer never received
        # anything, so they are also reported together.
        unfulfilled_rate=_divide(cancelled + unavailable, total_orders),

        unique_customers=unique_customers,
        customer_accounts=int(revenue_orders["customer_id"].nunique()),
        repeat_purchase_rate=_divide(int((orders_per_customer >= 2).sum()),
                                     len(orders_per_customer)),
        revenue_per_customer=_divide(product_revenue, unique_customers),

        product_revenue=product_revenue,
        freight_revenue=freight_revenue,
        gmv=gmv,
        freight_ratio=_divide(freight_revenue, gmv),
        avg_order_value=_divide(product_revenue, len(revenue_orders)),
        avg_items_per_order=_divide(len(revenue_lines), len(revenue_orders)),
        avg_item_price=_divide(product_revenue, len(revenue_lines)),

        active_sellers=int(revenue_lines["seller_id"].nunique()),
        products_sold=int(revenue_lines["product_id"].nunique()),

        on_time_delivery_rate=_divide(int((~delivered["is_late"].astype(bool)).sum()),
                                      len(delivered)),
        late_delivery_rate=_divide(int(delivered["is_late"].astype(bool).sum()),
                                   len(delivered)),
        avg_delivery_days=float(delivered["delivery_days"].mean()) if len(delivered) else 0.0,
        median_delivery_days=float(delivered["delivery_days"].median()) if len(delivered) else 0.0,
        # A handful of delivered orders carry no delivery date. The measures
        # above are computed on the rest; this reports how much that covers.
        delivery_date_coverage=_divide(len(delivered), len(all_delivered)),

        avg_review_score=float(reviewed["review_score"].mean()) if len(reviewed) else 0.0,
        negative_review_rate=_divide(
            int((reviewed["review_score"] <= NEGATIVE_REVIEW_SCORE).sum()), len(reviewed)
        ),
        review_coverage=_divide(len(reviewed), len(revenue_orders)),

        period_start=revenue_orders["order_purchase_timestamp"].min(),
        period_end=revenue_orders["order_purchase_timestamp"].max(),
    )


def kpi_table(kpis: HeadlineKPIs) -> pd.DataFrame:
    """Render the KPIs as a labelled two-column table for reports."""
    rows = [
        ("Reporting period", f"{kpis.period_start:%d %b %Y} to {kpis.period_end:%d %b %Y}"),
        ("Total orders", f"{kpis.total_orders:,}"),
        ("Delivered orders", f"{kpis.delivered_orders:,}"),
        ("Cancelled orders", f"{kpis.cancelled_orders:,}"),
        ("Unavailable orders", f"{kpis.unavailable_orders:,}"),
        ("Cancellation rate", f"{kpis.cancellation_rate:.2%}"),
        ("Unfulfilled rate (cancelled + unavailable)", f"{kpis.unfulfilled_rate:.2%}"),
        ("Unique customers", f"{kpis.unique_customers:,}"),
        ("Customer accounts (one per order)", f"{kpis.customer_accounts:,}"),
        ("Repeat purchase rate", f"{kpis.repeat_purchase_rate:.2%}"),
        ("Product revenue", f"{kpis.product_revenue:,.2f}"),
        ("Freight revenue", f"{kpis.freight_revenue:,.2f}"),
        ("GMV (product + freight)", f"{kpis.gmv:,.2f}"),
        ("Freight as share of GMV", f"{kpis.freight_ratio:.2%}"),
        ("Average order value", f"{kpis.avg_order_value:,.2f}"),
        ("Average items per order", f"{kpis.avg_items_per_order:.2f}"),
        ("Average item price", f"{kpis.avg_item_price:,.2f}"),
        ("Revenue per customer", f"{kpis.revenue_per_customer:,.2f}"),
        ("Active sellers", f"{kpis.active_sellers:,}"),
        ("Products sold", f"{kpis.products_sold:,}"),
        ("On-time delivery rate", f"{kpis.on_time_delivery_rate:.2%}"),
        ("Late delivery rate", f"{kpis.late_delivery_rate:.2%}"),
        ("Average delivery days", f"{kpis.avg_delivery_days:.1f}"),
        ("Median delivery days", f"{kpis.median_delivery_days:.0f}"),
        ("Delivery date coverage", f"{kpis.delivery_date_coverage:.2%}"),
        ("Average review score", f"{kpis.avg_review_score:.2f} / 5"),
        ("Negative review rate (1-2 stars)", f"{kpis.negative_review_rate:.2%}"),
        ("Review coverage", f"{kpis.review_coverage:.2%}"),
    ]
    return pd.DataFrame(rows, columns=["KPI", "Value"])


def _divide(numerator: float, denominator: float) -> float:
    """Divide, returning 0.0 rather than raising when the denominator is zero."""
    return float(numerator) / float(denominator) if denominator else 0.0
