"""Loading the analysis dataset and building the order-line fact table.

Everything downstream - the analytics modules, the charts, the dashboard and
the tests - works from the single fact table built here. That is deliberate:
the revenue definition and the delivery-lateness definition are each written
once, so a change propagates everywhere instead of being re-implemented per
chart.

Three things this module is responsible for getting right, because they are
the ones that quietly ruin Olist analyses:

1. ``customer_unique_id`` is attached to every line. ``customer_id`` is issued
   per order, so any customer-level grouping must use the unique id.
2. There is no ``quantity`` column. One row is one unit, so a unit count is a
   row count.
3. The reporting window excludes the sparse tail months at either end of the
   dataset, which otherwise produce meaningless growth rates.
"""

from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

from marketlens.config import (
    ANALYSIS_END,
    ANALYSIS_START,
    COMPLETED_STATUS,
    DATA_SOURCE,
    NON_REVENUE_STATUSES,
    PROCESSED_DIR,
    USE_FULL_WINDOW,
)
from marketlens.data_processing.database import database_available, get_engine

logger = logging.getLogger(__name__)

Source = Literal["parquet", "postgres", "auto"]

TABLES: tuple[str, ...] = (
    "customers", "sellers", "products", "orders",
    "order_items", "order_payments", "order_reviews",
)

#: Columns PostgreSQL returns as Decimal and Parquet as float.
_NUMERIC_COLUMNS = {
    "order_items": ["price", "freight_value"],
    "order_payments": ["payment_value", "payment_installments", "payment_sequential"],
    "order_reviews": ["review_score"],
}

_DATE_COLUMNS = {
    "orders": ["order_purchase_timestamp", "order_approved_at",
               "order_delivered_carrier_date", "order_delivered_customer_date",
               "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}


def resolve_source(source: Source | None = None) -> str:
    """Decide whether to read from PostgreSQL or the processed files."""
    requested = (source or DATA_SOURCE or "auto").lower()
    if requested in {"postgres", "parquet"}:
        return requested
    return "postgres" if database_available() else "parquet"


def load_tables(source: Source | None = None) -> dict[str, pd.DataFrame]:
    """Load the seven cleaned tables from the resolved source."""
    resolved = resolve_source(source)
    if resolved == "postgres":
        engine = get_engine()
        tables = {name: pd.read_sql_table(name, engine) for name in TABLES}
        logger.info("Loaded dataset from PostgreSQL")
    else:
        missing = [t for t in TABLES if not (PROCESSED_DIR / f"{t}.parquet").exists()]
        if missing:
            raise FileNotFoundError(
                f"Missing processed files: {missing}. Run "
                "`python -m marketlens.data_processing` first."
            )
        tables = {t: pd.read_parquet(PROCESSED_DIR / f"{t}.parquet") for t in TABLES}
        logger.info("Loaded dataset from %s", PROCESSED_DIR)

    for name, columns in _NUMERIC_COLUMNS.items():
        for column in columns:
            if column in tables[name].columns:
                tables[name][column] = tables[name][column].astype(float)

    for name, columns in _DATE_COLUMNS.items():
        for column in columns:
            if column in tables[name].columns:
                tables[name][column] = pd.to_datetime(tables[name][column])

    return tables


def build_order_lines(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build the order-line fact table used by every analysis.

    One row per (order, item sequence) - which is one unit sold - enriched with
    customer, seller, product, delivery and review context.
    """
    items = tables["order_items"]
    orders = tables["orders"]
    products = tables["products"]
    customers = tables["customers"]
    sellers = tables["sellers"]
    reviews = tables["order_reviews"]

    lines = (
        items.merge(
            orders[["order_id", "customer_id", "order_status",
                    "order_purchase_timestamp", "order_delivered_customer_date",
                    "order_estimated_delivery_date", "order_approved_at"]],
            on="order_id", how="inner", validate="many_to_one",
        )
        .merge(
            products[["product_id", "category_en", "category_group",
                      "product_weight_g", "product_volume_cm3", "product_photos_qty"]],
            on="product_id", how="inner", validate="many_to_one",
        )
        .merge(
            customers[["customer_id", "customer_unique_id", "customer_city",
                       "customer_state", "customer_region"]],
            on="customer_id", how="inner", validate="many_to_one",
        )
        .merge(
            sellers[["seller_id", "seller_city", "seller_state", "seller_region"]],
            on="seller_id", how="inner", validate="many_to_one",
        )
        .merge(
            reviews[["order_id", "review_score", "review_creation_date"]],
            on="order_id", how="left", validate="many_to_one",
        )
    )

    # --- money -----------------------------------------------------------
    # price is the product revenue; freight is what the customer paid to have
    # it shipped. They are kept apart because freight is a pass-through cost,
    # not margin, and the freight burden is an analysis in its own right.
    lines["item_total"] = (lines["price"] + lines["freight_value"]).round(2)

    # --- status ----------------------------------------------------------
    lines["is_revenue"] = ~lines["order_status"].isin(NON_REVENUE_STATUSES)
    lines["is_delivered"] = lines["order_status"] == COMPLETED_STATUS

    # --- delivery --------------------------------------------------------
    delivered = lines["order_delivered_customer_date"]
    lines["delivery_days"] = (
        delivered.dt.normalize() - lines["order_purchase_timestamp"].dt.normalize()
    ).dt.days
    lines["days_vs_estimate"] = (
        delivered.dt.normalize() - lines["order_estimated_delivery_date"].dt.normalize()
    ).dt.days
    # Nullable boolean on purpose: an order with no delivery date is neither
    # late nor on time. A plain bool column would silently record those orders
    # as on-time and understate the late rate.
    days_vs_estimate = lines["days_vs_estimate"]
    lines["is_late"] = (days_vs_estimate > 0).astype("boolean").mask(days_vs_estimate.isna())

    # --- time ------------------------------------------------------------
    lines["order_month"] = (
        lines["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    )
    lines["order_year"] = lines["order_purchase_timestamp"].dt.year

    return lines


def build_order_summary(lines: pd.DataFrame,
                        orders: pd.DataFrame | None = None,
                        customers: pd.DataFrame | None = None) -> pd.DataFrame:
    """Roll the fact table up to one row per order.

    Order counts and average order value must be computed here, not on the line
    table - counting lines would multiply orders by basket size.

    ``orders`` must be supplied for any count over the whole order population.
    767 orders - almost all ``unavailable`` or ``canceled`` - have no line items
    at all, so a summary built only from lines silently loses them and reports a
    cancellation rate roughly a third too low. Those orders are re-attached here
    with zero items and zero revenue, which is what they are.
    """
    summary = lines.groupby("order_id", as_index=False).agg(
        customer_id=("customer_id", "first"),
        customer_unique_id=("customer_unique_id", "first"),
        order_purchase_timestamp=("order_purchase_timestamp", "first"),
        order_month=("order_month", "first"),
        order_year=("order_year", "first"),
        order_status=("order_status", "first"),
        customer_city=("customer_city", "first"),
        customer_state=("customer_state", "first"),
        customer_region=("customer_region", "first"),
        is_revenue=("is_revenue", "first"),
        is_delivered=("is_delivered", "first"),
        is_late=("is_late", "first"),
        delivery_days=("delivery_days", "first"),
        days_vs_estimate=("days_vs_estimate", "first"),
        review_score=("review_score", "first"),
        items=("order_item_id", "size"),
        sellers=("seller_id", "nunique"),
        products=("product_id", "nunique"),
        price=("price", "sum"),
        freight_value=("freight_value", "sum"),
        item_total=("item_total", "sum"),
    )
    if orders is not None:
        missing = orders[~orders["order_id"].isin(set(summary["order_id"]))]
        if len(missing):
            empty = missing[["order_id", "customer_id", "order_status",
                             "order_purchase_timestamp",
                             "order_delivered_customer_date",
                             "order_estimated_delivery_date"]].copy()
            empty["order_month"] = (
                empty["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
            )
            empty["order_year"] = empty["order_purchase_timestamp"].dt.year
            empty["is_revenue"] = ~empty["order_status"].isin(NON_REVENUE_STATUSES)
            empty["is_delivered"] = empty["order_status"] == COMPLETED_STATUS
            days = (
                empty["order_delivered_customer_date"].dt.normalize()
                - empty["order_estimated_delivery_date"].dt.normalize()
            ).dt.days
            empty["days_vs_estimate"] = days
            empty["delivery_days"] = (
                empty["order_delivered_customer_date"].dt.normalize()
                - empty["order_purchase_timestamp"].dt.normalize()
            ).dt.days
            empty["is_late"] = (days > 0).astype("boolean").mask(days.isna())
            # float rather than pd.NA so the column dtype matches the frame it
            # is concatenated onto; an object column would trigger a dtype warning
            # and silently change review_score's type.
            empty["review_score"] = float("nan")
            for column, value in (("items", 0), ("sellers", 0), ("products", 0),
                                  ("price", 0.0), ("freight_value", 0.0),
                                  ("item_total", 0.0)):
                empty[column] = value

            if customers is not None:
                empty = empty.merge(
                    customers[["customer_id", "customer_unique_id", "customer_city",
                               "customer_state", "customer_region"]],
                    on="customer_id", how="left",
                )
            empty = empty.drop(columns=["order_delivered_customer_date",
                                        "order_estimated_delivery_date"])
            empty = empty.reindex(columns=summary.columns)
            summary = pd.concat([summary, empty], ignore_index=True)

    summary["freight_ratio"] = (
        summary["freight_value"] / summary["item_total"].where(summary["item_total"] > 0)
    )
    return summary


class AnalysisData:
    """Container holding the loaded tables and the derived frames.

    Built once per run (or once per dashboard session) and passed to the
    analytics functions, so the joins are not repeated for every chart.

    By default the frames are restricted to the reporting window - see
    ``marketlens.config`` for why the sparse tail months are excluded.
    """

    def __init__(self, tables: dict[str, pd.DataFrame],
                 apply_window: bool | None = None) -> None:
        self.tables = tables
        self.customers = tables["customers"]
        self.sellers = tables["sellers"]
        self.products = tables["products"]
        self.order_payments = tables["order_payments"]

        lines = build_order_lines(tables)
        orders = tables["orders"]
        reviews = tables["order_reviews"]

        use_window = (not USE_FULL_WINDOW) if apply_window is None else apply_window
        self.window_applied = use_window
        if use_window:
            start, end = pd.Timestamp(ANALYSIS_START), pd.Timestamp(ANALYSIS_END)
            end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            in_window = lines["order_purchase_timestamp"].between(start, end)
            excluded = int((~in_window).sum())
            lines = lines[in_window]
            orders = orders[orders["order_purchase_timestamp"].between(start, end)]
            reviews = reviews[reviews["order_id"].isin(set(orders["order_id"]))]
            if excluded:
                logger.info(
                    "Reporting window %s..%s excludes %s order lines in the sparse tails",
                    ANALYSIS_START, ANALYSIS_END, f"{excluded:,}",
                )

        self.orders = orders
        self.order_items = tables["order_items"][
            tables["order_items"]["order_id"].isin(set(orders["order_id"]))
        ]
        self.order_reviews = reviews
        self.lines = lines.reset_index(drop=True)
        self.order_summary = build_order_summary(
            self.lines, orders=self.orders, customers=self.customers
        )

    @classmethod
    def load(cls, source: Source | None = None,
             apply_window: bool | None = None) -> "AnalysisData":
        return cls(load_tables(source), apply_window=apply_window)

    # -- convenience views used repeatedly by the analytics modules ---------

    @property
    def revenue_lines(self) -> pd.DataFrame:
        """Order lines that count towards revenue."""
        return self.lines[self.lines["is_revenue"]]

    @property
    def delivered_lines(self) -> pd.DataFrame:
        """Order lines that were delivered."""
        return self.lines[self.lines["is_delivered"]]

    @property
    def revenue_orders(self) -> pd.DataFrame:
        """Orders that count towards revenue.

        Requires at least one line item as well as a revenue-bearing status. A
        handful of orders sit in 'created' or 'invoiced' with nothing on them:
        they are real orders and belong in the cancellation denominator, but
        they carry no revenue, so counting them would add a zero to the average
        order value and count their customer as a buyer who bought nothing.
        """
        summary = self.order_summary
        return summary[summary["is_revenue"] & (summary["items"] > 0)]

    @property
    def delivered_orders(self) -> pd.DataFrame:
        """Delivered orders that have a delivery date, so lateness is knowable."""
        delivered = self.order_summary[self.order_summary["is_delivered"]]
        return delivered[delivered["days_vs_estimate"].notna()]

    @property
    def as_of_date(self) -> pd.Timestamp:
        """The most recent revenue-bearing purchase in the dataset.

        Recency is measured against this rather than today's date, so customer
        segmentation does not drift as the dataset ages. Olist ends in 2018.
        """
        return self.revenue_orders["order_purchase_timestamp"].max()

    def describe(self) -> dict[str, int]:
        """Row counts for the data actually in scope.

        Customer, seller and product counts are restricted to what the in-scope
        orders reference, so they reconcile with the order counts rather than
        reporting the full dimension tables.
        """
        return {
            "orders": len(self.orders),
            "order_items": len(self.order_items),
            "order_payments": len(self.order_payments),
            "order_reviews": len(self.order_reviews),
            "customer_accounts": int(self.lines["customer_id"].nunique()),
            "unique_customers": int(self.lines["customer_unique_id"].nunique()),
            "sellers": int(self.lines["seller_id"].nunique()),
            "products": int(self.lines["product_id"].nunique()),
        }

    def subset(self, lines: pd.DataFrame,
               extra_order_ids: set[str] | None = None) -> "AnalysisData":
        """Build a new AnalysisData restricted to the given order lines.

        Used by the dashboard filters. Dimension tables are narrowed to what
        the surviving lines reference, and reviews are cut to the surviving
        orders - otherwise a filtered review average would be computed over an
        unfiltered population.

        ``extra_order_ids`` carries through orders that have no line items at
        all and so can never appear in ``lines``. In this dataset 739 orders in
        the reporting window are line-less - every one of the 602 'unavailable'
        orders among them - so selecting on lines alone reports an unavailable
        count of exactly zero. They contribute no revenue by construction; they
        exist to keep the order, cancellation and unfulfilled counts honest.
        """
        order_ids = set(lines["order_id"])
        if extra_order_ids:
            order_ids |= set(extra_order_ids)
        clone = object.__new__(AnalysisData)
        clone.tables = self.tables
        clone.window_applied = self.window_applied
        clone.customers = self.customers[
            self.customers["customer_id"].isin(set(lines["customer_id"]))
        ]
        clone.sellers = self.sellers[self.sellers["seller_id"].isin(set(lines["seller_id"]))]
        clone.products = self.products[
            self.products["product_id"].isin(set(lines["product_id"]))
        ]
        clone.orders = self.orders[self.orders["order_id"].isin(order_ids)]
        clone.order_items = self.order_items[self.order_items["order_id"].isin(order_ids)]
        clone.order_payments = self.order_payments[
            self.order_payments["order_id"].isin(order_ids)
        ]
        clone.order_reviews = self.order_reviews[
            self.order_reviews["order_id"].isin(order_ids)
        ]
        clone.lines = lines
        clone.order_summary = build_order_summary(
            lines, orders=clone.orders, customers=self.customers
        )
        return clone
