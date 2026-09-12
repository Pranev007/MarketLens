"""Data loading and filtering for the dashboard.

Loading and joining the dataset takes a few seconds, so it happens once and is
cached for the session. Filtering is cached separately, keyed on the filter
values, so moving a control does not re-read the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import streamlit as st

from marketlens.analytics import customers as customer_analytics
from marketlens.config import ANALYSIS_END, ANALYSIS_START
from marketlens.data_processing.datasets import AnalysisData, load_tables, resolve_source


@dataclass(frozen=True)
class Filters:
    """The sidebar filter state.

    Frozen and hashable so it can be used as a Streamlit cache key.
    """

    start_date: date
    end_date: date
    category_groups: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    segments: tuple[str, ...] = ()
    payment_types: tuple[str, ...] = ()
    delivery_outcome: str = "All"      # All | On time | Late
    review_scores: tuple[int, ...] = ()

    @property
    def is_active(self) -> bool:
        """True when anything other than the full date range is selected."""
        return bool(
            self.category_groups or self.regions or self.states or self.segments
            or self.payment_types or self.review_scores
            or self.delivery_outcome != "All"
        )


@dataclass
class DashboardData:
    """Everything a page needs: the filtered dataset plus its context."""

    data: AnalysisData
    full: AnalysisData
    filters: Filters
    segment_lookup: pd.DataFrame = field(default_factory=pd.DataFrame)


@st.cache_resource(show_spinner="Loading the Olist dataset...")
def load_full_dataset() -> AnalysisData:
    """Load and join the dataset once per session."""
    return AnalysisData(load_tables())


@st.cache_data(show_spinner=False)
def data_source_label() -> str:
    return "PostgreSQL" if resolve_source() == "postgres" else "processed files (Parquet)"


@st.cache_data(show_spinner=False)
def customer_segment_lookup() -> pd.DataFrame:
    """Map every purchasing customer to their RFM segment.

    Computed on the unfiltered dataset on purpose: a customer's segment is a
    property of their whole history, so it must not change when the dashboard
    date range is narrowed.
    """
    full = load_full_dataset()
    rfm = customer_analytics.rfm_segments(full)
    return rfm[["customer_unique_id", "segment", "recency_days", "frequency", "monetary"]]


def filter_options() -> dict[str, list]:
    """The values available in each filter control."""
    full = load_full_dataset()
    segments = customer_segment_lookup()
    return {
        "category_groups": sorted(full.products["category_group"].unique()),
        "regions": sorted(full.customers["customer_region"].unique()),
        "states": sorted(full.customers["customer_state"].unique()),
        "segments": sorted(segments["segment"].unique()),
        "payment_types": sorted(full.order_payments["payment_type"].unique()),
        "review_scores": [1, 2, 3, 4, 5],
    }


def date_bounds() -> tuple[date, date]:
    full = load_full_dataset()
    return (
        full.orders["order_purchase_timestamp"].min().date(),
        full.orders["order_purchase_timestamp"].max().date(),
    )


@st.cache_data(show_spinner="Applying filters...")
def apply_filters(filters: Filters) -> AnalysisData:
    """Return the dataset narrowed to the selected filters."""
    full = load_full_dataset()
    lines = full.lines

    mask = (
        lines["order_purchase_timestamp"] >= pd.Timestamp(filters.start_date)
    ) & (
        lines["order_purchase_timestamp"]
        < pd.Timestamp(filters.end_date) + pd.Timedelta(days=1)
    )

    if filters.category_groups:
        mask &= lines["category_group"].isin(filters.category_groups)
    if filters.regions:
        mask &= lines["customer_region"].isin(filters.regions)
    if filters.states:
        mask &= lines["customer_state"].isin(filters.states)
    if filters.review_scores:
        mask &= lines["review_score"].isin(filters.review_scores)
    if filters.delivery_outcome == "Late":
        mask &= lines["is_late"].fillna(False).astype(bool)
    elif filters.delivery_outcome == "On time":
        mask &= lines["is_late"].notna() & ~lines["is_late"].fillna(True).astype(bool)
    if filters.payment_types:
        payments = full.order_payments
        keep = set(
            payments.loc[payments["payment_type"].isin(filters.payment_types), "order_id"]
        )
        mask &= lines["order_id"].isin(keep)
    if filters.segments:
        segments = customer_segment_lookup()
        keep = set(
            segments.loc[segments["segment"].isin(filters.segments), "customer_unique_id"]
        )
        mask &= lines["customer_unique_id"].isin(keep)

    return full.subset(lines[mask], extra_order_ids=_lineless_order_ids(full, filters))


def _lineless_order_ids(full: AnalysisData, filters: Filters) -> set[str]:
    """Orders with no line items that still belong in the current selection.

    Every filter above selects on order LINES, so an order carrying no items
    cannot survive any of them - and 739 orders in the window are line-less,
    including all 602 'unavailable' ones. Left out, the dashboard reports zero
    unavailable orders while the KPI report reports 602 for the same window.

    A line-less order has no category, no seller and no delivery, so those
    filters legitimately exclude it. The rest are knowable from the order and
    its customer, and are applied here.
    """
    if filters.category_groups or filters.delivery_outcome != "All":
        return set()

    summary = full.order_summary
    candidates = summary[summary["items"] == 0]
    if candidates.empty:
        return set()

    keep = (
        candidates["order_purchase_timestamp"] >= pd.Timestamp(filters.start_date)
    ) & (
        candidates["order_purchase_timestamp"]
        < pd.Timestamp(filters.end_date) + pd.Timedelta(days=1)
    )
    if filters.regions:
        keep &= candidates["customer_region"].isin(filters.regions)
    if filters.states:
        keep &= candidates["customer_state"].isin(filters.states)
    if filters.review_scores:
        keep &= candidates["review_score"].isin(filters.review_scores)
    if filters.payment_types:
        payments = full.order_payments
        paid_by = set(
            payments.loc[payments["payment_type"].isin(filters.payment_types), "order_id"]
        )
        keep &= candidates["order_id"].isin(paid_by)
    if filters.segments:
        segments = customer_segment_lookup()
        in_segment = set(
            segments.loc[segments["segment"].isin(filters.segments), "customer_unique_id"]
        )
        keep &= candidates["customer_unique_id"].isin(in_segment)

    return set(candidates.loc[keep, "order_id"])


@st.cache_data(show_spinner="Recomputing insights for the current selection...")
def cached_insights(filters: Filters):
    """Generate the business insights for a filter selection, once.

    Insight generation runs the full analytics stack, which takes several
    seconds. Caching on the filter values means it happens once per selection
    rather than on every rerun.
    """
    from marketlens.analytics.insights import generate_insights

    return generate_insights(apply_filters(filters))


@st.cache_data(show_spinner=False)
def cached_kpis(filters: Filters):
    """Headline KPIs for a filter selection."""
    from marketlens.analytics.kpis import calculate_headline_kpis

    return calculate_headline_kpis(apply_filters(filters))


def render_sidebar() -> Filters:
    """Draw the sidebar filters and return the resulting filter state."""
    options = filter_options()
    min_date, max_date = date_bounds()
    default_start = max(min_date, ANALYSIS_START)
    default_end = min(max_date, ANALYSIS_END)

    st.sidebar.markdown("## Filters")
    st.sidebar.caption("Filters apply to every page.")

    selected_range = st.sidebar.date_input(
        "Order date range",
        value=(default_start, default_end),
        min_value=min_date,
        max_value=max_date,
        help=(
            "Defaults to the reporting window (Jan 2017 - Aug 2018). The months "
            "outside it contain a handful of orders each and distort every trend."
        ),
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date, end_date = default_start, default_end

    categories = st.sidebar.multiselect("Category group", options["category_groups"])
    regions = st.sidebar.multiselect("Customer region", options["regions"])

    # Only offer states inside the selected regions, so the two cannot conflict.
    state_options = options["states"]
    if regions:
        full = load_full_dataset()
        state_options = sorted(
            full.customers.loc[
                full.customers["customer_region"].isin(regions), "customer_state"
            ].unique()
        )
    states = st.sidebar.multiselect("Customer state", state_options)

    delivery_outcome = st.sidebar.radio(
        "Delivery outcome", ["All", "On time", "Late"], horizontal=True,
        help="Late means delivered after the date promised to the customer at checkout.",
    )
    review_scores = st.sidebar.multiselect("Review score", options["review_scores"])
    segments = st.sidebar.multiselect("Customer segment (RFM)", options["segments"])
    payment_types = st.sidebar.multiselect("Payment type", options["payment_types"])

    if st.sidebar.button("Reset filters", use_container_width=True):
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(f"Reading from **{data_source_label()}**")
    st.sidebar.caption(
        "Source: Brazilian E-Commerce Public Dataset by Olist (CC BY-NC-SA 4.0). "
        "Real marketplace transactions, 2016-2018."
    )

    return Filters(
        start_date=start_date,
        end_date=end_date,
        category_groups=tuple(categories),
        regions=tuple(regions),
        states=tuple(states),
        segments=tuple(segments),
        payment_types=tuple(payment_types),
        delivery_outcome=delivery_outcome,
        review_scores=tuple(int(s) for s in review_scores),
    )


def get_dashboard_data(filters: Filters) -> DashboardData:
    """Assemble everything the pages need."""
    return DashboardData(
        data=apply_filters(filters),
        full=load_full_dataset(),
        filters=filters,
        segment_lookup=customer_segment_lookup(),
    )
