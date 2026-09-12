"""Data-quality validation run against the cleaned Olist dataset.

These are the checks an analyst should be able to point at when asked "how do
you know the numbers are right?". They run after cleaning, so a failure means
either a cleaning rule is wrong or the source has a problem the rules do not
yet cover.

Some checks are deliberately informational rather than pass/fail - coverage of
delivery dates, for instance, is a fact about the source that the analysis has
to work around, not a defect to fix.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from marketlens.config import ALL_STATUSES
from marketlens.data_processing.cleaning import FULFILMENT_STATUSES

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "customers": {
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state", "customer_region",
    },
    "sellers": {
        "seller_id", "seller_zip_code_prefix", "seller_city",
        "seller_state", "seller_region",
    },
    "products": {
        "product_id", "category_pt", "category_en", "category_group",
        "product_name_length", "product_description_length", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm",
        "product_width_cm", "product_volume_cm3",
    },
    "orders": {
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date",
    },
    "order_items": {
        "order_id", "order_item_id", "product_id", "seller_id",
        "shipping_limit_date", "price", "freight_value",
    },
    "order_payments": {
        "order_id", "payment_sequential", "payment_type",
        "payment_installments", "payment_value",
    },
    "order_reviews": {
        "review_id", "order_id", "review_score", "review_comment_title",
        "review_comment_message", "review_creation_date", "review_answer_timestamp",
    },
}

PRIMARY_KEYS: dict[str, list[str]] = {
    "customers": ["customer_id"],
    "sellers": ["seller_id"],
    "products": ["product_id"],
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "order_payments": ["order_id", "payment_sequential"],
    "order_reviews": ["order_id"],
}

NOT_NULL: dict[str, list[str]] = {
    "customers": ["customer_id", "customer_unique_id", "customer_city",
                  "customer_state", "customer_region"],
    "sellers": ["seller_id", "seller_city", "seller_state", "seller_region"],
    "products": ["product_id", "category_en", "category_group"],
    "orders": ["order_id", "customer_id", "order_status",
               "order_purchase_timestamp", "order_estimated_delivery_date"],
    "order_items": ["order_id", "order_item_id", "product_id", "seller_id",
                    "price", "freight_value"],
    "order_payments": ["order_id", "payment_sequential", "payment_type",
                       "payment_value"],
    "order_reviews": ["review_id", "order_id", "review_score",
                      "review_creation_date"],
}


@dataclass
class Check:
    category: str
    check: str
    scope: str
    failures: int
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.failures == 0


def validate_dataset(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Run every validation check and return the results as a DataFrame."""
    checks: list[Check] = []
    checks += _check_schema(tables)
    checks += _check_keys(tables)
    checks += _check_nulls(tables)
    checks += _check_referential_integrity(tables)
    checks += _check_value_ranges(tables)
    checks += _check_business_rules(tables)
    checks += _check_coverage(tables)

    frame = pd.DataFrame(
        [
            {
                "category": c.category, "check": c.check, "scope": c.scope,
                "status": "PASS" if c.passed else "FAIL",
                "failing_rows": c.failures, "detail": c.detail,
            }
            for c in checks
        ]
    )
    failed = int((frame["status"] == "FAIL").sum())
    logger.info("Data quality: %s checks, %s failed", len(frame), failed)
    return frame


def _check_schema(tables: dict[str, pd.DataFrame]) -> list[Check]:
    results = []
    for name, expected in EXPECTED_COLUMNS.items():
        missing = expected - set(tables.get(name, pd.DataFrame()).columns)
        results.append(Check("schema", "expected columns present", name, len(missing),
                             f"missing: {sorted(missing)}" if missing else ""))
    return results


def _check_keys(tables: dict[str, pd.DataFrame]) -> list[Check]:
    results = []
    for name, keys in PRIMARY_KEYS.items():
        duplicates = int(tables[name].duplicated(subset=keys).sum())
        results.append(Check("uniqueness", f"unique {'+'.join(keys)}", name, duplicates))
    return results


def _check_nulls(tables: dict[str, pd.DataFrame]) -> list[Check]:
    results = []
    for name, columns in NOT_NULL.items():
        for column in columns:
            nulls = int(tables[name][column].isna().sum())
            results.append(Check("completeness", f"{column} not null", name, nulls))
    return results


def _check_referential_integrity(tables: dict[str, pd.DataFrame]) -> list[Check]:
    customers, sellers, products = tables["customers"], tables["sellers"], tables["products"]
    orders, items = tables["orders"], tables["order_items"]
    payments, reviews = tables["order_payments"], tables["order_reviews"]

    return [
        Check("referential", "orders.customer_id exists in customers", "orders",
              int((~orders["customer_id"].isin(set(customers["customer_id"]))).sum())),
        Check("referential", "order_items.order_id exists in orders", "order_items",
              int((~items["order_id"].isin(set(orders["order_id"]))).sum())),
        Check("referential", "order_items.product_id exists in products", "order_items",
              int((~items["product_id"].isin(set(products["product_id"]))).sum())),
        Check("referential", "order_items.seller_id exists in sellers", "order_items",
              int((~items["seller_id"].isin(set(sellers["seller_id"]))).sum())),
        Check("referential", "order_payments.order_id exists in orders", "order_payments",
              int((~payments["order_id"].isin(set(orders["order_id"]))).sum())),
        Check("referential", "order_reviews.order_id exists in orders", "order_reviews",
              int((~reviews["order_id"].isin(set(orders["order_id"]))).sum())),
    ]


def _check_value_ranges(tables: dict[str, pd.DataFrame]) -> list[Check]:
    items, payments, reviews = (
        tables["order_items"], tables["order_payments"], tables["order_reviews"]
    )
    products, customers = tables["products"], tables["customers"]

    return [
        Check("validity", "price > 0", "order_items", int((items["price"] <= 0).sum())),
        Check("validity", "freight_value >= 0", "order_items",
              int((items["freight_value"] < 0).sum())),
        Check("validity", "order_item_id >= 1", "order_items",
              int((items["order_item_id"] < 1).sum())),
        Check("validity", "payment_value >= 0", "order_payments",
              int((payments["payment_value"] < 0).sum())),
        Check("validity", "payment_installments >= 0", "order_payments",
              int((payments["payment_installments"] < 0).sum())),
        Check("validity", "review_score between 1 and 5", "order_reviews",
              int((~reviews["review_score"].between(1, 5)).sum())),
        Check("validity", "order_status is a recognised value", "orders",
              int((~tables["orders"]["order_status"].isin(ALL_STATUSES)).sum())),
        Check("validity", "customer_region is a recognised region", "customers",
              int((customers["customer_region"] == "Unknown").sum())),
        Check("validity", "product weight not negative", "products",
              int((products["product_weight_g"].dropna() < 0).sum())),
    ]


def _check_business_rules(tables: dict[str, pd.DataFrame]) -> list[Check]:
    orders, items, reviews = tables["orders"], tables["order_items"], tables["order_reviews"]

    purchase = orders.set_index("order_id")["order_purchase_timestamp"]
    delivered = orders["order_delivered_customer_date"]

    # A review cannot predate the order it reviews.
    review_purchase = reviews["order_id"].map(purchase)
    reviews_before_order = int(
        (reviews["review_creation_date"] < review_purchase.dt.normalize()).sum()
    )

    # An order that was actually picked and moved must have something in it.
    # Orders sitting in 'created' or 'invoiced' have not been fulfilled yet and
    # legitimately have no lines, as do cancelled and unavailable ones.
    fulfilled = orders[orders["order_status"].isin(FULFILMENT_STATUSES)]
    fulfilled_without_lines = int(
        (~fulfilled["order_id"].isin(set(items["order_id"]))).sum()
    )

    return [
        Check("business", "delivery date on or after purchase date", "orders",
              int((delivered < orders["order_purchase_timestamp"]).sum())),
        Check("business", "review created on or after the order", "order_reviews",
              reviews_before_order),
        Check("business", "fulfilled order has at least one line", "orders",
              fulfilled_without_lines,
              "created/invoiced/cancelled/unavailable orders legitimately have none"),
        Check("business", "one review per order", "order_reviews",
              int(reviews.duplicated(subset=["order_id"]).sum())),
    ]


def _check_coverage(tables: dict[str, pd.DataFrame]) -> list[Check]:
    """Facts about the source the analysis has to work around.

    Reported as passing checks with a detail string rather than as failures:
    they are properties of the dataset, not defects to repair.
    """
    orders, items = tables["orders"], tables["order_items"]
    customers, products = tables["customers"], tables["products"]
    payments, reviews = tables["order_payments"], tables["order_reviews"]

    delivered = orders[orders["order_status"] == "delivered"]
    with_date = delivered["order_delivered_customer_date"].notna().mean()
    unknown_category = (products["category_en"] == "unknown").mean()
    orders_with_review = reviews["order_id"].nunique() / max(len(orders), 1)
    orders_with_payment = payments["order_id"].nunique() / max(len(orders), 1)
    people = customers["customer_unique_id"].nunique()

    return [
        Check("coverage", "delivered orders with a delivery date", "orders", 0,
              f"{with_date:.2%} - the rest are excluded from delivery analysis"),
        Check("coverage", "products with a known category", "products", 0,
              f"{1 - unknown_category:.2%} - the rest are labelled 'unknown'"),
        Check("coverage", "orders with a review", "order_reviews", 0,
              f"{orders_with_review:.2%}"),
        Check("coverage", "orders with a payment record", "order_payments", 0,
              f"{orders_with_payment:.2%}"),
        Check("coverage", "customer_id resolves to fewer people", "customers", 0,
              f"{len(customers):,} order-level ids -> {people:,} unique customers"),
        Check("coverage", "order_items has no quantity column", "order_items", 0,
              f"{len(items):,} rows = {len(items):,} units sold"),
    ]


def format_report(checks: pd.DataFrame, cleaning_log: pd.DataFrame,
                  row_counts: pd.DataFrame) -> str:
    """Render the data-quality report as Markdown."""
    failed = checks[checks["status"] == "FAIL"]
    lines: list[str] = [
        "# Data Quality Report",
        "",
        "Generated by `python -m marketlens.data_processing`. Every number here is",
        "measured against the cleaned dataset, not asserted.",
        "",
        "The source is the Brazilian E-Commerce Public Dataset by Olist - real",
        "transaction data, so these defects are what the export actually contains",
        "rather than problems introduced on purpose.",
        "",
        "## Summary",
        "",
        f"- Validation checks run: **{len(checks)}**",
        f"- Passed: **{len(checks) - len(failed)}**",
        f"- Failed: **{len(failed)}**",
        "",
        "## Row counts: raw extract vs cleaned dataset",
        "",
        row_counts.to_markdown(index=False),
        "",
        "## Cleaning actions",
        "",
        "Rules that touched zero rows are omitted.",
        "",
        cleaning_log[cleaning_log["rows_affected"] > 0].to_markdown(index=False),
        "",
        "## Validation results",
        "",
        checks.to_markdown(index=False),
        "",
    ]
    if len(failed):
        lines += ["## Failing checks", "", failed.to_markdown(index=False), ""]
    return "\n".join(lines)
