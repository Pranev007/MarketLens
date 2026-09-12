"""Cohort retention analysis.

A cohort is the set of customers whose first purchase falls in a given month.
Retention in month N is the share of that cohort that ordered again N months
later.

Two things make this analysis different on Olist than on a typical retail
dataset, and both have to be stated rather than glossed over:

1. **Cohorts key on ``customer_unique_id``.** Olist issues a new
   ``customer_id`` per order, so a cohort table built on it shows exactly 0%
   retention in every cell - a result that looks like a catastrophic business
   failure and is actually a join error.

2. **Retention here is genuinely very low.** Around 3% of customers ever place
   a second order. The cohort table is therefore mostly single-digit
   percentages, and that is the finding, not a bug. The numbers are small
   enough that individual cells are noisy, so the trend is read from a fixed
   90-day window rather than from single cells.

Cells beyond a cohort's observable horizon are NaN, not zero: "not yet
observable" and "nobody came back" are different facts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from marketlens.data_processing.datasets import AnalysisData


# Sorting a customer's orders by timestamp alone is ambiguous: 281 customers in
# this dataset placed two orders on the identical timestamp - a split basket, or
# a second checkout in the same session. Which one counts as "the first order"
# then depends on row order, so every "first order" rule here breaks the tie on
# order_id. The SQL side does the same (see the DISTINCT ON in Q20), which is
# what keeps the two implementations comparable.
ORDER_SEQUENCE = ["order_purchase_timestamp", "order_id"]


def cohort_base(data: AnalysisData) -> pd.DataFrame:
    """Order activity keyed on the person, with their cohort attached.

    Unlike a dataset with a signup date, Olist has no customer registration
    event - the first purchase IS the acquisition. There is therefore no left
    truncation to correct for beyond the start of the reporting window itself,
    which the first-cohort caveat in the report covers.
    """
    orders = data.revenue_orders.copy()

    first_order = orders.groupby("customer_unique_id")["order_purchase_timestamp"].transform("min")
    orders["cohort_month"] = first_order.dt.to_period("M").dt.to_timestamp()
    orders["months_since"] = (
        (orders["order_month"].dt.year - orders["cohort_month"].dt.year) * 12
        + (orders["order_month"].dt.month - orders["cohort_month"].dt.month)
    )
    orders["first_order_timestamp"] = first_order
    orders["days_since_first"] = (
        orders["order_purchase_timestamp"] - first_order
    ).dt.days
    # A repeat order is any order placed strictly after the first, compared on
    # the TIMESTAMP rather than on whole days. Some customers place a second
    # order an hour after the first - a split basket or a second checkout in
    # the same session - and those have days_since_first = 0. Testing
    # `days_since_first > 0` would silently drop them, which would make the
    # 90-day retention figure disagree with the headline repeat purchase rate
    # computed on distinct order counts.
    orders["is_repeat_order"] = orders["order_purchase_timestamp"] > first_order
    return orders


def cohort_retention_matrix(data: AnalysisData, max_months: int = 12) -> pd.DataFrame:
    """Retention percentage by cohort and cohort age.

    Cells the data cannot yet speak to are NaN.
    """
    activity = cohort_base(data)
    if activity.empty:
        return pd.DataFrame()

    counts = (
        activity.groupby(["cohort_month", "months_since"])["customer_unique_id"]
        .nunique()
        .unstack(fill_value=0)
    )
    retention = counts.div(counts[0], axis=0) * 100

    last_month = activity["order_month"].max()
    months_observable = (
        (last_month.year - retention.index.year) * 12
        + (last_month.month - retention.index.month)
    )
    horizon = pd.DataFrame(
        np.arange(retention.shape[1])[None, :] <= np.asarray(months_observable)[:, None],
        index=retention.index, columns=retention.columns,
    )
    retention = retention.where(horizon)

    keep = [c for c in retention.columns if c <= max_months]
    return retention[keep]


def cohort_sizes(data: AnalysisData) -> pd.DataFrame:
    """Number of customers acquired in each cohort month, and what they spent."""
    activity = cohort_base(data)
    first_orders = activity[activity["months_since"] == 0]
    sizes = first_orders.groupby("cohort_month", as_index=False).agg(
        cohort_customers=("customer_unique_id", "nunique"),
        first_order_revenue=("price", "sum"),
    )
    sizes["avg_first_order_value"] = (
        sizes["first_order_revenue"] / sizes["cohort_customers"]
    )
    return sizes


def repeat_within_days(data: AnalysisData, days: int = 90) -> pd.DataFrame:
    """Share of each cohort that placed another order within ``days``.

    A single comparable number per cohort. Only cohorts that have had the full
    window to come back are included.
    """
    activity = cohort_base(data)
    if activity.empty:
        return pd.DataFrame()

    last_date = activity["order_purchase_timestamp"].max()
    activity = activity.assign(
        within_window=activity["is_repeat_order"] & (
            activity["order_purchase_timestamp"]
            <= activity["first_order_timestamp"] + pd.Timedelta(days=days)
        )
    )
    per_customer = activity.groupby("customer_unique_id", as_index=False).agg(
        cohort_month=("cohort_month", "first"),
        first_order_date=("order_purchase_timestamp", "min"),
        returned=("within_window", "any"),
    )
    mature = per_customer[
        per_customer["first_order_date"] <= last_date - pd.Timedelta(days=days)
    ]

    by_cohort = mature.groupby("cohort_month", as_index=False).agg(
        cohort_customers=("customer_unique_id", "count"),
        returned=("returned", "sum"),
    )
    by_cohort = by_cohort[by_cohort["cohort_customers"] >= 50]
    by_cohort["repeat_rate"] = by_cohort["returned"] / by_cohort["cohort_customers"]
    by_cohort["repeat_rate_3cohort_avg"] = (
        by_cohort["repeat_rate"].rolling(3, min_periods=1).mean()
    )
    return by_cohort.reset_index(drop=True)


def retention_by_dimension(data: AnalysisData, dimension: str = "customer_region",
                           days: int = 90, min_customers: int = 200) -> pd.DataFrame:
    """Repeat-within-``days`` rate cut by a customer attribute.

    Olist has no acquisition-channel field, so the question "which customers
    come back" has to be answered from what the data does carry: where they
    are, what they bought, and what happened to their first delivery.
    """
    activity = cohort_base(data)
    if activity.empty:
        return pd.DataFrame()

    last_date = activity["order_purchase_timestamp"].max()
    activity = activity.assign(
        within_window=activity["is_repeat_order"] & (
            activity["order_purchase_timestamp"]
            <= activity["first_order_timestamp"] + pd.Timedelta(days=days)
        )
    )
    # Row-wise for the same reason as retention_by_first_experience below:
    # the dimension has to come from the first order itself, not from the first
    # order that happens to have a non-null value for it.
    ordered = activity.sort_values(ORDER_SEQUENCE)
    first_rows = ordered.drop_duplicates("customer_unique_id", keep="first")
    returned = ordered.groupby("customer_unique_id")["within_window"].any()
    per_customer = pd.DataFrame({
        "customer_unique_id": first_rows["customer_unique_id"].to_numpy(),
        "first_order_date": first_rows["order_purchase_timestamp"].to_numpy(),
        "returned": first_rows["customer_unique_id"].map(returned).to_numpy(),
        dimension: first_rows[dimension].to_numpy(),
    })
    mature = per_customer[
        per_customer["first_order_date"] <= last_date - pd.Timedelta(days=days)
    ]

    grouped = mature.groupby(dimension, as_index=False).agg(
        customers=("customer_unique_id", "count"),
        repeat_rate=("returned", "mean"),
    )
    grouped = grouped[grouped["customers"] >= min_customers]
    grouped["pct_of_customers"] = grouped["customers"] / grouped["customers"].sum()
    return grouped.sort_values("repeat_rate", ascending=False).reset_index(drop=True)


def retention_by_first_experience(data: AnalysisData, days: int = 90) -> pd.DataFrame:
    """Does a bad first delivery stop customers coming back?

    The most useful retention cut available in this dataset. Each customer is
    grouped by what happened on their first order - delivered on time, delivered
    late, or reviewed badly - and measured on whether they returned.

    Association, not proof: customers who had a late first delivery may differ
    in other ways (remote regions, bulky items) that independently reduce
    repeat purchasing.
    """
    activity = cohort_base(data)
    if activity.empty:
        return pd.DataFrame()

    last_date = activity["order_purchase_timestamp"].max()
    activity = activity.assign(
        within_window=activity["is_repeat_order"] & (
            activity["order_purchase_timestamp"]
            <= activity["first_order_timestamp"] + pd.Timedelta(days=days)
        )
    )
    # Take the whole first-order ROW rather than aggregating each column with
    # "first". Pandas' groupby "first" skips nulls per column, so a customer
    # whose first order was invoiced-but-never-delivered would take their date
    # from that order and their delivery outcome from the NEXT one - stitching
    # a first order that never existed. 55 customers here have exactly that
    # shape: two orders on the same timestamp, one undelivered. SQL's
    # DISTINCT ON takes the row, so this has to as well or the two disagree.
    ordered = activity.sort_values(ORDER_SEQUENCE)
    first_rows = ordered.drop_duplicates("customer_unique_id", keep="first")
    returned = ordered.groupby("customer_unique_id")["within_window"].any()
    per_customer = pd.DataFrame({
        "customer_unique_id": first_rows["customer_unique_id"].to_numpy(),
        "first_order_date": first_rows["order_purchase_timestamp"].to_numpy(),
        "first_was_late": first_rows["is_late"].to_numpy(),
        "first_review": first_rows["review_score"].to_numpy(),
        "first_delivery_days": first_rows["delivery_days"].to_numpy(),
        "returned": first_rows["customer_unique_id"].map(returned).to_numpy(),
    })
    mature = per_customer[
        (per_customer["first_order_date"] <= last_date - pd.Timedelta(days=days))
        & per_customer["first_was_late"].notna()
    ].copy()

    mature["first_experience"] = np.where(
        mature["first_was_late"].astype(bool), "First delivery late", "First delivery on time"
    )
    by_delivery = mature.groupby("first_experience", as_index=False).agg(
        customers=("customer_unique_id", "count"),
        repeat_rate=("returned", "mean"),
        avg_first_review=("first_review", "mean"),
        avg_delivery_days=("first_delivery_days", "mean"),
    )

    rated = mature[mature["first_review"].notna()].copy()
    rated["first_experience"] = np.where(
        rated["first_review"] <= 2, "First review 1-2 stars",
        np.where(rated["first_review"] == 3, "First review 3 stars",
                 "First review 4-5 stars"),
    )
    by_review = rated.groupby("first_experience", as_index=False).agg(
        customers=("customer_unique_id", "count"),
        repeat_rate=("returned", "mean"),
        avg_first_review=("first_review", "mean"),
        avg_delivery_days=("first_delivery_days", "mean"),
    )

    return pd.concat([by_delivery, by_review], ignore_index=True)


def time_between_orders(data: AnalysisData) -> dict[str, float]:
    """Distribution of the gap between consecutive orders.

    Only about 3% of customers ever produce a gap at all, so this describes a
    small subset - the ones who did come back.
    """
    orders = data.revenue_orders.sort_values(
        ["customer_unique_id", *ORDER_SEQUENCE]
    )
    gaps = (
        orders.groupby("customer_unique_id")["order_purchase_timestamp"]
        .diff().dt.days.dropna()
    )
    if gaps.empty:
        return {}

    per_customer_median = (
        orders.assign(
            gap=orders.groupby("customer_unique_id")["order_purchase_timestamp"]
            .diff().dt.days
        )
        .dropna(subset=["gap"])
        .groupby("customer_unique_id")["gap"].median()
    )

    return {
        "repeat_purchases": int(len(gaps)),
        "repeat_customers": int(per_customer_median.size),
        "mean_days": float(gaps.mean()),
        "p25_days": float(gaps.quantile(0.25)),
        "median_days": float(gaps.median()),
        "p75_days": float(gaps.quantile(0.75)),
        "p90_days": float(gaps.quantile(0.90)),
        "pct_within_30d": float((gaps <= 30).mean()),
        "pct_within_90d": float((gaps <= 90).mean()),
        "pct_within_180d": float((gaps <= 180).mean()),
        "median_of_customer_medians": float(per_customer_median.median()),
    }
