"""Page 4 - Customer analytics.

Everything on this page keys on ``customer_unique_id``. Olist issues a new
``customer_id`` for every order, and grouping on it reports a repeat purchase
rate of exactly 0.00% - the defining trap of this dataset.
"""

from __future__ import annotations

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.data_access import DashboardData
from dashboard.theme import (
    ACCENT,
    ACCENT_LIGHT,
    MUTED,
    WARN,
    money,
    percent,
    plotly_layout,
)
from marketlens.analytics import cohorts, customers as customer_analytics


def render(dashboard: DashboardData) -> None:
    data = dashboard.data
    st.title("Customer analytics")

    if data.lines.empty:
        st.warning("No orders match the current filters.")
        return

    st.caption(
        "Who buys, how often, what they are worth - and the answer to whether this "
        "marketplace has a retention problem or simply a low-frequency category."
    )

    _repeat_headline(data)
    st.divider()

    left, right = st.columns(2)
    with left:
        _frequency(data)
    with right:
        _concentration(data)

    st.divider()
    _segments(data)

    st.divider()
    _cohorts(data, dashboard)


def _repeat_headline(data) -> None:
    """The customer_id trap, shown rather than described."""
    repeat = customer_analytics.repeat_behaviour(data)
    if not repeat:
        return

    row = st.columns(4)
    row[0].metric("Unique customers", f"{repeat['unique_customers']:,}")
    row[1].metric("Customers who ordered twice", f"{repeat['repeat_customers']:,}")
    row[2].metric("Repeat purchase rate", percent(repeat["repeat_purchase_rate"], 2))
    row[3].metric(
        "Revenue from repeat buyers",
        percent(repeat["pct_revenue_from_repeat_customers"], 2),
    )

    st.info(
        f"**The join that decides this number.** Olist issues a `customer_id` per "
        f"*order*: {repeat['customer_accounts']:,} account ids resolve to "
        f"{repeat['unique_customers']:,} people. Keyed correctly on "
        f"`customer_unique_id` the repeat rate is "
        f"**{percent(repeat['repeat_purchase_rate'], 2)}**; keyed on `customer_id` it "
        f"comes out at **{percent(repeat['repeat_rate_if_keyed_on_customer_id'], 2)}** - "
        "a join artefact that reads as a catastrophic business failure.",
        icon=":material/key:",
    )


def _frequency(data) -> None:
    st.subheader("Purchase frequency")
    bands = customer_analytics.purchase_frequency_distribution(data)

    figure = go.Figure()
    labels = bands["frequency_band"].astype(str)
    figure.add_bar(
        x=labels, y=bands["pct_of_customers"], name="Share of customers",
        marker_color=MUTED,
        hovertemplate="%{x}<br>Customers: %{y:.1%}<extra></extra>",
    )
    figure.add_bar(
        x=labels, y=bands["pct_of_revenue"], name="Share of revenue",
        marker_color=ACCENT,
        hovertemplate="%{x}<br>Revenue: %{y:.1%}<extra></extra>",
    )
    figure.update_layout(barmode="group")
    figure.update_yaxes(title="Share", tickformat=".0%")
    st.plotly_chart(plotly_layout(figure, height=360), use_container_width=True)

    one_order = bands[bands["frequency_band"].astype(str) == "1 order"]
    if not one_order.empty:
        st.markdown(
            f"<span class='caption-note'>"
            f"<b>{percent(float(one_order['pct_of_customers'].iloc[0]))}</b> of "
            f"customers bought exactly once, and they account for "
            f"<b>{percent(float(one_order['pct_of_revenue'].iloc[0]))}</b> of "
            "revenue.</span>",
            unsafe_allow_html=True,
        )


def _concentration(data) -> None:
    st.subheader("Revenue concentration")
    customers = customer_analytics.revenue_concentration(data)

    figure = go.Figure()
    figure.add_scatter(
        x=customers["top_n_percent"], y=customers["cumulative_pct_of_revenue"],
        mode="lines+markers", name="Customers",
        line=dict(color=ACCENT, width=2.5),
        hovertemplate="Top %{x}% of customers<br>%{y:.1%} of revenue<extra></extra>",
    )
    figure.add_scatter(
        x=[0, 100], y=[0, 1], mode="lines", name="Perfectly even",
        line=dict(color=MUTED, width=1, dash="dash"), hoverinfo="skip",
    )
    figure.update_xaxes(title="Top N% of customers")
    figure.update_yaxes(title="Cumulative share of revenue", tickformat=".0%")
    st.plotly_chart(plotly_layout(figure, height=360), use_container_width=True)

    top10 = customers[customers["top_n_percent"] == 10]
    if not top10.empty:
        st.markdown(
            f"<span class='caption-note'>The top 10% of customers account for "
            f"<b>{percent(float(top10['cumulative_pct_of_revenue'].iloc[0]))}</b> of "
            "revenue - unusually flat, because almost everyone buys exactly once. "
            "There is no small high-value group to build a retention programme "
            "around.</span>",
            unsafe_allow_html=True,
        )


def _segments(data) -> None:
    st.subheader("RFM segments")
    profile = customer_analytics.segment_profile(customer_analytics.rfm_segments(data))

    left, right = st.columns([2, 3])
    with left:
        figure = go.Figure()
        figure.add_bar(
            y=profile["segment"], x=profile["pct_of_customers"],
            name="Share of customers", orientation="h", marker_color=MUTED,
            hovertemplate="%{y}<br>Customers: %{x:.1%}<extra></extra>",
        )
        figure.add_bar(
            y=profile["segment"], x=profile["pct_of_revenue"],
            name="Share of revenue", orientation="h", marker_color=ACCENT,
            hovertemplate="%{y}<br>Revenue: %{x:.1%}<extra></extra>",
        )
        figure.update_layout(barmode="group")
        figure.update_xaxes(title="Share", tickformat=".0%")
        figure.update_yaxes(title="")
        st.plotly_chart(plotly_layout(figure, height=400), use_container_width=True)

    with right:
        st.dataframe(
            profile[["segment", "customers", "pct_of_customers", "avg_recency_days",
                     "avg_orders", "avg_lifetime_revenue", "pct_of_revenue",
                     "revenue_concentration_index", "recommended_action"]],
            hide_index=True, use_container_width=True, height=400,
            column_config={
                "segment": st.column_config.TextColumn("Segment"),
                "customers": st.column_config.NumberColumn("Customers", format="%d"),
                "pct_of_customers": st.column_config.NumberColumn(
                    "% customers", format="percent"),
                "avg_recency_days": st.column_config.NumberColumn(
                    "Days since order", format="%.0f"),
                "avg_orders": st.column_config.NumberColumn("Avg orders", format="%.2f"),
                "avg_lifetime_revenue": st.column_config.NumberColumn(
                    "Avg value", format="%.2f"),
                "pct_of_revenue": st.column_config.NumberColumn(
                    "% revenue", format="percent"),
                "revenue_concentration_index": st.column_config.NumberColumn(
                    "Concentration", format="%.2f",
                    help="Share of revenue divided by share of customers."),
                "recommended_action": st.column_config.TextColumn(
                    "Recommended action", width="large"),
            },
        )

    st.markdown(
        "<span class='caption-note'>Recency and Monetary are scored as quintiles of "
        "this customer base. Frequency is not usefully scoreable here - 97% of "
        "customers have exactly one order - so the segment rules branch on the raw "
        "order count instead. That is a property of the business, not a flaw in the "
        "method, and it is why these segment names differ from a textbook RFM "
        "scheme.</span>",
        unsafe_allow_html=True,
    )


def _cohorts(data, dashboard: DashboardData) -> None:
    st.subheader("Cohort retention")

    matrix = cohorts.cohort_retention_matrix(data, max_months=12)
    if matrix.empty:
        st.warning("Not enough history in the current selection to build cohorts.")
        return

    values = matrix.drop(columns=[0], errors="ignore")
    left, right = st.columns([3, 2])

    with left:
        figure = px.imshow(
            values.to_numpy(dtype=float),
            x=[f"M{c}" for c in values.columns],
            y=[d.strftime("%b %Y") for d in matrix.index],
            color_continuous_scale="Blues", aspect="auto",
            labels=dict(color="Retention %"), text_auto=".1f",
        )
        figure.update_traces(
            hovertemplate="Cohort %{y}<br>%{x}<br>Retention: %{z:.2f}%<extra></extra>"
        )
        figure.update_xaxes(title="Months since first purchase", side="top")
        figure.update_yaxes(title="Cohort")
        st.plotly_chart(plotly_layout(figure, height=520, legend=False),
                        use_container_width=True)
        st.markdown(
            "<span class='caption-note'>Note the scale - these are fractions of a "
            "percent, not the double digits a retention table usually shows. Blank "
            "cells have not happened yet and are left empty rather than filled with "
            "zero.</span>",
            unsafe_allow_html=True,
        )

    with right:
        experience = cohorts.retention_by_first_experience(data)
        if not experience.empty:
            st.markdown("**Does a bad first order stop them coming back?**")
            colours = [
                WARN if ("late" in str(e).lower() or "1-2" in str(e)) else ACCENT
                for e in experience["first_experience"]
            ]
            figure = go.Figure()
            figure.add_bar(
                y=experience["first_experience"], x=experience["repeat_rate"],
                orientation="h", marker_color=colours,
                customdata=experience[["customers", "avg_first_review"]],
                hovertemplate=(
                    "%{y}<br>Repeat: %{x:.2%}<br>Customers: %{customdata[0]:,.0f}"
                    "<br>Avg first review: %{customdata[1]:.2f}<extra></extra>"
                ),
            )
            figure.update_xaxes(
                title="Ordered again within 90 days", tickformat=".1%",
                range=[0, float(experience["repeat_rate"].max()) * 1.5],
            )
            figure.update_yaxes(title="")
            st.plotly_chart(plotly_layout(figure, height=300, legend=False),
                            use_container_width=True)
            st.markdown(
                "<span class='caption-note'>The axis starts at zero deliberately. The "
                "difference between a good and a bad first experience is real but "
                "small, because almost nobody returns either way - which is the "
                "argument against selling a delivery programme as a retention "
                "programme.</span>",
                unsafe_allow_html=True,
            )

        gaps = cohorts.time_between_orders(data)
        if gaps:
            st.markdown("**For the few who do return**")
            metrics = st.columns(2)
            metrics[0].metric("Median days between orders",
                              f"{gaps['median_days']:.0f}")
            metrics[1].metric("Returned within 180 days",
                              percent(gaps["pct_within_180d"]))
