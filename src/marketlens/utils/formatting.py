"""Number and currency formatting shared by reports and the dashboard."""

from __future__ import annotations

from marketlens.config import CURRENCY_SYMBOL


def format_currency(value: float, decimals: int = 0) -> str:
    """Format an amount with the project currency symbol and thousands separators."""
    if value is None:
        return "-"
    return f"{CURRENCY_SYMBOL}{value:,.{decimals}f}"


def format_compact(value: float) -> str:
    """Format a large amount compactly, e.g. 13,449,530 -> R$13.45M.

    Only millions and billions are abbreviated. Six-figure amounts read better
    in full than as "985.62K", and this dataset has a lot of them.
    """
    if value is None:
        return "-"
    abs_value = abs(value)
    for threshold, suffix in ((1e9, "B"), (1e6, "M")):
        if abs_value >= threshold:
            return f"{CURRENCY_SYMBOL}{value / threshold:,.2f}{suffix}"
    return f"{CURRENCY_SYMBOL}{value:,.0f}"


def format_percent(value: float, decimals: int = 1) -> str:
    """Format a fraction (0.0731) as a percentage string (7.3%)."""
    if value is None:
        return "-"
    return f"{value * 100:,.{decimals}f}%"


def format_int(value: float) -> str:
    """Format a count with thousands separators."""
    if value is None:
        return "-"
    return f"{value:,.0f}"
