"""Page 6 - Business insights.

Every insight here is regenerated from whatever the current filters select.
Nothing is written into the page as text; if the filters change the underlying
numbers, the wording and the ranking change with them.
"""

from __future__ import annotations

import html

import streamlit as st

from dashboard.data_access import DashboardData, cached_insights, cached_kpis
from dashboard.theme import money_compact, percent


def render(dashboard: DashboardData) -> None:
    data = dashboard.data
    st.title("Business insights")

    if data.lines.empty:
        st.warning("No orders match the current filters.")
        return

    st.caption(
        "Generated from the current selection. Each finding follows the same shape: "
        "what the data shows, the numbers behind it, why it matters, and what to do."
    )

    kpis = cached_kpis(dashboard.filters)
    summary = st.columns(4)
    summary[0].metric("Product revenue", money_compact(kpis.product_revenue))
    summary[1].metric("Freight paid", money_compact(kpis.freight_revenue))
    summary[2].metric("Repeat purchase rate", percent(kpis.repeat_purchase_rate, 2))
    summary[3].metric("Late delivery rate", percent(kpis.late_delivery_rate))

    st.divider()

    insights = cached_insights(dashboard.filters)
    if not insights:
        st.info("Not enough data in the current selection to generate insights.")
        return

    areas = ["All"] + sorted({insight.area for insight in insights})
    chosen = st.radio("Filter by area", areas, horizontal=True, label_visibility="collapsed")
    visible = [i for i in insights if chosen == "All" or i.area == chosen]

    high = sum(1 for i in visible if i.priority == "high")
    st.markdown(
        f"<span class='caption-note'>{len(visible)} findings"
        f"{f', {high} high priority' if high else ''}.</span>",
        unsafe_allow_html=True,
    )
    st.write("")

    for number, insight in enumerate(visible, start=1):
        _render_card(number, insight)


def _render_card(number: int, insight) -> None:
    """One insight, laid out as Observation / Evidence / Implication / Action."""
    css_class = "insight-card high" if insight.priority == "high" else "insight-card"
    st.markdown(
        f"""
        <div class="{css_class}">
            <div class="insight-label">{html.escape(insight.area)} &middot;
                {html.escape(insight.priority)} priority</div>
            <h4>{number}. {html.escape(insight.title)}</h4>
            <p><span class="insight-label">Observation</span><br>
               {html.escape(insight.observation)}</p>
            <p><span class="insight-label">Evidence</span><br>
               {html.escape(insight.evidence)}</p>
            <p><span class="insight-label">Implication</span><br>
               {html.escape(insight.implication)}</p>
            <p><span class="insight-label">Recommendation</span><br>
               {html.escape(insight.recommendation)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
