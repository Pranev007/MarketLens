"""Delivery performance and customer satisfaction.

Olist has no returns table, so this module carries the weight that returns
analysis would in a retail dataset. It is arguably a better signal: instead of
inferring dissatisfaction from a product coming back, the customer states it
directly with a 1-5 review score, and the dataset also records what the
customer was promised at checkout and when the parcel actually arrived.

Definitions used throughout:

    late          = delivered after order_estimated_delivery_date, the date
                    shown to the customer at purchase
    delivery days = calendar days from purchase to delivery
    negative      = review score of 1 or 2

Only delivered orders with an actual delivery date can be assessed. Orders
still in transit, cancelled, or delivered without a recorded date are excluded
from the denominator rather than counted as on time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from marketlens.config import NEGATIVE_REVIEW_SCORE
from marketlens.data_processing.datasets import AnalysisData


def delivery_overview(data: AnalysisData) -> dict[str, float]:
    """Company-wide delivery and satisfaction measures."""
    delivered = data.delivered_orders
    reviewed = delivered[delivered["review_score"].notna()]

    if delivered.empty:
        return {}

    late = delivered["is_late"].astype(bool)
    return {
        "delivered_orders": int(len(delivered)),
        "late_orders": int(late.sum()),
        "late_rate": float(late.mean()),
        "on_time_rate": float((~late).mean()),
        "avg_delivery_days": float(delivered["delivery_days"].mean()),
        "median_delivery_days": float(delivered["delivery_days"].median()),
        "p90_delivery_days": float(delivered["delivery_days"].quantile(0.90)),
        "avg_days_early": float(-delivered["days_vs_estimate"].mean()),
        "avg_review_score": float(reviewed["review_score"].mean()),
        "negative_review_rate": float(
            (reviewed["review_score"] <= NEGATIVE_REVIEW_SCORE).mean()
        ),
        "avg_score_on_time": float(
            reviewed.loc[~reviewed["is_late"].astype(bool), "review_score"].mean()
        ),
        "avg_score_late": float(
            reviewed.loc[reviewed["is_late"].astype(bool), "review_score"].mean()
        ),
    }


def satisfaction_by_delivery(data: AnalysisData) -> pd.DataFrame:
    """Review score against whether the delivery beat its promise.

    The single strongest relationship in the dataset. Reported as a table
    rather than a correlation because the effect is not linear - it is a cliff
    at the promised date.
    """
    delivered = data.delivered_orders
    reviewed = delivered[delivered["review_score"].notna()].copy()
    if reviewed.empty:
        return pd.DataFrame()

    reviewed["delivery_outcome"] = np.where(
        reviewed["is_late"].astype(bool), "Late", "On time or early"
    )
    grouped = reviewed.groupby("delivery_outcome", as_index=False).agg(
        orders=("order_id", "count"),
        avg_review_score=("review_score", "mean"),
        median_review_score=("review_score", "median"),
        avg_delivery_days=("delivery_days", "mean"),
        revenue=("price", "sum"),
    )
    negative = reviewed.assign(
        negative=reviewed["review_score"] <= NEGATIVE_REVIEW_SCORE,
        one_star=reviewed["review_score"] == 1,
        five_star=reviewed["review_score"] == 5,
    ).groupby("delivery_outcome", as_index=False).agg(
        negative_review_rate=("negative", "mean"),
        one_star_rate=("one_star", "mean"),
        five_star_rate=("five_star", "mean"),
    )
    grouped = grouped.merge(negative, on="delivery_outcome", how="left")
    grouped["pct_of_orders"] = grouped["orders"] / grouped["orders"].sum()
    return grouped.sort_values("avg_review_score", ascending=False).reset_index(drop=True)


def satisfaction_by_lateness_band(data: AnalysisData) -> pd.DataFrame:
    """How review score moves with how early or late the parcel was.

    Bands rather than a scatter, because the relationship is a step change at
    the promised date rather than a smooth slope.
    """
    delivered = data.delivered_orders
    reviewed = delivered[delivered["review_score"].notna()].copy()
    if reviewed.empty:
        return pd.DataFrame()

    bins = [-np.inf, -15, -7, -3, 0, 3, 7, 15, np.inf]
    labels = ["15+ days early", "7-14 early", "3-6 early", "0-2 early",
              "1-3 days late", "4-7 late", "8-15 late", "15+ days late"]
    reviewed["lateness_band"] = pd.cut(
        reviewed["days_vs_estimate"], bins=bins, labels=labels, right=True
    )

    banded = reviewed.groupby("lateness_band", as_index=False, observed=True).agg(
        orders=("order_id", "count"),
        avg_review_score=("review_score", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
        revenue=("price", "sum"),
    )
    rates = reviewed.assign(
        one_star=reviewed["review_score"] == 1,
        negative=reviewed["review_score"] <= NEGATIVE_REVIEW_SCORE,
    ).groupby("lateness_band", as_index=False, observed=True).agg(
        one_star_rate=("one_star", "mean"),
        negative_review_rate=("negative", "mean"),
    )
    banded = banded.merge(rates, on="lateness_band", how="left")
    banded["pct_of_orders"] = banded["orders"] / banded["orders"].sum()
    return banded


def delivery_by_dimension(data: AnalysisData, dimension: str = "customer_region",
                          min_orders: int = 100) -> pd.DataFrame:
    """Delivery reliability and satisfaction cut by any dimension."""
    delivered = data.delivered_orders
    if dimension not in delivered.columns:
        lines = data.delivered_lines
        source = lines[lines["days_vs_estimate"].notna()]
        grouped = source.groupby(dimension, as_index=False).agg(
            orders=("order_id", "nunique"),
            late_rate=("is_late", "mean"),
            avg_delivery_days=("delivery_days", "mean"),
            median_delivery_days=("delivery_days", "median"),
            avg_review_score=("review_score", "mean"),
            revenue=("price", "sum"),
            avg_freight=("freight_value", "mean"),
        )
    else:
        grouped = delivered.groupby(dimension, as_index=False).agg(
            orders=("order_id", "count"),
            late_rate=("is_late", "mean"),
            avg_delivery_days=("delivery_days", "mean"),
            median_delivery_days=("delivery_days", "median"),
            avg_review_score=("review_score", "mean"),
            revenue=("price", "sum"),
            avg_freight=("freight_value", "mean"),
        )

    grouped = grouped[grouped["orders"] >= min_orders]
    company_late = float(delivered["is_late"].astype(bool).mean())
    grouped["company_late_rate"] = company_late
    grouped["late_vs_company_pp"] = 100 * (grouped["late_rate"] - company_late)
    return grouped.sort_values("late_rate", ascending=False).reset_index(drop=True)


def monthly_delivery_performance(data: AnalysisData) -> pd.DataFrame:
    """Delivery reliability and satisfaction over time.

    Cohorted on the month the order was PLACED, not the month it arrived,
    so the number reflects the promise made that month.
    """
    delivered = data.delivered_orders
    if delivered.empty:
        return pd.DataFrame()

    monthly = delivered.groupby("order_month", as_index=False).agg(
        delivered_orders=("order_id", "count"),
        late_rate=("is_late", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
        median_delivery_days=("delivery_days", "median"),
        avg_review_score=("review_score", "mean"),
    )
    negative = (
        delivered[delivered["review_score"].notna()]
        .assign(negative=lambda d: d["review_score"] <= NEGATIVE_REVIEW_SCORE)
        .groupby("order_month", as_index=False)
        .agg(negative_review_rate=("negative", "mean"))
    )
    monthly = monthly.merge(negative, on="order_month", how="left")
    monthly["late_rate_change_pp"] = 100 * monthly["late_rate"].diff()
    return monthly


def review_score_distribution(data: AnalysisData) -> pd.DataFrame:
    """How the 1-5 scores are distributed, and the revenue behind each."""
    reviewed = data.revenue_orders[data.revenue_orders["review_score"].notna()]
    if reviewed.empty:
        return pd.DataFrame()

    distribution = reviewed.groupby("review_score", as_index=False).agg(
        orders=("order_id", "count"),
        revenue=("price", "sum"),
        avg_order_value=("price", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
        late_rate=("is_late", "mean"),
    )
    distribution["pct_of_orders"] = distribution["orders"] / distribution["orders"].sum()
    distribution["pct_of_revenue"] = distribution["revenue"] / distribution["revenue"].sum()
    return distribution.sort_values("review_score").reset_index(drop=True)


def problem_sellers(data: AnalysisData, min_orders: int = 50,
                    limit: int = 25) -> pd.DataFrame:
    """Sellers whose delivery reliability is materially worse than the market.

    The marketplace equivalent of a product-level returns problem: Olist does
    not control fulfilment, so a seller with a high late rate is an operational
    lever the platform can actually pull.
    """
    lines = data.delivered_lines
    source = lines[lines["days_vs_estimate"].notna()]

    sellers = source.groupby(["seller_id", "seller_state"], as_index=False).agg(
        orders=("order_id", "nunique"),
        units=("order_item_id", "size"),
        late_rate=("is_late", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
        avg_review_score=("review_score", "mean"),
        revenue=("price", "sum"),
    )
    sellers = sellers[sellers["orders"] >= min_orders]
    if sellers.empty:
        return sellers

    company_late = float(source["is_late"].astype(bool).mean())
    company_score = float(source["review_score"].mean())
    sellers["company_late_rate"] = company_late
    sellers["late_vs_company_multiple"] = sellers["late_rate"] / company_late
    sellers["score_vs_company"] = sellers["avg_review_score"] - company_score

    flagged = sellers[sellers["late_rate"] > company_late * 1.5]
    return flagged.sort_values("revenue", ascending=False).head(limit).reset_index(drop=True)


def estimate_accuracy(data: AnalysisData) -> pd.DataFrame:
    """How well the promised delivery date matches reality, by region.

    Olist's estimates are heavily padded - most orders arrive well before the
    promised date. That is a deliberate choice with a cost: an over-padded
    promise loses customers at checkout who would have bought with a realistic
    one. The gap is quantified here rather than assumed.
    """
    delivered = data.delivered_orders
    if delivered.empty:
        return pd.DataFrame()

    grouped = delivered.groupby("customer_region", as_index=False).agg(
        orders=("order_id", "count"),
        avg_delivery_days=("delivery_days", "mean"),
        median_delivery_days=("delivery_days", "median"),
        avg_days_vs_estimate=("days_vs_estimate", "mean"),
        median_days_vs_estimate=("days_vs_estimate", "median"),
        late_rate=("is_late", "mean"),
        avg_review_score=("review_score", "mean"),
    )
    # Days of padding built into the promise: how much earlier the parcel
    # typically arrives than the date the customer was given.
    grouped["avg_promise_padding_days"] = -grouped["avg_days_vs_estimate"]
    return grouped.sort_values("avg_promise_padding_days", ascending=False).reset_index(
        drop=True
    )


def revenue_at_risk_from_experience(data: AnalysisData) -> pd.DataFrame:
    """Revenue sitting behind poor delivery experiences.

    Sizes the delivery problem in money rather than in percentages, which is
    what a budget conversation needs.
    """
    delivered = data.delivered_orders
    reviewed = delivered[delivered["review_score"].notna()].copy()
    if reviewed.empty:
        return pd.DataFrame()

    reviewed["experience"] = np.select(
        [
            reviewed["is_late"].astype(bool) & (reviewed["review_score"] <= 2),
            reviewed["is_late"].astype(bool),
            reviewed["review_score"] <= 2,
        ],
        ["Late and badly reviewed", "Late but not badly reviewed",
         "On time but badly reviewed"],
        default="On time and acceptably reviewed",
    )
    grouped = reviewed.groupby("experience", as_index=False).agg(
        orders=("order_id", "count"),
        customers=("customer_unique_id", "nunique"),
        revenue=("price", "sum"),
        avg_review_score=("review_score", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
    )
    grouped["pct_of_orders"] = grouped["orders"] / grouped["orders"].sum()
    grouped["pct_of_revenue"] = grouped["revenue"] / grouped["revenue"].sum()
    return grouped.sort_values("revenue", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Severity of delay
# ---------------------------------------------------------------------------
#
# `satisfaction_by_delivery` splits on-time against late and reports a 2.0-point
# gap. That understates what a serious delay does, because "late" is dominated
# by orders that missed the date by a day or two. Splitting out the orders that
# missed it by more than a week gives the real depth of the fall.


SEVERE_DELAY_DAYS = 7


def severe_delay_impact(data: AnalysisData) -> dict[str, float]:
    """Review score for on-time orders against seriously delayed ones."""
    delivered = data.delivered_orders
    reviewed = delivered[delivered["review_score"].notna()]
    if reviewed.empty:
        return {}

    late = reviewed["is_late"].astype(bool)
    severe = reviewed["days_vs_estimate"] > SEVERE_DELAY_DAYS

    on_time_score = float(reviewed.loc[~late, "review_score"].mean())
    any_late_score = float(reviewed.loc[late, "review_score"].mean())
    severe_score = float(reviewed.loc[severe, "review_score"].mean()) if severe.any() else 0.0

    return {
        "threshold_days": SEVERE_DELAY_DAYS,
        "on_time_orders": int((~late).sum()),
        "on_time_score": on_time_score,
        "any_late_orders": int(late.sum()),
        "any_late_score": any_late_score,
        "severe_orders": int(severe.sum()),
        "severe_score": severe_score,
        "drop_any_late": on_time_score - any_late_score,
        "drop_severe": on_time_score - severe_score,
        "one_star_rate_on_time": float((reviewed.loc[~late, "review_score"] == 1).mean()),
        "one_star_rate_late": float((reviewed.loc[late, "review_score"] == 1).mean()),
        "one_star_rate_severe": (
            float((reviewed.loc[severe, "review_score"] == 1).mean()) if severe.any() else 0.0
        ),
    }


def one_star_attribution(data: AnalysisData) -> dict[str, float]:
    """How much of the one-star population is explained by slow shipping.

    Two directions, because they answer different questions and get confused
    with each other constantly:

      - of orders that arrived late, what share were rated one star
      - of one-star orders, what share shipped slowly

    The second is the weaker of the two on the strict definition - missing the
    promised date explains about a third of one-star reviews - but most one-star
    orders did take materially longer than a typical order, and the promise is
    padded by roughly two weeks, so "not late" is a generous bar.
    """
    delivered = data.delivered_orders
    reviewed = delivered[delivered["review_score"].notna()]
    if reviewed.empty:
        return {}

    late = reviewed["is_late"].astype(bool)
    one_star = reviewed["review_score"] == 1
    median_days = float(reviewed["delivery_days"].median())
    slow = reviewed["delivery_days"] > median_days

    return {
        "one_star_orders": int(one_star.sum()),
        "late_orders": int(late.sum()),
        "median_delivery_days": median_days,
        # Of late orders, the share rated one star.
        "one_star_share_of_late": float(one_star[late].mean()),
        # Of one-star orders, the share that missed the promised date.
        "late_share_of_one_star": float(late[one_star].mean()),
        # Of one-star orders, the share slower than a typical order.
        "slow_share_of_one_star": float(slow[one_star].mean()),
        "avg_delivery_days_one_star": float(reviewed.loc[one_star, "delivery_days"].mean()),
        "avg_delivery_days_overall": float(reviewed["delivery_days"].mean()),
    }


# ---------------------------------------------------------------------------
# Regional logistics
# ---------------------------------------------------------------------------


def regional_performance(data: AnalysisData) -> pd.DataFrame:
    """Revenue, freight burden, delivery time and satisfaction by region.

    Almost every regional difference in this dataset is really a distance
    measurement: the sellers cluster in the Southeast, so a customer further
    away pays more freight, waits longer and rates lower. Freight is also the
    only cost Olist exposes - there is no cost price anywhere - so the
    freight-to-price ratio stands in for cost pressure.
    """
    orders = data.revenue_orders
    delivered = data.delivered_orders
    if orders.empty:
        return pd.DataFrame()

    regions = orders.groupby("customer_region", as_index=False).agg(
        customers=("customer_unique_id", "nunique"),
        orders=("order_id", "nunique"),
        product_revenue=("price", "sum"),
        freight_revenue=("freight_value", "sum"),
        units=("items", "sum"),
        avg_review_score=("review_score", "mean"),
    )
    timings = delivered.groupby("customer_region", as_index=False).agg(
        avg_delivery_days=("delivery_days", "mean"),
        median_delivery_days=("delivery_days", "median"),
        late_rate=("is_late", "mean"),
    )
    regions = regions.merge(timings, on="customer_region", how="left")

    regions["avg_order_value"] = regions["product_revenue"] / regions["orders"]
    regions["avg_item_price"] = regions["product_revenue"] / regions["units"]
    regions["freight_to_price_ratio"] = (
        regions["freight_revenue"] / regions["product_revenue"]
    )
    regions["pct_of_revenue"] = (
        regions["product_revenue"] / regions["product_revenue"].sum()
    )
    return regions.sort_values("product_revenue", ascending=False).reset_index(drop=True)


def seller_region_share(data: AnalysisData) -> pd.DataFrame:
    """Where the goods ship from, as a share of revenue.

    This is the explanation for `regional_performance`: the supply base is
    concentrated in one region, so distance from it drives the rest.
    """
    lines = data.revenue_lines
    if lines.empty or "seller_region" not in lines.columns:
        return pd.DataFrame()

    sellers = lines.groupby("seller_region", as_index=False).agg(
        sellers=("seller_id", "nunique"),
        units=("price", "size"),
        product_revenue=("price", "sum"),
    )
    sellers["pct_of_revenue"] = (
        sellers["product_revenue"] / sellers["product_revenue"].sum()
    )
    return sellers.sort_values("product_revenue", ascending=False).reset_index(drop=True)
