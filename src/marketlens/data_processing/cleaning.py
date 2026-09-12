"""Cleaning the raw Olist extract into an analysis-ready dataset.

Unlike a generated dataset, these defects were not put here on purpose - they
are what the real export actually contains. Each rule below exists because
something in the source breaks in that specific way, and each records how many
rows it touched so the data-quality report describes what happened rather than
what was supposed to happen.

The substantive decisions, all of which change downstream numbers:

* ``customer_unique_id`` is carried onto everything customer-level.
  ``customer_id`` is issued per order, so keying customer analysis on it
  reports a 0.00% repeat purchase rate instead of 3.12%.

* Products with no category (610 of 32,951) are labelled ``unknown`` rather
  than dropped. They carry real revenue, and dropping them would silently
  reduce every revenue total.

* Duplicate reviews are resolved to one per order, keeping the earliest, and
  the count is reported. The raw mirror carries an earlier Olist snapshot with
  duplicate review ids and multiple reviews per order.

* Orders with no order_items rows are kept, not dropped. 775 of them exist and
  they are almost entirely ``unavailable`` or ``canceled`` - the fact that an
  unfulfillable order has no line items is information, not corruption. They
  carry no revenue by construction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from marketlens.config import ALL_STATUSES
from marketlens.data_ingestion.reference_data import (
    MISSING_CATEGORY_TRANSLATIONS,
    UNKNOWN_CATEGORY,
    group_for_category,
    region_for_state,
)

logger = logging.getLogger(__name__)

#: Statuses that mean the order was actually picked and moved. An order in one
#: of these must have line items; an order in 'created', 'invoiced', 'canceled'
#: or 'unavailable' legitimately may not.
FULFILMENT_STATUSES: tuple[str, ...] = ("delivered", "shipped", "processing", "approved")


@dataclass
class CleaningLog:
    """Row-level record of every cleaning action taken."""

    rows: list[dict] = field(default_factory=list)

    def add(self, table: str, rule: str, action: str, rows_affected: int) -> None:
        self.rows.append(
            {"table": table, "rule": rule, "action": action,
             "rows_affected": int(rows_affected)}
        )
        if rows_affected:
            logger.info("  %-15s %-44s %-30s %7s",
                        table, rule, action, f"{rows_affected:,}")

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["table", "rule", "action", "rows_affected"])


@dataclass
class CleaningResult:
    tables: dict[str, pd.DataFrame]
    log: pd.DataFrame
    row_counts: pd.DataFrame


def clean_dataset(raw: dict[str, pd.DataFrame]) -> CleaningResult:
    """Clean all seven source tables, respecting their dependency order."""
    log = CleaningLog()
    before = {name: len(df) for name, df in raw.items()}

    customers = clean_customers(raw["customers"], log)
    sellers = clean_sellers(raw["sellers"], log)
    products = clean_products(raw["products"], raw["category_translation"], log)
    orders = clean_orders(raw["orders"], customers, log)
    order_items = clean_order_items(raw["order_items"], orders, products, sellers, log)

    # An order that claims to have been fulfilled must have something in it.
    # Orders that never reached fulfilment - cancelled, unavailable, created,
    # invoiced - legitimately have no lines, and 774 of them do; those are kept.
    # Exactly one order claims to have shipped with nothing on it, which cannot
    # be interpreted, so it goes.
    fulfilled = orders["order_status"].isin(FULFILMENT_STATUSES)
    has_lines = orders["order_id"].isin(set(order_items["order_id"]))
    impossible = fulfilled & ~has_lines
    log.add("orders", "claims fulfilment but has no line items", "dropped", impossible.sum())
    orders = orders[~impossible].reset_index(drop=True)
    order_items = order_items[order_items["order_id"].isin(set(orders["order_id"]))]

    order_payments = clean_order_payments(raw["order_payments"], orders, log)
    order_reviews = clean_order_reviews(raw["order_reviews"], orders, log)

    tables = {
        "customers": customers,
        "sellers": sellers,
        "products": products,
        "orders": orders,
        "order_items": order_items,
        "order_payments": order_payments,
        "order_reviews": order_reviews,
    }
    row_counts = pd.DataFrame(
        {
            "table": list(tables),
            "raw_rows": [before.get(name, 0) for name in tables],
            "clean_rows": [len(tables[name]) for name in tables],
        }
    )
    row_counts["rows_removed"] = row_counts["raw_rows"] - row_counts["clean_rows"]
    return CleaningResult(tables=tables, log=log.to_frame(), row_counts=row_counts)


# ---------------------------------------------------------------------------
# customers
# ---------------------------------------------------------------------------


def clean_customers(raw: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    df = raw.copy()

    duplicates = df.duplicated(subset=["customer_id"]).sum()
    df = df.drop_duplicates(subset=["customer_id"], keep="first")
    log.add("customers", "duplicate customer_id", "dropped", duplicates)

    # City is free text and arrives with inconsistent casing and accents.
    original_city = df["customer_city"].copy()
    df["customer_city"] = df["customer_city"].astype(str).str.strip().str.title()
    log.add("customers", "city casing/whitespace", "normalised",
            (df["customer_city"] != original_city).sum())

    df["customer_state"] = df["customer_state"].astype(str).str.strip().str.upper()
    df["customer_zip_code_prefix"] = (
        df["customer_zip_code_prefix"].astype(str).str.strip().str.zfill(5)
    )

    # Region is not in the source at all; it is derived from the state code.
    df["customer_region"] = df["customer_state"].map(region_for_state)
    unmapped = (df["customer_region"] == "Unknown").sum()
    log.add("customers", "state not in the IBGE region map", "region set to 'Unknown'", unmapped)

    log.add("customers", "customer_unique_id carried through",
            "retained for customer-level analysis", df["customer_unique_id"].nunique())

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# sellers
# ---------------------------------------------------------------------------


def clean_sellers(raw: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    df = raw.copy()

    duplicates = df.duplicated(subset=["seller_id"]).sum()
    df = df.drop_duplicates(subset=["seller_id"], keep="first")
    log.add("sellers", "duplicate seller_id", "dropped", duplicates)

    original_city = df["seller_city"].copy()
    df["seller_city"] = df["seller_city"].astype(str).str.strip().str.title()
    log.add("sellers", "city casing/whitespace", "normalised",
            (df["seller_city"] != original_city).sum())

    df["seller_state"] = df["seller_state"].astype(str).str.strip().str.upper()
    df["seller_zip_code_prefix"] = (
        df["seller_zip_code_prefix"].astype(str).str.strip().str.zfill(5)
    )
    df["seller_region"] = df["seller_state"].map(region_for_state)
    log.add("sellers", "state not in the IBGE region map", "region set to 'Unknown'",
            (df["seller_region"] == "Unknown").sum())

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------


def clean_products(raw: pd.DataFrame, translation: pd.DataFrame,
                   log: CleaningLog) -> pd.DataFrame:
    df = raw.copy()

    duplicates = df.duplicated(subset=["product_id"]).sum()
    df = df.drop_duplicates(subset=["product_id"], keep="first")
    log.add("products", "duplicate product_id", "dropped", duplicates)

    # Olist ships two misspelled column names in this table.
    df = df.rename(columns={
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    })
    log.add("products", "misspelled source columns (lenght)", "renamed to length", len(df))

    # Translate Portuguese categories, filling the two the translation file
    # omits rather than losing them.
    pt_to_en = dict(zip(translation["product_category_name"],
                        translation["product_category_name_english"]))
    pt_to_en.update(MISSING_CATEGORY_TRANSLATIONS)

    df["category_pt"] = df["product_category_name"]
    df["category_en"] = df["category_pt"].map(pt_to_en)

    filled = df["category_pt"].notna() & df["category_en"].isna()
    log.add("products", "category missing from the translation file",
            "filled from the reference map", filled.sum())
    df.loc[filled, "category_en"] = df.loc[filled, "category_pt"]

    # 610 products have no category at all. They carry real revenue, so they
    # are labelled rather than dropped.
    no_category = df["category_en"].isna().sum()
    df["category_en"] = df["category_en"].fillna(UNKNOWN_CATEGORY)
    log.add("products", "no category in the source",
            f"labelled '{UNKNOWN_CATEGORY}' (kept, not dropped)", no_category)

    df["category_group"] = df["category_en"].map(group_for_category)

    numeric = ["product_name_length", "product_description_length", "product_photos_qty",
               "product_weight_g", "product_length_cm", "product_height_cm",
               "product_width_cm"]
    for column in numeric:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Two products have no dimensions. Volume is used only in the freight
    # analysis, which reports coverage rather than imputing.
    dims = ["product_length_cm", "product_height_cm", "product_width_cm"]
    df["product_volume_cm3"] = (
        df[dims[0]] * df[dims[1]] * df[dims[2]]
    ).round()
    log.add("products", "missing dimensions", "volume left null (not imputed)",
            df["product_volume_cm3"].isna().sum())

    # A zero or negative dimension would make volume meaningless.
    implausible = ((df[dims] <= 0).any(axis=1)).sum()
    df.loc[(df[dims] <= 0).any(axis=1), "product_volume_cm3"] = np.nan
    log.add("products", "non-positive dimensions", "volume set to null", implausible)

    keep = ["product_id", "category_pt", "category_en", "category_group",
            "product_name_length", "product_description_length", "product_photos_qty",
            "product_weight_g", "product_length_cm", "product_height_cm",
            "product_width_cm", "product_volume_cm3"]
    df = df[keep]
    for column in ["product_name_length", "product_description_length",
                   "product_photos_qty", "product_weight_g", "product_length_cm",
                   "product_height_cm", "product_width_cm", "product_volume_cm3"]:
        df[column] = df[column].astype("Int64")

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# orders
# ---------------------------------------------------------------------------

ORDER_DATE_COLUMNS = [
    "order_purchase_timestamp", "order_approved_at",
    "order_delivered_carrier_date", "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def clean_orders(raw: pd.DataFrame, customers: pd.DataFrame,
                 log: CleaningLog) -> pd.DataFrame:
    df = raw.copy()

    duplicates = df.duplicated(subset=["order_id"]).sum()
    df = df.drop_duplicates(subset=["order_id"], keep="first")
    log.add("orders", "duplicate order_id", "dropped", duplicates)

    for column in ORDER_DATE_COLUMNS:
        df[column] = pd.to_datetime(df[column], errors="coerce")

    bad_purchase = df["order_purchase_timestamp"].isna().sum()
    df = df[df["order_purchase_timestamp"].notna()]
    log.add("orders", "unparseable order_purchase_timestamp", "dropped", bad_purchase)

    unknown_status = (~df["order_status"].isin(ALL_STATUSES)).sum()
    df = df[df["order_status"].isin(ALL_STATUSES)]
    log.add("orders", "unrecognised order_status", "dropped", unknown_status)

    orphans = (~df["customer_id"].isin(set(customers["customer_id"]))).sum()
    df = df[df["customer_id"].isin(set(customers["customer_id"]))]
    log.add("orders", "customer_id not in customers", "dropped", orphans)

    # A delivered order should have a delivery date. 2,965 do not; that is a
    # gap in the source, and the delivery analysis excludes them rather than
    # guessing a date.
    delivered_no_date = (
        (df["order_status"] == "delivered") & df["order_delivered_customer_date"].isna()
    ).sum()
    log.add("orders", "delivered but no delivery date",
            "left null (excluded from delivery analysis)", delivered_no_date)

    log.add("orders", "no approval timestamp", "left null",
            df["order_approved_at"].isna().sum())

    # A delivery date before the purchase date would be impossible.
    impossible = (df["order_delivered_customer_date"] < df["order_purchase_timestamp"]).sum()
    df.loc[
        df["order_delivered_customer_date"] < df["order_purchase_timestamp"],
        "order_delivered_customer_date",
    ] = pd.NaT
    log.add("orders", "delivery date before purchase date", "set to null", impossible)

    return df.sort_values("order_purchase_timestamp").reset_index(drop=True)


# ---------------------------------------------------------------------------
# order_items
# ---------------------------------------------------------------------------


def clean_order_items(raw: pd.DataFrame, orders: pd.DataFrame, products: pd.DataFrame,
                      sellers: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    df = raw.copy()

    exact = df.duplicated().sum()
    df = df.drop_duplicates()
    log.add("order_items", "fully duplicated rows", "dropped", exact)

    dup_key = df.duplicated(subset=["order_id", "order_item_id"]).sum()
    df = df.drop_duplicates(subset=["order_id", "order_item_id"], keep="first")
    log.add("order_items", "duplicate (order_id, order_item_id)", "kept first", dup_key)

    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors="coerce")
    for column in ("price", "freight_value"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    invalid_price = (~(df["price"] > 0)).sum()
    df = df[df["price"] > 0]
    log.add("order_items", "price <= 0 or null", "dropped", invalid_price)

    negative_freight = (df["freight_value"] < 0).sum()
    df = df[~(df["freight_value"] < 0)]
    log.add("order_items", "negative freight_value", "dropped", negative_freight)

    null_freight = df["freight_value"].isna().sum()
    df["freight_value"] = df["freight_value"].fillna(0.0)
    log.add("order_items", "null freight_value", "set to 0", null_freight)

    for name, keys, reference in (
        ("order_id not in orders", "order_id", set(orders["order_id"])),
        ("product_id not in products", "product_id", set(products["product_id"])),
        ("seller_id not in sellers", "seller_id", set(sellers["seller_id"])),
    ):
        orphans = (~df[keys].isin(reference)).sum()
        df = df[df[keys].isin(reference)]
        log.add("order_items", name, "dropped", orphans)

    df["order_item_id"] = df["order_item_id"].astype(int)
    return df.sort_values(["order_id", "order_item_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# order_payments
# ---------------------------------------------------------------------------


def clean_order_payments(raw: pd.DataFrame, orders: pd.DataFrame,
                         log: CleaningLog) -> pd.DataFrame:
    df = raw.copy()

    exact = df.duplicated().sum()
    df = df.drop_duplicates()
    log.add("order_payments", "fully duplicated rows", "dropped", exact)

    dup_key = df.duplicated(subset=["order_id", "payment_sequential"]).sum()
    df = df.drop_duplicates(subset=["order_id", "payment_sequential"], keep="first")
    log.add("order_payments", "duplicate (order_id, payment_sequential)", "kept first", dup_key)

    for column in ("payment_sequential", "payment_installments", "payment_value"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    negative = (df["payment_value"] < 0).sum()
    df = df[~(df["payment_value"] < 0)]
    log.add("order_payments", "negative payment_value", "dropped", negative)

    orphans = (~df["order_id"].isin(set(orders["order_id"]))).sum()
    df = df[df["order_id"].isin(set(orders["order_id"]))]
    log.add("order_payments", "order_id not in orders", "dropped", orphans)

    # "not_defined" is Olist's placeholder for a payment type it could not
    # record. Kept as a labelled category rather than dropped or guessed.
    not_defined = (df["payment_type"] == "not_defined").sum()
    log.add("order_payments", "payment_type 'not_defined'", "kept as its own category",
            not_defined)

    df["payment_sequential"] = df["payment_sequential"].astype(int)
    df["payment_installments"] = df["payment_installments"].fillna(0).astype(int)
    return df.sort_values(["order_id", "payment_sequential"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# order_reviews
# ---------------------------------------------------------------------------


def clean_order_reviews(raw: pd.DataFrame, orders: pd.DataFrame,
                        log: CleaningLog) -> pd.DataFrame:
    df = raw.copy()

    exact = df.duplicated().sum()
    df = df.drop_duplicates()
    log.add("order_reviews", "fully duplicated rows", "dropped", exact)

    for column in ("review_creation_date", "review_answer_timestamp"):
        df[column] = pd.to_datetime(df[column], errors="coerce")

    df["review_score"] = pd.to_numeric(df["review_score"], errors="coerce")
    invalid = (~df["review_score"].between(1, 5)).sum()
    df = df[df["review_score"].between(1, 5)]
    log.add("order_reviews", "review_score outside 1-5", "dropped", invalid)

    bad_date = df["review_creation_date"].isna().sum()
    df = df[df["review_creation_date"].notna()]
    log.add("order_reviews", "unparseable review_creation_date", "dropped", bad_date)

    orphans = (~df["order_id"].isin(set(orders["order_id"]))).sum()
    df = df[df["order_id"].isin(set(orders["order_id"]))]
    log.add("order_reviews", "order_id not in orders", "dropped", orphans)

    # A review cannot precede the order it reviews. 65 rows do, and 58 of them
    # belong to cancelled orders - most likely a review carried over from an
    # earlier attempt. They cannot be attributed to this order, so they go.
    purchase = orders.set_index("order_id")["order_purchase_timestamp"]
    order_date = df["order_id"].map(purchase).dt.normalize()
    backdated = (df["review_creation_date"] < order_date).sum()
    df = df[~(df["review_creation_date"] < order_date)]
    log.add("order_reviews", "review dated before its order", "dropped", backdated)

    # The same review_id appears against more than one order in this snapshot.
    dup_review_id = df.duplicated(subset=["review_id"]).sum()
    log.add("order_reviews", "review_id appears more than once",
            "kept (order_id is the analysis key)", dup_review_id)

    # Several orders carry more than one review. Keep the earliest, which is
    # the customer's first reaction to the delivery, and report the rest.
    df = df.sort_values(["order_id", "review_creation_date"])
    multiple = df.duplicated(subset=["order_id"]).sum()
    df = df.drop_duplicates(subset=["order_id"], keep="first")
    log.add("order_reviews", "more than one review for an order",
            "kept the earliest", multiple)

    df["review_score"] = df["review_score"].astype(int)
    return df.sort_values("review_creation_date").reset_index(drop=True)
