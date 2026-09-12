"""Product, category and seller analysis.

Olist carries no cost price, so nothing here reports margin. What it does carry
instead is the customer's verdict - the review score - and the freight cost of
moving the item. Those are the two lenses used to separate a category that
sells well from one that performs well.
"""

from __future__ import annotations

import pandas as pd

from marketlens.config import NEGATIVE_REVIEW_SCORE
from marketlens.data_processing.datasets import AnalysisData


def category_performance(data: AnalysisData, level: str = "category_group") -> pd.DataFrame:
    """Revenue, freight burden, delivery and satisfaction for each category.

    ``level`` is ``category_group`` (8 business groupings) or ``category_en``
    (73 leaf categories). The groupings exist because a chart with 73 bars
    communicates nothing; the leaf level stays available for drill-down.
    """
    lines = data.revenue_lines
    delivered = data.delivered_lines

    performance = lines.groupby(level, as_index=False).agg(
        orders=("order_id", "nunique"),
        customers=("customer_unique_id", "nunique"),
        products_sold=("product_id", "nunique"),
        sellers=("seller_id", "nunique"),
        units=("order_item_id", "size"),
        product_revenue=("price", "sum"),
        freight_revenue=("freight_value", "sum"),
        gmv=("item_total", "sum"),
        avg_item_price=("price", "mean"),
        avg_weight_g=("product_weight_g", "mean"),
    )

    quality = delivered.groupby(level, as_index=False).agg(
        delivered_units=("order_item_id", "size"),
        avg_review_score=("review_score", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
    )
    late = (
        delivered[delivered["is_late"].notna()]
        .groupby(level, as_index=False)
        .agg(late_rate=("is_late", "mean"), rated_units=("is_late", "size"))
    )
    negative = (
        delivered[delivered["review_score"].notna()]
        .assign(negative=lambda d: d["review_score"] <= NEGATIVE_REVIEW_SCORE)
        .groupby(level, as_index=False)
        .agg(negative_review_rate=("negative", "mean"))
    )

    performance = (
        performance.merge(quality, on=level, how="left")
        .merge(late, on=level, how="left")
        .merge(negative, on=level, how="left")
    )

    performance["freight_ratio"] = performance["freight_revenue"] / performance["gmv"]
    performance["pct_of_revenue"] = (
        performance["product_revenue"] / performance["product_revenue"].sum()
    )
    performance = performance.sort_values("product_revenue", ascending=False).reset_index(
        drop=True
    )
    performance["cumulative_pct"] = performance["pct_of_revenue"].cumsum()
    return performance


def category_quality_matrix(data: AnalysisData) -> pd.DataFrame:
    """Rank categories on revenue and on customer satisfaction, and compare.

    With no margin available, the equivalent of "big on revenue but weak on
    profit" is "big on revenue but weak on the customer's verdict". A category
    ranking materially worse on review score than on revenue is one where
    growth is being bought at the cost of experience.
    """
    performance = category_performance(data)
    frame = performance[[
        "category_group", "product_revenue", "pct_of_revenue", "avg_review_score",
        "negative_review_rate", "late_rate", "freight_ratio", "avg_delivery_days",
    ]].copy()

    frame["revenue_rank"] = frame["product_revenue"].rank(ascending=False, method="min").astype(int)
    frame["satisfaction_rank"] = (
        frame["avg_review_score"].rank(ascending=False, method="min").astype(int)
    )
    frame["rank_gap"] = frame["satisfaction_rank"] - frame["revenue_rank"]
    return frame.sort_values("product_revenue", ascending=False).reset_index(drop=True)


def top_products(data: AnalysisData, limit: int = 20) -> pd.DataFrame:
    """Highest-revenue products, with the satisfaction behind them."""
    lines = data.revenue_lines
    delivered = data.delivered_lines

    products = lines.groupby(
        ["product_id", "category_en", "category_group"], as_index=False
    ).agg(
        units_sold=("order_item_id", "size"),
        orders=("order_id", "nunique"),
        sellers=("seller_id", "nunique"),
        product_revenue=("price", "sum"),
        freight_revenue=("freight_value", "sum"),
        avg_price=("price", "mean"),
    )

    quality = delivered.groupby("product_id", as_index=False).agg(
        avg_review_score=("review_score", "mean"),
        delivered_units=("order_item_id", "size"),
    )
    products = products.merge(quality, on="product_id", how="left")
    products["freight_ratio"] = products["freight_revenue"] / (
        products["product_revenue"] + products["freight_revenue"]
    )
    return (
        products.sort_values("product_revenue", ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )
def seller_performance(data: AnalysisData, min_orders: int = 50) -> pd.DataFrame:
    """Seller-level revenue, delivery reliability and satisfaction.

    This is the marketplace lens the synthetic version could not have: Olist
    does not own the inventory, so seller quality is the operational lever.
    ``min_orders`` keeps sellers with too little volume out of the ranking,
    where one late delivery swings the rate by several points.
    """
    lines = data.revenue_lines
    delivered = data.delivered_lines

    sellers = lines.groupby(["seller_id", "seller_state", "seller_region"],
                            as_index=False).agg(
        orders=("order_id", "nunique"),
        units=("order_item_id", "size"),
        products=("product_id", "nunique"),
        product_revenue=("price", "sum"),
        freight_revenue=("freight_value", "sum"),
        avg_item_price=("price", "mean"),
    )
    sellers = sellers[sellers["orders"] >= min_orders]

    quality = delivered[delivered["is_late"].notna()].groupby("seller_id", as_index=False).agg(
        late_rate=("is_late", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
        avg_review_score=("review_score", "mean"),
    )
    sellers = sellers.merge(quality, on="seller_id", how="left")
    sellers["pct_of_revenue"] = (
        sellers["product_revenue"] / lines["price"].sum()
    )
    return sellers.sort_values("product_revenue", ascending=False).reset_index(drop=True)


def seller_concentration(data: AnalysisData) -> pd.DataFrame:
    """How much of the marketplace's revenue sits with how few sellers."""
    revenue = (
        data.revenue_lines.groupby("seller_id")["price"].sum()
        .sort_values(ascending=False)
        .reset_index(drop=True)
    )
    total = revenue.sum()
    rows = []
    for pct in (1, 5, 10, 20, 50, 100):
        cutoff = max(int(len(revenue) * pct / 100), 1)
        rows.append({
            "top_n_percent": pct,
            "sellers": cutoff,
            "cumulative_revenue": float(revenue.head(cutoff).sum()),
            "cumulative_pct_of_revenue": float(revenue.head(cutoff).sum() / total),
        })
    return pd.DataFrame(rows)


def category_growth(data: AnalysisData) -> pd.DataFrame:
    """Growth by category, comparing equivalent periods.

    2018 stops at the end of August, so a plain calendar-year comparison would
    show every category shrinking. This compares January-August 2018 against
    January-August 2017 instead, which is like for like.
    """
    lines = data.revenue_lines.copy()
    lines["month_number"] = lines["order_purchase_timestamp"].dt.month
    years = sorted(lines["order_year"].unique())
    if len(years) < 2:
        return pd.DataFrame()
    first, last = years[0], years[-1]

    # The months present in the shorter (partial) year.
    common_months = set(lines.loc[lines["order_year"] == last, "month_number"])
    comparable = lines[lines["month_number"].isin(common_months)]

    pivot = (
        comparable.pivot_table(index="category_group", columns="order_year",
                               values="price", aggfunc="sum")
        .fillna(0.0)
        .reset_index()
    )
    if first not in pivot.columns or last not in pivot.columns:
        return pd.DataFrame()

    pivot = pivot.rename(columns={first: "revenue_first_period",
                                  last: "revenue_last_period"})
    pivot["revenue_change"] = pivot["revenue_last_period"] - pivot["revenue_first_period"]
    pivot["growth_rate"] = pivot["revenue_change"] / pivot["revenue_first_period"].replace(0, pd.NA)
    pivot["share_of_total_growth"] = pivot["revenue_change"] / pivot["revenue_change"].sum()
    pivot["pct_of_revenue_last_period"] = (
        pivot["revenue_last_period"] / pivot["revenue_last_period"].sum()
    )
    pivot["months_compared"] = len(common_months)
    return pivot.sort_values("growth_rate", ascending=False).reset_index(drop=True)