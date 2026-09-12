"""Page 2 - Delivery and satisfaction.

The core of this dataset. Olist has no returns table, so delivery performance
against the promised date, and the review score the customer leaves, together
carry the weight that returns analysis would in a retail dataset.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.data_access import DashboardData
from dashboard.theme import (
    ACCENT,
    ACCENT_LIGHT,
    GOOD,
    MUTED,
    WARN,
    money_compact,
    percent,
    plotly_layout,
)
from marketlens.analytics import delivery


def render(dashboard: DashboardData) -> None:
    data = dashboard.data
    st.title("Delivery and satisfaction")

    if data.lines.empty:
        st.warning("No orders match the current filters.")
        return

    overview = delivery.delivery_overview(data)
    if not overview:
        st.warning("No delivered orders with a delivery date in the current selection.")
        return

    st.caption(
        "Late means delivered after the date the customer was shown at checkout. "
        "Only delivered orders with a recorded delivery date are assessed - orders "
        "in transit are excluded rather than counted as on time."
    )

    _headline(overview, data)
    st.divider()

    _satisfaction_cliff(data)
    st.divider()

    left, right = st.columns([3, 2])
    with left:
        _over_time(data)
    with right:
        _by_region(data)

    st.divider()
    _regional_logistics(data)

    st.divider()
    _revenue_at_risk(data)

    st.divider()
    _problem_sellers(data)


def _headline(overview: dict, data) -> None:
    row = st.columns(5)
    row[0].metric("On-time delivery", percent(overview["on_time_rate"]))
    row[1].metric("Late orders", f"{int(overview['late_orders']):,}")
    row[2].metric("Median delivery days", f"{overview['median_delivery_days']:.0f}")
    row[3].metric("Average review score", f"{overview['avg_review_score']:.2f} / 5")
    row[4].metric(
        "Negative reviews (1-2)", percent(overview["negative_review_rate"])
    )

    gap = overview["avg_score_on_time"] - overview["avg_score_late"]
    st.markdown(
        f"<span class='caption-note'>Orders delivered on time average "
        f"<b>{overview['avg_score_on_time']:.2f}</b> out of 5. Orders delivered late "
        f"average <b>{overview['avg_score_late']:.2f}</b> - a gap of "
        f"<b>{gap:.2f} points</b>.</span>",
        unsafe_allow_html=True,
    )

    severe = delivery.severe_delay_impact(data)
    attribution = delivery.one_star_attribution(data)
    if severe and attribution:
        st.markdown(
            f"<span class='caption-note'>Severity matters more than the headline gap "
            f"suggests. Orders missing the date by more than a week average "
            f"<b>{severe['severe_score']:.2f}</b> - a fall of "
            f"<b>{severe['drop_severe']:.2f} points</b> against on-time orders. And "
            f"{percent(attribution['slow_share_of_one_star'])} of one-star orders took "
            f"longer than a typical order, against "
            f"{percent(attribution['late_share_of_one_star'])} that formally missed the "
            "promised date - the promise is padded enough that 'not late' is a generous "
            "bar.</span>",
            unsafe_allow_html=True,
        )


def _satisfaction_cliff(data) -> None:
    st.subheader("Where satisfaction breaks")
    bands = delivery.satisfaction_by_lateness_band(data)
    if bands.empty:
        return

    labels = bands["lateness_band"].astype(str)
    is_late = labels.str.contains("late")
    colours = [WARN if late else ACCENT for late in is_late]

    left, right = st.columns([3, 2])
    with left:
        figure = go.Figure()
        figure.add_bar(
            x=labels, y=bands["avg_review_score"], marker_color=colours,
            customdata=bands[["orders", "one_star_rate"]],
            hovertemplate=(
                "%{x}<br>Average score: %{y:.2f}<br>Orders: %{customdata[0]:,.0f}"
                "<br>One-star rate: %{customdata[1]:.1%}<extra></extra>"
            ),
        )
        figure.update_yaxes(title="Average review score", range=[0, 5])
        figure.update_xaxes(title="")
        st.plotly_chart(plotly_layout(figure, height=360, legend=False),
                        use_container_width=True)
        st.markdown(
            "<span class='caption-note'>The relationship is a cliff at the promised "
            "date, not a slope. That makes the operational target unambiguous: beat "
            "the date, by any margin. Two days faster on an already-on-time order buys "
            "almost nothing.</span>",
            unsafe_allow_html=True,
        )

    with right:
        st.markdown("**Score and one-star rate by band**")
        st.dataframe(
            bands[["lateness_band", "orders", "pct_of_orders", "avg_review_score",
                   "one_star_rate", "avg_delivery_days"]],
            hide_index=True, use_container_width=True, height=360,
            column_config={
                "lateness_band": st.column_config.TextColumn("Band"),
                "orders": st.column_config.NumberColumn("Orders", format="%d"),
                "pct_of_orders": st.column_config.NumberColumn("% orders", format="percent"),
                "avg_review_score": st.column_config.NumberColumn("Score", format="%.2f"),
                "one_star_rate": st.column_config.NumberColumn("1-star", format="percent"),
                "avg_delivery_days": st.column_config.NumberColumn("Days", format="%.0f"),
            },
        )


def _over_time(data) -> None:
    st.subheader("Delivery reliability over time")
    monthly = delivery.monthly_delivery_performance(data)
    if monthly.empty:
        return

    figure = go.Figure()
    figure.add_bar(
        x=monthly["order_month"], y=monthly["late_rate"], name="Late rate",
        marker_color=ACCENT_LIGHT,
        hovertemplate="%{x|%b %Y}<br>Late: %{y:.1%}<extra></extra>",
    )
    figure.add_scatter(
        x=monthly["order_month"], y=monthly["avg_review_score"],
        name="Average review score", mode="lines+markers", yaxis="y2",
        line=dict(color=ACCENT, width=2.5), marker=dict(size=5),
        hovertemplate="%{x|%b %Y}<br>Score: %{y:.2f}<extra></extra>",
    )
    figure.update_layout(
        yaxis=dict(title="Late rate", tickformat=".0%"),
        yaxis2=dict(title="Review score", overlaying="y", side="right",
                    range=[1, 5], showgrid=False),
    )
    st.plotly_chart(plotly_layout(figure, height=340), use_container_width=True)
    st.markdown(
        "<span class='caption-note'>Cohorted on the month the order was placed, not "
        "the month it arrived - otherwise a spike in late deliveries just follows the "
        "previous month's sales spike.</span>",
        unsafe_allow_html=True,
    )


def _regional_logistics(data) -> None:
    """Regional logistics KPIs.

    The sellers cluster in the Southeast, so distance from that cluster is what
    most of these differences actually measure - freight burden, transit time
    and review score all move together as you get further away.
    """
    st.subheader("Regional logistics")
    regions = delivery.regional_performance(data)
    if regions.empty:
        return

    st.dataframe(
        regions[["customer_region", "orders", "product_revenue", "pct_of_revenue",
                 "avg_order_value", "freight_to_price_ratio", "avg_delivery_days",
                 "late_rate", "avg_review_score"]],
        hide_index=True, use_container_width=True,
        column_config={
            "customer_region": st.column_config.TextColumn("Region"),
            "orders": st.column_config.NumberColumn("Orders", format="%d"),
            "product_revenue": st.column_config.NumberColumn("Revenue", format="%.0f"),
            "pct_of_revenue": st.column_config.NumberColumn("% revenue", format="percent"),
            "avg_order_value": st.column_config.NumberColumn("AOV", format="%.2f"),
            "freight_to_price_ratio": st.column_config.NumberColumn(
                "Freight / price", format="percent",
                help="Freight is the only cost Olist exposes - there is no cost price."),
            "avg_delivery_days": st.column_config.NumberColumn("Days", format="%.1f"),
            "late_rate": st.column_config.NumberColumn("Late", format="percent"),
            "avg_review_score": st.column_config.NumberColumn("Score", format="%.2f"),
        },
    )

    sellers = delivery.seller_region_share(data)
    if not sellers.empty:
        top = sellers.iloc[0]
        st.markdown(
            f"<span class='caption-note'>"
            f"{percent(float(top['pct_of_revenue']))} of revenue ships from sellers based "
            f"in the {top['seller_region']}, so the regional spread above is largely a "
            "distance measurement.</span>",
            unsafe_allow_html=True,
        )


def _by_region(data) -> None:
    st.subheader("Late rate by region")
    regions = delivery.delivery_by_dimension(data, "customer_region", min_orders=50)
    if regions.empty:
        return

    figure = px.bar(
        regions.sort_values("late_rate"),
        x="late_rate", y="customer_region", orientation="h",
        color="avg_review_score", color_continuous_scale="RdYlGn",
        range_color=[3.5, 4.5],
        custom_data=["avg_delivery_days", "orders"],
    )
    figure.update_traces(
        hovertemplate=(
            "%{y}<br>Late rate: %{x:.1%}<br>Avg days: %{customdata[0]:.0f}"
            "<br>Orders: %{customdata[1]:,.0f}<extra></extra>"
        )
    )
    figure.update_xaxes(title="Late delivery rate", tickformat=".0%")
    figure.update_yaxes(title="")
    figure.update_layout(coloraxis_colorbar=dict(title="Score"))
    st.plotly_chart(plotly_layout(figure, height=340, legend=False),
                    use_container_width=True)


def _revenue_at_risk(data) -> None:
    st.subheader("Revenue attached to a poor experience")
    at_risk = delivery.revenue_at_risk_from_experience(data)
    if at_risk.empty:
        return

    left, right = st.columns([2, 3])
    with left:
        figure = px.pie(
            at_risk, values="revenue", names="experience", hole=0.5,
            color="experience",
            color_discrete_map={
                "On time and acceptably reviewed": GOOD,
                "On time but badly reviewed": MUTED,
                "Late but not badly reviewed": "#c08552",
                "Late and badly reviewed": WARN,
            },
        )
        figure.update_traces(
            textinfo="percent", hovertemplate="%{label}<br>R$%{value:,.0f}<extra></extra>"
        )
        st.plotly_chart(plotly_layout(figure, height=320), use_container_width=True)

    with right:
        st.dataframe(
            at_risk[["experience", "orders", "customers", "pct_of_orders",
                     "revenue", "pct_of_revenue", "avg_review_score",
                     "avg_delivery_days"]],
            hide_index=True, use_container_width=True,
            column_config={
                "experience": st.column_config.TextColumn("Experience", width="medium"),
                "orders": st.column_config.NumberColumn("Orders", format="%d"),
                "customers": st.column_config.NumberColumn("Customers", format="%d"),
                "pct_of_orders": st.column_config.NumberColumn("% orders", format="percent"),
                "revenue": st.column_config.NumberColumn("Revenue", format="%.0f"),
                "pct_of_revenue": st.column_config.NumberColumn("% revenue", format="percent"),
                "avg_review_score": st.column_config.NumberColumn("Score", format="%.2f"),
                "avg_delivery_days": st.column_config.NumberColumn("Days", format="%.0f"),
            },
        )
        bad = at_risk[at_risk["experience"].str.contains("badly")]
        if not bad.empty:
            st.markdown(
                f"<span class='caption-note'>"
                f"{money_compact(float(bad['revenue'].sum()))} of revenue - "
                f"{percent(float(bad['pct_of_revenue'].sum()))} - sits behind orders the "
                "customer rated one or two stars.</span>",
                unsafe_allow_html=True,
            )


def _problem_sellers(data) -> None:
    st.subheader("Sellers with a delivery problem")
    problem = delivery.problem_sellers(data, limit=15)
    if problem.empty:
        st.info("No sellers with enough volume exceed the late-rate threshold here.")
        return

    st.dataframe(
        problem[["seller_id", "seller_state", "orders", "late_rate",
                 "company_late_rate", "late_vs_company_multiple",
                 "avg_delivery_days", "avg_review_score", "revenue"]],
        hide_index=True, use_container_width=True,
        column_config={
            "seller_id": st.column_config.TextColumn("Seller", width="medium"),
            "seller_state": st.column_config.TextColumn("State"),
            "orders": st.column_config.NumberColumn("Orders", format="%d"),
            "late_rate": st.column_config.NumberColumn("Late rate", format="percent"),
            "company_late_rate": st.column_config.NumberColumn(
                "Market rate", format="percent"),
            "late_vs_company_multiple": st.column_config.NumberColumn(
                "x market", format="%.2f"),
            "avg_delivery_days": st.column_config.NumberColumn("Days", format="%.1f"),
            "avg_review_score": st.column_config.NumberColumn("Score", format="%.2f"),
            "revenue": st.column_config.NumberColumn("Revenue", format="%.0f"),
        },
    )
    st.markdown(
        "<span class='caption-note'>Only sellers with at least 50 delivered orders are "
        "shown - below that a single late parcel moves the rate by two points. Olist "
        "does not control fulfilment, so seller SLAs are one of the few operational "
        "levers the platform has.</span>",
        unsafe_allow_html=True,
    )
