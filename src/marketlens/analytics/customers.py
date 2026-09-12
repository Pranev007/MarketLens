"""Customer behaviour, value and RFM segmentation.

Everything in this module keys on ``customer_unique_id``. Olist issues a fresh
``customer_id`` for every order, so grouping on it reports a repeat purchase
rate of 0.00% - the single most common error made with this dataset, and one
that inverts the headline conclusion.

RFM methodology, stated so it can be challenged:

    Recency   - days between the customer's last order and the most recent
                order in the dataset. Measured against the data, not today, so
                the segmentation does not drift as the data ages. Olist ends in
                2018, so wall-clock recency would put every customer in the
                same bucket.
    Frequency - count of distinct revenue-bearing orders.
    Monetary  - lifetime product revenue.

A caveat that matters more here than in most RFM work: 97% of these customers
bought exactly once, so Frequency carries almost no information. Quintiles on
it are close to meaningless, and the segmentation leans on Recency and Monetary
instead. That is a finding about the business, not a flaw in the method - and
it is why the segment names below differ from a textbook RFM scheme.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from marketlens.data_processing.datasets import AnalysisData

#: Segment rules, applied in order - the first match wins.
SEGMENT_RULES: tuple[tuple[str, str], ...] = (
    ("Champions", "frequency >= 2 and r_score >= 4 and m_score >= 4"),
    ("Repeat - At Risk", "frequency >= 2 and r_score <= 2"),
    ("Repeat", "frequency >= 2"),
    ("High-Value One-Off", "frequency == 1 and m_score == 5 and r_score >= 3"),
    ("Recent One-Off", "frequency == 1 and r_score >= 4"),
    ("Lapsed - Higher Value", "frequency == 1 and r_score <= 2 and m_score >= 4"),
    ("Lapsed - Low Value", "frequency == 1 and r_score <= 2"),
)
DEFAULT_SEGMENT = "Single Purchase - Mid"

SEGMENT_MEANING: dict[str, dict[str, str]] = {
    "Champions": {
        "meaning": "Bought more than once, recently, and spent well. Rare here.",
        "action": "Protect and study. This group is the proof repeat is possible - "
                  "find what they have in common and target it.",
    },
    "Repeat - At Risk": {
        "meaning": "Bought more than once but have gone quiet.",
        "action": "Highest-value win-back target. They already proved they will "
                  "come back once; the second return is cheaper than a new customer.",
    },
    "Repeat": {
        "meaning": "More than one order, mid recency and value.",
        "action": "Nurture towards a third order - the point where a customer "
                  "starts to look like a relationship rather than a transaction.",
    },
    "High-Value One-Off": {
        "meaning": "One large order, placed reasonably recently.",
        "action": "The most promising conversion target: the spend is there, "
                  "the habit is not. Post-purchase follow-up and category cross-sell.",
    },
    "Recent One-Off": {
        "meaning": "One order, recently. Value not yet established.",
        "action": "Second-purchase programme, triggered from delivery rather than "
                  "from a calendar date.",
    },
    "Lapsed - Higher Value": {
        "meaning": "One good order, long ago, never returned.",
        "action": "Worth a reactivation test - the order value justifies the cost.",
    },
    "Lapsed - Low Value": {
        "meaning": "One small order, long ago.",
        "action": "Low-cost automated reactivation only. Do not spend here.",
    },
    "Single Purchase - Mid": {
        "meaning": "One order, middling on both recency and value.",
        "action": "The bulk of the base. Address through broad lifecycle "
                  "automation rather than targeted spend.",
    },
}
def customer_summary(data: AnalysisData) -> pd.DataFrame:
    """One row per purchasing person, with lifetime behaviour measures."""
    orders = data.revenue_orders
    as_of = data.as_of_date

    summary = orders.groupby("customer_unique_id", as_index=False).agg(
        frequency=("order_id", "nunique"),
        monetary=("price", "sum"),
        freight_paid=("freight_value", "sum"),
        units=("items", "sum"),
        first_order_date=("order_purchase_timestamp", "min"),
        last_order_date=("order_purchase_timestamp", "max"),
        avg_review_score=("review_score", "mean"),
        accounts=("customer_id", "nunique"),
        states=("customer_state", "nunique"),
    )
    summary["recency_days"] = (as_of - summary["last_order_date"]).dt.days
    summary["tenure_days"] = (
        summary["last_order_date"] - summary["first_order_date"]
    ).dt.days
    summary["avg_order_value"] = summary["monetary"] / summary["frequency"]

    attributes = (
        orders.sort_values("order_purchase_timestamp")
        .groupby("customer_unique_id", as_index=False)
        .agg(customer_city=("customer_city", "last"),
             customer_state=("customer_state", "last"),
             customer_region=("customer_region", "last"))
    )
    return summary.merge(attributes, on="customer_unique_id", how="left")


def rfm_segments(data: AnalysisData) -> pd.DataFrame:
    """Score every purchasing customer on R, F and M and assign a segment."""
    summary = customer_summary(data)

    summary["r_score"] = _quintile(-summary["recency_days"])
    summary["m_score"] = _quintile(summary["monetary"])
    # Frequency is almost degenerate here - 97% of customers have exactly one
    # order - so it is scored but the segment rules use the raw count, which is
    # the only part of it that carries information.
    summary["f_score"] = _quintile(
        summary["frequency"] + summary["monetary"].rank(pct=True) * 0.001
    )
    summary["rfm_score"] = (
        summary["r_score"].astype(str)
        + summary["f_score"].astype(str)
        + summary["m_score"].astype(str)
    )

    segment = pd.Series(DEFAULT_SEGMENT, index=summary.index, dtype=object)
    unassigned = pd.Series(True, index=summary.index)
    for name, rule in SEGMENT_RULES:
        matches = summary.eval(rule) & unassigned
        segment[matches] = name
        unassigned &= ~matches
    summary["segment"] = segment
    return summary


def segment_profile(rfm: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the RFM output into a per-segment profile."""
    profile = rfm.groupby("segment", as_index=False).agg(
        customers=("customer_unique_id", "count"),
        avg_recency_days=("recency_days", "mean"),
        avg_orders=("frequency", "mean"),
        avg_lifetime_revenue=("monetary", "mean"),
        segment_revenue=("monetary", "sum"),
        avg_order_value=("avg_order_value", "mean"),
        avg_review_score=("avg_review_score", "mean"),
    )
    profile["pct_of_customers"] = profile["customers"] / profile["customers"].sum()
    profile["pct_of_revenue"] = profile["segment_revenue"] / profile["segment_revenue"].sum()
    profile["revenue_concentration_index"] = (
        profile["pct_of_revenue"] / profile["pct_of_customers"]
    )
    profile["meaning"] = profile["segment"].map(lambda s: SEGMENT_MEANING[s]["meaning"])
    profile["recommended_action"] = profile["segment"].map(
        lambda s: SEGMENT_MEANING[s]["action"]
    )
    return profile.sort_values("segment_revenue", ascending=False).reset_index(drop=True)
def purchase_frequency_distribution(data: AnalysisData) -> pd.DataFrame:
    """How customers are spread across order counts, and revenue per band."""
    orders = data.revenue_orders.groupby("customer_unique_id", as_index=False).agg(
        orders=("order_id", "nunique"), revenue=("price", "sum")
    )
    bins = [0, 1, 2, 3, 5, np.inf]
    labels = ["1 order", "2 orders", "3 orders", "4-5 orders", "6+ orders"]
    orders["frequency_band"] = pd.cut(
        orders["orders"], bins=bins, labels=labels, right=True, include_lowest=True
    )

    banded = orders.groupby("frequency_band", as_index=False, observed=True).agg(
        customers=("customer_unique_id", "count"),
        orders=("orders", "sum"),
        revenue=("revenue", "sum"),
    )
    banded["pct_of_customers"] = banded["customers"] / banded["customers"].sum()
    banded["pct_of_revenue"] = banded["revenue"] / banded["revenue"].sum()
    banded["revenue_per_customer"] = banded["revenue"] / banded["customers"]
    banded["avg_order_value"] = banded["revenue"] / banded["orders"]
    return banded


def revenue_concentration(data: AnalysisData) -> pd.DataFrame:
    """Cumulative share of revenue held by the top N% of customers."""
    revenue = (
        data.revenue_orders.groupby("customer_unique_id")["price"].sum()
        .sort_values(ascending=False)
        .reset_index(drop=True)
    )
    total = revenue.sum()
    rows = []
    for pct in (1, 5, 10, 20, 50, 100):
        cutoff = max(int(len(revenue) * pct / 100), 1)
        rows.append({
            "top_n_percent": pct,
            "customers": cutoff,
            "cumulative_revenue": float(revenue.head(cutoff).sum()),
            "cumulative_pct_of_revenue": float(revenue.head(cutoff).sum() / total),
        })
    return pd.DataFrame(rows)


def repeat_behaviour(data: AnalysisData) -> dict[str, float]:
    """The repeat-purchase picture, including the trap that produces 0%."""
    orders = data.revenue_orders
    by_person = orders.groupby("customer_unique_id").size()
    by_account = orders.groupby("customer_id").size()

    repeat_customers = by_person[by_person >= 2]
    repeat_revenue = orders[
        orders["customer_unique_id"].isin(set(repeat_customers.index))
    ]["price"].sum()

    return {
        "unique_customers": int(len(by_person)),
        "customer_accounts": int(len(by_account)),
        "repeat_customers": int(len(repeat_customers)),
        "repeat_purchase_rate": float((by_person >= 2).mean()),
        # What the same calculation reports when keyed on the per-order id.
        "repeat_rate_if_keyed_on_customer_id": float((by_account >= 2).mean()),
        "max_orders_by_one_customer": int(by_person.max()),
        "avg_orders_per_customer": float(by_person.mean()),
        "pct_revenue_from_repeat_customers": float(repeat_revenue / orders["price"].sum()),
    }


def top_customers(data: AnalysisData, limit: int = 20) -> pd.DataFrame:
    """The highest lifetime-value customers, with their favourite category."""
    summary = customer_summary(data).nlargest(limit, "monetary")

    lines = data.revenue_lines
    top_category = (
        lines[lines["customer_unique_id"].isin(summary["customer_unique_id"])]
        .groupby(["customer_unique_id", "category_group"], as_index=False)["price"].sum()
        .sort_values("price", ascending=False)
        .drop_duplicates("customer_unique_id")[["customer_unique_id", "category_group"]]
        .rename(columns={"category_group": "top_category"})
    )
    return summary.merge(top_category, on="customer_unique_id", how="left").reset_index(drop=True)


def _quintile(series: pd.Series) -> pd.Series:
    """Score a series 1-5 by quintile, 5 being the highest.

    Ranking before cutting avoids the "bin edges are not unique" failure that
    plain qcut hits when one value is shared by more than a fifth of the rows -
    which is exactly what order count does here, where 97% of customers have
    exactly one.
    """
    ranked = series.rank(method="first")
    return pd.qcut(ranked, 5, labels=[1, 2, 3, 4, 5]).astype(int)
