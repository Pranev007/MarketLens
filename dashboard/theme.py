"""Shared styling and formatting helpers for the dashboard."""

from __future__ import annotations

import streamlit as st

from marketlens.config import CURRENCY_SYMBOL

#: One accent colour, one warning colour, and greys. Restraint keeps a
#: business dashboard readable; a different colour per series does not.
ACCENT = "#2f6f8f"
ACCENT_LIGHT = "#8fb8cc"
WARN = "#b4553f"
GOOD = "#5b8a72"
MUTED = "#9aa5b1"
INK = "#1f2933"

#: Ordered palette for categorical charts.
SEQUENCE = [ACCENT, ACCENT_LIGHT, GOOD, "#c08552", WARN, "#7a6a9b", "#4f6d7a", MUTED]

CSS = """
<style>
    .block-container { padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1400px; }
    [data-testid="stMetricValue"] { font-size: 1.55rem; }
    [data-testid="stMetricLabel"] { color: #52606d; font-weight: 500; }
    [data-testid="stMetricDelta"] { font-size: 0.8rem; }
    h1 { font-size: 1.9rem; padding-bottom: 0.2rem; }
    h2 { font-size: 1.25rem; margin-top: 1.4rem; }
    h3 { font-size: 1.02rem; }
    .insight-card {
        border: 1px solid #e4e7eb; border-left: 4px solid #2f6f8f;
        border-radius: 6px; padding: 1rem 1.2rem; margin-bottom: 1rem;
        background: #fbfcfd;
    }
    .insight-card.high { border-left-color: #b4553f; }
    .insight-card h4 { margin: 0 0 .6rem 0; font-size: 1.05rem; }
    .insight-label {
        font-size: .72rem; text-transform: uppercase; letter-spacing: .06em;
        color: #7b8794; font-weight: 600;
    }
    .caption-note { color: #7b8794; font-size: 0.82rem; }
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def money(value: float, decimals: int = 0) -> str:
    """Currency with thousands separators."""
    return f"{CURRENCY_SYMBOL}{value:,.{decimals}f}"


def money_compact(value: float) -> str:
    """Compact currency, e.g. INR 233.69M."""
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            return f"{CURRENCY_SYMBOL}{value / threshold:,.2f}{suffix}"
    return f"{CURRENCY_SYMBOL}{value:,.0f}"


def percent(value: float, decimals: int = 1) -> str:
    return f"{value * 100:,.{decimals}f}%"


def plotly_layout(fig, height: int = 340, legend: bool = True, **kwargs):
    """Apply the shared chart styling to a Plotly figure."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color=INK, size=12),
        # Section headings come from st.subheader, so the figure itself carries
        # no title. Without setting it explicitly Plotly renders "undefined".
        title=dict(text="", font=dict(size=14)),
        hoverlabel=dict(bgcolor="white", font_size=12),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        **kwargs,
    )
    fig.update_xaxes(showgrid=False, linecolor="#cbd2d9")
    fig.update_yaxes(showgrid=True, gridcolor="#eef1f4", linecolor="#cbd2d9")
    return fig
