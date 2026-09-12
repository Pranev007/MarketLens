"""Page 3 - Product, category and seller analytics."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from dashboard.data_access import DashboardData
from dashboard.theme import ACCENT, ACCENT_LIGHT, MUTED, WARN, percent, plotly_layout
from marketlens.analytics import products


def render(dashboard: DashboardData) -> None:
    data = dashboard.data
    st.title("Product and seller analytics")

    if data.lines.empty:
        st.warning("No orders match the current filters.")
        return

    st.caption(
        "Olist carries no cost price, so nothing here reports margin. The customer's "
        "review score and the freight burden are used instead to separate a category "
        "that sells well from one that performs well."
    )

    _category_table(data)
    st.divider()

    left, right = st.columns(2)
    with left:
        _revenue_vs_satisfaction(data)
    with right:
        _category_growth(data)

    st.divider()
    _sellers(data)

    st.divider()
    _top_products(data)


def _category_table(data) -> None:
    st.subheader("Category performance")
    performance = products.category_performance(data)
    matrix = products.category_quality_matrix(data)[
        ["category_group", "revenue_rank", "satisfaction_rank", "rank_gap"]
    ]
    table = performance.merge(matrix, on="category_group", how="left")

    st.dataframe(
        table[["category_group", "orders", "units", "product_revenue", "pct_of_revenue",
               "avg_item_price", "freight_ratio", "avg_review_score",
               "negative_review_rate", "late_rate", "revenue_rank",
               "satisfaction_rank"]],
        hide_index=True, use_container_width=True,
        column_config={
            "category_group": st.column_config.TextColumn("Category"),
            "orders": st.column_config.NumberColumn("Orders", format="%d"),
            "units": st.column_config.NumberColumn("Units", format="%d"),
            "product_revenue": st.column_config.NumberColumn("Revenue", format="%.0f"),
            "pct_of_revenue": st.column_config.NumberColumn("% revenue", format="percent"),
            "avg_item_price": st.column_config.NumberColumn("Avg price", format="%.2f"),
            "freight_ratio": st.column_config.NumberColumn("Freight share", format="percent"),
            "avg_review_score": st.column_config.NumberColumn("Score", format="%.2f"),
            "negative_review_rate": st.column_config.NumberColumn(
                "1-2 star", format="percent"),
            "late_rate": st.column_config.NumberColumn("Late", format="percent"),
            "revenue_rank": st.column_config.NumberColumn("Rev #", format="%d"),
            "satisfaction_rank": st.column_config.NumberColumn("Score #", format="%d"),
        },
    )

    mismatched = table[table["rank_gap"] >= 2]
    if not mismatched.empty:
        names = ", ".join(
            f"{row['category_group']} (#{int(row['revenue_rank'])} revenue, "
            f"#{int(row['satisfaction_rank'])} satisfaction)"
            for _, row in mismatched.iterrows()
        )
        st.markdown(
            f"<span class='caption-note'>Selling well but satisfying poorly: {names}. "
            "With no cost data this is the closest available equivalent to "
            "'big on revenue, thin on profit'.</span>",
            unsafe_allow_html=True,
        )


def _revenue_vs_satisfaction(data) -> None:
    st.subheader("Revenue against satisfaction")
    performance = products.category_performance(data)
    company_score = float(data.delivered_lines["review_score"].mean())

    figure = px.scatter(
        performance,
        x="avg_review_score", y="product_revenue", size="units",
        text="category_group", color_discrete_sequence=[ACCENT], size_max=55,
        custom_data=["late_rate", "freight_ratio", "orders"],
    )
    figure.update_traces(
        textposition="top center",
        hovertemplate=(
            "%{text}<br>Review score: %{x:.2f}<br>Revenue: R$%{y:,.0f}"
            "<br>Late rate: %{customdata[0]:.1%}"
            "<br>Freight share: %{customdata[1]:.1%}<extra></extra>"
        ),
    )
    figure.add_vline(x=company_score, line_dash="dash", line_color=MUTED)
    figure.update_xaxes(title="Average review score")
    figure.update_yaxes(title="Product revenue")
    st.plotly_chart(plotly_layout(figure, height=400, legend=False),
                    use_container_width=True)
    st.markdown(
        f"<span class='caption-note'>Dashed line is the company average of "
        f"{company_score:.2f}. Bubble size is units sold. Top-left is the problem "
        "quadrant: high revenue, low satisfaction.</span>",
        unsafe_allow_html=True,
    )


def _category_growth(data) -> None:
    st.subheader("Growth by category")
    growth = products.category_growth(data)
    if growth.empty:
        st.info("Not enough history in the current selection to compute growth.")
        return

    months = int(growth["months_compared"].iloc[0])
    figure = px.bar(
        growth.sort_values("growth_rate"),
        x="growth_rate", y="category_group", orientation="h",
        color_discrete_sequence=[ACCENT],
        custom_data=["revenue_first_period", "revenue_last_period"],
    )
    figure.update_traces(
        hovertemplate=(
            "%{y}<br>Growth: %{x:.1%}<br>Before: R$%{customdata[0]:,.0f}"
            "<br>After: R$%{customdata[1]:,.0f}<extra></extra>"
        )
    )
    figure.update_xaxes(title="Revenue growth", tickformat=".0%")
    figure.update_yaxes(title="")
    st.plotly_chart(plotly_layout(figure, height=400, legend=False),
                    use_container_width=True)
    st.markdown(
        f"<span class='caption-note'>Compares the same {months} calendar months a year "
        "apart. The dataset stops in August 2018, so a plain year-on-year total would "
        "show every category shrinking.</span>",
        unsafe_allow_html=True,
    )


def _sellers(data) -> None:
    st.subheader("Sellers")
    left, right = st.columns([2, 3])

    with left:
        concentration = products.seller_concentration(data)
        figure = px.line(
            concentration, x="top_n_percent", y="cumulative_pct_of_revenue",
            markers=True, color_discrete_sequence=[ACCENT],
        )
        figure.update_traces(
            hovertemplate="Top %{x}% of sellers<br>%{y:.1%} of revenue<extra></extra>"
        )
        figure.update_xaxes(title="Top N% of sellers")
        figure.update_yaxes(title="Cumulative share of revenue", tickformat=".0%")
        st.plotly_chart(plotly_layout(figure, height=330, legend=False),
                        use_container_width=True)
        top10 = concentration[concentration["top_n_percent"] == 10]
        if not top10.empty:
            st.markdown(
                f"<span class='caption-note'>The top 10% of sellers carry "
                f"<b>{percent(float(top10['cumulative_pct_of_revenue'].iloc[0]))}</b> "
                "of revenue.</span>",
                unsafe_allow_html=True,
            )

    with right:
        sellers = products.seller_performance(data).head(12)
        st.dataframe(
            sellers[["seller_id", "seller_state", "orders", "units",
                     "product_revenue", "avg_item_price", "late_rate",
                     "avg_review_score"]],
            hide_index=True, use_container_width=True, height=330,
            column_config={
                "seller_id": st.column_config.TextColumn("Seller", width="medium"),
                "seller_state": st.column_config.TextColumn("State"),
                "orders": st.column_config.NumberColumn("Orders", format="%d"),
                "units": st.column_config.NumberColumn("Units", format="%d"),
                "product_revenue": st.column_config.NumberColumn("Revenue", format="%.0f"),
                "avg_item_price": st.column_config.NumberColumn("Avg price", format="%.2f"),
                "late_rate": st.column_config.NumberColumn("Late", format="percent"),
                "avg_review_score": st.column_config.NumberColumn("Score", format="%.2f"),
            },
        )


def _top_products(data) -> None:
    st.subheader("Top products by revenue")
    top = products.top_products(data, limit=15)
    if top.empty:
        return

    company_score = float(data.delivered_lines["review_score"].mean())
    top = top.copy()
    top["flag"] = [
        "below average score" if (s or company_score) < company_score - 0.3 else "normal"
        for s in top["avg_review_score"]
    ]

    figure = px.bar(
        top.sort_values("product_revenue"),
        x="product_revenue", y="product_id", orientation="h",
        color="flag",
        color_discrete_map={"below average score": WARN, "normal": ACCENT_LIGHT},
        custom_data=["category_group", "units_sold", "avg_review_score", "freight_ratio"],
    )
    figure.update_traces(
        hovertemplate=(
            "%{y}<br>%{customdata[0]}<br>Revenue: R$%{x:,.0f}"
            "<br>Units: %{customdata[1]:,.0f}<br>Score: %{customdata[2]:.2f}"
            "<br>Freight share: %{customdata[3]:.1%}<extra></extra>"
        )
    )
    figure.update_xaxes(title="Product revenue")
    figure.update_yaxes(title="")
    st.plotly_chart(plotly_layout(figure, height=430), use_container_width=True)
    st.markdown(
        "<span class='caption-note'>Product ids rather than names - Olist does not "
        "publish product names, only the category. Highlighted where the review score "
        "runs materially below the company average.</span>",
        unsafe_allow_html=True,
    )
