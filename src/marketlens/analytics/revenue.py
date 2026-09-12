"""Revenue trend analysis: monthly series, growth rates and seasonality."""

from __future__ import annotations

import pandas as pd

from marketlens.data_processing.datasets import AnalysisData


def monthly_revenue(data: AnalysisData) -> pd.DataFrame:
    """Monthly revenue, orders, customers and AOV.

    Orders and customers are counted on the order-level frame; revenue is
    summed on the line-level frame. Doing both on the line frame would count
    each order once per item in the basket.
    """
    lines = data.revenue_lines
    orders = data.revenue_orders

    revenue = lines.groupby("order_month", as_index=False).agg(
        product_revenue=("price", "sum"),
        freight_revenue=("freight_value", "sum"),
        gmv=("item_total", "sum"),
        units=("order_item_id", "size"),
        sellers=("seller_id", "nunique"),
    )
    counts = orders.groupby("order_month", as_index=False).agg(
        orders=("order_id", "nunique"),
        customers=("customer_unique_id", "nunique"),
    )

    monthly = revenue.merge(counts, on="order_month", how="outer").sort_values("order_month")
    monthly["avg_order_value"] = monthly["product_revenue"] / monthly["orders"]
    monthly["items_per_order"] = monthly["units"] / monthly["orders"]
    monthly["freight_ratio"] = monthly["freight_revenue"] / monthly["gmv"]
    monthly["pct_of_total_revenue"] = (
        monthly["product_revenue"] / monthly["product_revenue"].sum()
    )
    return monthly.reset_index(drop=True)


def revenue_growth(monthly: pd.DataFrame) -> pd.DataFrame:
    """Add month-over-month, year-over-year and cumulative measures.

    ``shift(12)`` gives the same month a year earlier. That comparison only
    becomes available part-way through this dataset, since it covers 20 months,
    but where it exists it is the fairer one - Brazilian retail has a November
    peak (Black Friday) that makes a month-on-month read misleading.
    """
    frame = monthly.sort_values("order_month").copy()

    frame["prev_month_revenue"] = frame["product_revenue"].shift(1)
    frame["mom_revenue_growth"] = frame["product_revenue"].pct_change()
    frame["mom_order_growth"] = frame["orders"].pct_change()
    frame["yoy_revenue_growth"] = frame["product_revenue"].pct_change(periods=12)
    frame["running_revenue"] = frame["product_revenue"].cumsum()
    frame["revenue_3m_avg"] = frame["product_revenue"].rolling(3, min_periods=1).mean()
    frame["aov_3m_avg"] = frame["avg_order_value"].rolling(3, min_periods=1).mean()
    return frame.reset_index(drop=True)
def _divide(numerator, denominator) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0
