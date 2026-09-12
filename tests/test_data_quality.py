"""Data-quality tests against the cleaned Olist dataset.

These are the checks that catch a bad extract before anyone builds a number on it:
schema, keys, nulls, referential integrity, value ranges and business rules.
"""

from __future__ import annotations

import pandas as pd
import pytest

from marketlens.config import ALL_STATUSES
from marketlens.data_processing.validation import (
    EXPECTED_COLUMNS,
    NOT_NULL,
    PRIMARY_KEYS,
    validate_dataset,
)


# --- the validation suite as a whole --------------------------------------


def test_every_validation_check_passes(processed_tables):
    checks = validate_dataset(processed_tables)
    failures = checks[checks["status"] == "FAIL"]
    assert failures.empty, f"Failing checks:\n{failures.to_string(index=False)}"


def test_validation_covers_all_tables(processed_tables):
    checks = validate_dataset(processed_tables)
    assert set(checks["scope"]) >= set(EXPECTED_COLUMNS)
    assert len(checks) >= 50


# --- schema ---------------------------------------------------------------


@pytest.mark.parametrize("table", sorted(EXPECTED_COLUMNS))
def test_expected_columns_present(processed_tables, table):
    missing = EXPECTED_COLUMNS[table] - set(processed_tables[table].columns)
    assert not missing, f"{table} is missing {sorted(missing)}"


@pytest.mark.parametrize("table", sorted(PRIMARY_KEYS))
def test_primary_keys_are_unique(processed_tables, table):
    keys = PRIMARY_KEYS[table]
    duplicates = processed_tables[table].duplicated(subset=keys).sum()
    assert duplicates == 0, f"{table} has {duplicates} duplicate {keys}"


@pytest.mark.parametrize("table", sorted(NOT_NULL))
def test_required_columns_have_no_nulls(processed_tables, table):
    for column in NOT_NULL[table]:
        nulls = processed_tables[table][column].isna().sum()
        assert nulls == 0, f"{table}.{column} has {nulls} nulls"


# --- referential integrity ------------------------------------------------


def test_no_orphan_orders(processed_tables):
    customers = set(processed_tables["customers"]["customer_id"])
    orphans = ~processed_tables["orders"]["customer_id"].isin(customers)
    assert orphans.sum() == 0


def test_no_orphan_order_items(processed_tables):
    orders = set(processed_tables["orders"]["order_id"])
    products = set(processed_tables["products"]["product_id"])
    sellers = set(processed_tables["sellers"]["seller_id"])
    items = processed_tables["order_items"]
    assert (~items["order_id"].isin(orders)).sum() == 0
    assert (~items["product_id"].isin(products)).sum() == 0
    assert (~items["seller_id"].isin(sellers)).sum() == 0


def test_no_orphan_payments(processed_tables):
    orders = set(processed_tables["orders"]["order_id"])
    payments = processed_tables["order_payments"]
    assert (~payments["order_id"].isin(orders)).sum() == 0


def test_no_orphan_reviews(processed_tables):
    orders = set(processed_tables["orders"]["order_id"])
    reviews = processed_tables["order_reviews"]
    assert (~reviews["order_id"].isin(orders)).sum() == 0


# --- value ranges ---------------------------------------------------------


def test_prices_and_freight_are_non_negative(processed_tables):
    items = processed_tables["order_items"]
    assert (items["price"] > 0).all()
    assert (items["freight_value"] >= 0).all()


def test_order_status_values_are_recognised(processed_tables):
    assert set(processed_tables["orders"]["order_status"]) <= set(ALL_STATUSES)


# --- scale ----------------------------------------------------------------


def test_dataset_meets_its_documented_scale(processed_tables):
    """Assert against the Olist dataset scale."""
    assert len(processed_tables["orders"]) >= 90_000
    assert len(processed_tables["customers"]) >= 90_000
    assert len(processed_tables["products"]) >= 30_000
    assert len(processed_tables["sellers"]) >= 3_000
    assert processed_tables["customers"]["customer_state"].nunique() >= 25
