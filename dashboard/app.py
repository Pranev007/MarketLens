"""MarketLens dashboard.

    streamlit run dashboard/app.py

Five pages sharing one set of sidebar filters. Navigation is handled here
rather than through Streamlit's magic ``pages/`` directory, because the filters
have to apply across every page - which needs a single script that owns the
filter state and passes the filtered dataset down.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Allow `streamlit run dashboard/app.py` from a clean checkout without the
# package being installed first.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dashboard.data_access import get_dashboard_data, render_sidebar  # noqa: E402
from dashboard.theme import apply_theme  # noqa: E402
from dashboard.views import (  # noqa: E402
    customer,
    delivery_view,
    insights_view,
    overview,
    product,
)

PAGES = {
    "Executive overview": overview.render,
    "Delivery & satisfaction": delivery_view.render,
    "Product & sellers": product.render,
    "Customer analytics": customer.render,
    "Business insights": insights_view.render,
}


def main() -> None:
    st.set_page_config(
        page_title="MarketLens - Olist Marketplace Analytics",
        page_icon=":bar_chart:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()

    st.sidebar.title("MarketLens")
    st.sidebar.caption("Brazilian marketplace analytics")
    page_name = st.sidebar.radio("Page", list(PAGES), label_visibility="collapsed")
    st.sidebar.divider()

    filters = render_sidebar()
    dashboard = get_dashboard_data(filters)

    PAGES[page_name](dashboard)


if __name__ == "__main__":
    main()
