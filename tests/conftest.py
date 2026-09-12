"""Shared pytest fixtures for the Olist dataset.

Two kinds of fixture live here:

``tiny_dataset``
    A four-order Olist dataset small enough that every KPI can be worked out by hand.
    Tests assert against those hand-computed values, so a broken calculation
    fails against arithmetic rather than against a previous run of the same
    (possibly wrong) code.

``full_dataset``
    The real Olist dataset, loaded from PostgreSQL or Parquet files.
"""

from __future__ import annotations

import pandas as pd
import pytest

from marketlens.config import PROCESSED_DIR
from marketlens.data_processing.database import LOAD_ORDER, database_available
from marketlens.data_processing.datasets import AnalysisData, TABLES


# ---------------------------------------------------------------------------
# Hand-computable fixture
# ---------------------------------------------------------------------------
#
# Four orders, one cancelled, three delivered (one late, two on-time).
# Unique customers: CU1 (placed O1, O2, O4) and CU2 (placed O3).
#
#   O1 (C1 / CU1, delivered): P1 @ 100.0, freight 20.0, review 5, on-time
#   O2 (C1 / CU1, delivered): P2 @ 200.0, freight 30.0, review 1, late (+5 days)
#   O3 (C2 / CU2, canceled):  P1 @ 100.0, freight 20.0, no review
#   O4 (C3 / CU1, delivered): P2 @ 200.0, freight 30.0, review 4, on-time
#
# Metrics:
#   total_orders = 4, completed_orders = 3, canceled_orders = 1
#   cancellation_rate = 0.25 (25%)
#   gross_revenue = 500.0, total_freight = 80.0
#   net_revenue = 500.0
#   avg_order_value = 500.0 / 3 = 166.6667
#   unique_customers = 2
#   revenue_per_customer = 250.0
#   late_delivery_rate = 1 / 3 = 0.3333
#   negative_review_rate = 1 / 3 = 0.3333
#   repeat_purchase_rate = 1 / 2 = 0.5 (CU1 repeated)

EXPECTED = {
    "total_orders": 4,
    "completed_orders": 3,
    "cancelled_orders": 1,
    "cancellation_rate": 0.25,
    "revenue_orders": 3,
    "gross_revenue": 500.0,
    "total_freight": 80.0,
    "net_revenue": 500.0,
    "avg_order_value": 500.0 / 3,
    "units": 3,
    "avg_items_per_order": 1.0,
    "unique_customers": 1,
    "revenue_per_customer": 500.0,
    "late_delivery_rate": 1 / 3,
    "negative_review_rate": 1 / 3,
    "repeat_purchase_rate": 1.0,
}


@pytest.fixture(scope="session")
def tiny_tables() -> dict[str, pd.DataFrame]:
    """The seven source tables for the hand-computable Olist dataset."""
    customers = pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "customer_unique_id": ["CU1", "CU2", "CU1"],
            "customer_city": ["sao paulo", "rio de janeiro", "sao paulo"],
            "customer_state": ["SP", "RJ", "SP"],
            "customer_region": ["Southeast", "Southeast", "Southeast"],
        }
    )
    sellers = pd.DataFrame(
        {
            "seller_id": ["S1", "S2"],
            "seller_city": ["sao paulo", "curitiba"],
            "seller_state": ["SP", "PR"],
            "seller_region": ["Southeast", "South"],
        }
    )
    products = pd.DataFrame(
        {
            "product_id": ["P1", "P2"],
            "category_en": ["health_beauty", "bed_bath_table"],
            "category_group": ["Health & Beauty", "Home & Living"],
            "product_weight_g": [500, 1200],
            "product_volume_cm3": [1000, 3000],
            "product_photos_qty": [2, 4],
        }
    )
    orders = pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3", "O4"],
            "customer_id": ["C1", "C1", "C2", "C3"],
            "order_status": ["delivered", "delivered", "canceled", "delivered"],
            "order_purchase_timestamp": pd.to_datetime(
                ["2017-02-01 10:00:00", "2017-03-01 10:00:00", "2017-03-15 10:00:00", "2017-04-01 10:00:00"]
            ),
            "order_approved_at": pd.to_datetime(
                ["2017-02-01 10:30:00", "2017-03-01 10:30:00", "2017-03-15 10:30:00", "2017-04-01 10:30:00"]
            ),
            "order_delivered_carrier_date": pd.to_datetime(
                ["2017-02-02 10:00:00", "2017-03-03 10:00:00", None, "2017-04-02 10:00:00"]
            ),
            "order_delivered_customer_date": pd.to_datetime(
                ["2017-02-05 10:00:00", "2017-03-15 10:00:00", None, "2017-04-05 10:00:00"]
            ),
            "order_estimated_delivery_date": pd.to_datetime(
                ["2017-02-10 00:00:00", "2017-03-10 00:00:00", "2017-03-25 00:00:00", "2017-04-10 00:00:00"]
            ),
        }
    )
    order_items = pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3", "O4"],
            "order_item_id": [1, 1, 1, 1],
            "product_id": ["P1", "P2", "P1", "P2"],
            "seller_id": ["S1", "S2", "S1", "S2"],
            "shipping_limit_date": pd.to_datetime(
                ["2017-02-06", "2017-03-06", "2017-03-20", "2017-04-06"]
            ),
            "price": [100.0, 200.0, 100.0, 200.0],
            "freight_value": [20.0, 30.0, 20.0, 30.0],
        }
    )
    order_payments = pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3", "O4"],
            "payment_sequential": [1, 1, 1, 1],
            "payment_type": ["credit_card", "credit_card", "boleto", "voucher"],
            "payment_installments": [1, 3, 1, 1],
            "payment_value": [120.0, 230.0, 120.0, 230.0],
        }
    )
    order_reviews = pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O4"],
            "review_id": ["R1", "R2", "R4"],
            "review_score": [5, 1, 4],
            "review_comment_title": [None, "Delayed", "Good"],
            "review_comment_message": ["Great", "Late delivery", "Satisfied"],
            "review_creation_date": pd.to_datetime(["2017-02-06", "2017-03-16", "2017-04-06"]),
            "review_answer_timestamp": pd.to_datetime(["2017-02-07", "2017-03-17", "2017-04-07"]),
        }
    )
    return {
        "customers": customers,
        "sellers": sellers,
        "products": products,
        "orders": orders,
        "order_items": order_items,
        "order_payments": order_payments,
        "order_reviews": order_reviews,
    }


@pytest.fixture(scope="session")
def tiny_dataset(tiny_tables) -> AnalysisData:
    return AnalysisData(tiny_tables, apply_window=False)


@pytest.fixture(scope="session")
def expected() -> dict:
    return EXPECTED


# ---------------------------------------------------------------------------
# The real dataset
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def processed_tables() -> dict[str, pd.DataFrame]:
    missing = [t for t in TABLES if not (PROCESSED_DIR / f"{t}.parquet").exists()]
    if missing:
        pytest.skip(
            "Processed dataset not built. Run `python -m marketlens.data_processing` first."
        )
    return {t: pd.read_parquet(PROCESSED_DIR / f"{t}.parquet") for t in TABLES}


@pytest.fixture(scope="session")
def full_dataset(processed_tables) -> AnalysisData:
    from marketlens.data_processing.datasets import load_tables

    return AnalysisData(load_tables("parquet"))


@pytest.fixture(scope="session")
def db_engine():
    """A live PostgreSQL engine, or skip the test if there is not one."""
    if not database_available():
        pytest.skip("PostgreSQL is not reachable; skipping database tests.")
    from marketlens.data_processing.database import get_engine

    return get_engine()

