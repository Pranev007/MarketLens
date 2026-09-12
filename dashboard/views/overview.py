"""Page 1 - Executive overview."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.data_access import DashboardData, cached_kpis
from dashboard.theme import (
    ACCENT,
    ACCENT_LIGHT,
    GOOD,
    MUTED,
    WARN,
    money,
    money_compact,
    percent,
    plotly_layout,
)
from marketlens.analytics import delivery, products, revenue as revenue_analytics


def render(dashboard: DashboardData) -> None:
    data = dashboard.data
    st.title("Executive overview")

    if data.lines.empty:
        st.warning("No orders match the current filters. Widen the selection to see results.")
        return

    kpis = cached_kpis(dashboard.filters)
    st.caption(
        f"{kpis.period_start:%d %b %Y} to {kpis.period_end:%d %b %Y} - "
        f"{kpis.total_orders:,} orders from {kpis.unique_customers:,} customers"
    )

    _kpi_rows(kpis)
    st.divider()

    monthly = revenue_analytics.revenue_growth(revenue_analytics.monthly_revenue(data))

    left, right = st.columns([3, 2])
    with left:
        _revenue_trend(monthly)
    with right:
        _category_revenue(data)

    lower_left, lower_right = st.columns([3, 2])
    with lower_left:
        _orders_and_aov(monthly)
    with lower_right:
        _review_distribution(data)


def _kpi_rows(kpis) -> None:
    """Three rows of headline metrics, grouped by the question they answer."""
    st.markdown("**Commercial**")
    row1 = st.columns(4)
    row1[0].metric("Product revenue", money_compact(kpis.product_revenue))
    row1[1].metric("Orders", f"{kpis.total_orders:,}")
    row1[2].metric("Average order value", money(kpis.avg_order_value, 2))
    row1[3].metric("Items per order", f"{kpis.avg_items_per_order:.2f}")

    st.markdown("**Customer**")
    row2 = st.columns(4)
    row2[0].metric("Unique customers", f"{kpis.unique_customers:,}")
    row2[1].metric(
        "Repeat purchase rate", percent(kpis.repeat_purchase_rate, 2),
        help="Share of customers with two or more orders, keyed on "
             "customer_unique_id. Keying on the per-order customer_id would "
             "report exactly 0.00%.",
    )
    row2[2].metric("Revenue per customer", money(kpis.revenue_per_customer, 2))
    row2[3].metric("Active sellers", f"{kpis.active_sellers:,}")

    st.markdown("**Operational**")
    row3 = st.columns(4)
    row3[0].metric("On-time delivery", percent(kpis.on_time_delivery_rate))
    row3[1].metric("Average delivery days", f"{kpis.avg_delivery_days:.1f}")
    row3[2].metric("Average review score", f"{kpis.avg_review_score:.2f} / 5")
    row3[3].metric(
        "Freight share of GMV", percent(kpis.freight_ratio),
        help="Olist has no cost price, so gross margin cannot be computed. "
             "Freight is the one cost the dataset exposes.",
    )


def _revenue_trend(monthly) -> None:
    st.subheader("Revenue trend")
    figure = go.Figure()
    figure.add_bar(
        x=monthly["order_month"], y=monthly["product_revenue"],
        name="Product revenue", marker_color=ACCENT_LIGHT,
        hovertemplate="%{x|%b %Y}<br>Revenue: R$%{y:,.0f}<extra></extra>",
    )
    figure.add_scatter(
        x=monthly["order_month"], y=monthly["revenue_3m_avg"],
        name="3-month average", mode="lines",
        line=dict(color=ACCENT, width=2.5),
        hovertemplate="%{x|%b %Y}<br>3-month avg: R$%{y:,.0f}<extra></extra>",
    )
    figure.update_yaxes(title="Product revenue")
    st.plotly_chart(plotly_layout(figure, height=330), use_container_width=True)
    st.markdown(
        "<span class='caption-note'>Revenue is the goods only; freight is tracked "
        "separately because it is a pass-through cost, not margin.</span>",
        unsafe_allow_html=True,
    )


def _orders_and_aov(monthly) -> None:
    st.subheader("Orders and average order value")
    figure = go.Figure()
    figure.add_bar(
        x=monthly["order_month"], y=monthly["orders"], name="Orders",
        marker_color=ACCENT_LIGHT,
        hovertemplate="%{x|%b %Y}<br>Orders: %{y:,.0f}<extra></extra>",
    )
    figure.add_scatter(
        x=monthly["order_month"], y=monthly["avg_order_value"],
        name="Average order value", mode="lines", yaxis="y2",
        line=dict(color=WARN, width=2.5),
        hovertemplate="%{x|%b %Y}<br>AOV: R$%{y:,.2f}<extra></extra>",
    )
    figure.update_layout(
        yaxis=dict(title="Orders"),
        yaxis2=dict(title="Average order value", overlaying="y", side="right",
                    showgrid=False),
    )
    st.plotly_chart(plotly_layout(figure, height=320), use_container_width=True)
    st.markdown(
        "<span class='caption-note'>Growth is volume-driven: orders compound while "
        "basket value drifts down.</span>",
        unsafe_allow_html=True,
    )


def _category_revenue(data) -> None:
    st.subheader("Revenue by category")
    performance = products.category_performance(data)
    figure = px.bar(
        performance.sort_values("product_revenue"),
        x="product_revenue", y="category_group", orientation="h",
        color_discrete_sequence=[ACCENT],
        custom_data=["avg_review_score", "orders"],
    )
    figure.update_traces(
        hovertemplate=(
            "%{y}<br>Revenue: R$%{x:,.0f}<br>Orders: %{customdata[1]:,.0f}"
            "<br>Review score: %{customdata[0]:.2f}<extra></extra>"
        )
    )
    figure.update_xaxes(title="Product revenue")
    figure.update_yaxes(title="")
    st.plotly_chart(plotly_layout(figure, height=330, legend=False),
                    use_container_width=True)

    top3 = performance.head(3)
    st.markdown(
        f"<span class='caption-note'>Top three categories account for "
        f"<b>{percent(float(top3['pct_of_revenue'].sum()))}</b> of revenue.</span>",
        unsafe_allow_html=True,
    )


def _review_distribution(data) -> None:
    """Reviews are polarised rather than mediocre - worth seeing on page one."""
    st.subheader("How customers rate their orders")
    distribution = delivery.review_score_distribution(data)
    if distribution.empty:
        st.info("No reviewed orders in the current selection.")
        return

    colours = [
        WARN if score <= 2 else MUTED if score == 3 else GOOD
        for score in distribution["review_score"]
    ]
    figure = go.Figure()
    figure.add_bar(
        x=distribution["review_score"], y=distribution["pct_of_orders"],
        marker_color=colours,
        customdata=distribution[["orders", "late_rate"]],
        hovertemplate=(
            "%{x} star<br>%{y:.1%} of orders<br>Orders: %{customdata[0]:,.0f}"
            "<br>Late: %{customdata[1]:.1%}<extra></extra>"
        ),
    )
    figure.update_xaxes(title="Review score", dtick=1)
    figure.update_yaxes(title="Share of orders", tickformat=".0%")
    st.plotly_chart(plotly_layout(figure, height=320, legend=False),
                    use_container_width=True)

    negative = float(
        distribution.loc[distribution["review_score"] <= 2, "pct_of_orders"].sum()
    )
    five_star = float(
        distribution.loc[distribution["review_score"] == 5, "pct_of_orders"].sum()
    )
    st.markdown(
        f"<span class='caption-note'>Scores are polarised rather than mediocre: "
        f"<b>{percent(five_star)}</b> give five stars and <b>{percent(negative)}</b> "
        "give one or two. There is no returns table in this dataset - the review "
        "score is the quality signal.</span>",
        unsafe_allow_html=True,
    )
