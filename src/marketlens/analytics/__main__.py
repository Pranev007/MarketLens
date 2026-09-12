"""Entry point: run the full Python analysis and write the reports.

    python -m marketlens.analytics

Reads the cleaned dataset (from PostgreSQL when available, otherwise from
``data/processed``), computes every analysis and writes:

    reports/analysis/*.csv          every analysis table, for inspection
    reports/business_insights.md    the generated insights report
    reports/kpi_summary.md          the headline KPI table
"""

from __future__ import annotations

import logging
import sys

import pandas as pd

from marketlens.analytics import (
    cohorts,
    customers as customer_analytics,
    delivery,
    products,
    revenue as revenue_analytics,
)
from marketlens.analytics.insights import (
    generate_insights,
    insights_to_frame,
    insights_to_markdown,
)
from marketlens.analytics.kpis import calculate_headline_kpis, kpi_table
from marketlens.config import ANALYSIS_END, ANALYSIS_START, REPORTS_DIR, ensure_directories
from marketlens.data_processing.datasets import AnalysisData
from marketlens.utils.logging_config import configure_logging

logger = logging.getLogger(__name__)


def build_analysis_tables(data: AnalysisData) -> dict[str, pd.DataFrame]:
    """Compute every analysis table exposed by the project."""
    monthly = revenue_analytics.monthly_revenue(data)
    rfm = customer_analytics.rfm_segments(data)

    return {
        "kpi_summary": kpi_table(calculate_headline_kpis(data)),
        "monthly_revenue": revenue_analytics.revenue_growth(monthly),

        "category_performance": products.category_performance(data),
        "category_performance_leaf": products.category_performance(data, "category_en"),
        "category_quality_matrix": products.category_quality_matrix(data),
        "category_growth": products.category_growth(data),
        "top_products": products.top_products(data, limit=25),
        "seller_performance": products.seller_performance(data),
        "seller_concentration": products.seller_concentration(data),

        "customer_rfm_segments": customer_analytics.segment_profile(rfm),
        "customer_frequency_distribution":
            customer_analytics.purchase_frequency_distribution(data),
        "customer_revenue_concentration": customer_analytics.revenue_concentration(data),
        "customer_repeat_behaviour":
            pd.DataFrame([customer_analytics.repeat_behaviour(data)]),
        "top_customers": customer_analytics.top_customers(data, limit=25),

        "cohort_retention_matrix": cohorts.cohort_retention_matrix(data).reset_index(),
        "cohort_sizes": cohorts.cohort_sizes(data),
        "cohort_repeat_90d": cohorts.repeat_within_days(data, days=90),
        "cohort_retention_by_region": cohorts.retention_by_dimension(data),
        "cohort_retention_by_first_experience":
            cohorts.retention_by_first_experience(data),
        "time_between_orders": pd.DataFrame([cohorts.time_between_orders(data)]),

        "delivery_overview": pd.DataFrame([delivery.delivery_overview(data)]),
        "delivery_satisfaction": delivery.satisfaction_by_delivery(data),
        "delivery_lateness_bands": delivery.satisfaction_by_lateness_band(data),
        "delivery_by_region": delivery.delivery_by_dimension(data),
        "delivery_by_category": delivery.delivery_by_dimension(data, "category_group"),
        "delivery_monthly": delivery.monthly_delivery_performance(data),
        "delivery_review_distribution": delivery.review_score_distribution(data),
        "delivery_problem_sellers": delivery.problem_sellers(data),
        "delivery_estimate_accuracy": delivery.estimate_accuracy(data),
        "delivery_revenue_at_risk": delivery.revenue_at_risk_from_experience(data),

        "delivery_severe_delay": pd.DataFrame([delivery.severe_delay_impact(data)]),
        "delivery_one_star_attribution":
            pd.DataFrame([delivery.one_star_attribution(data)]),

        "regional_performance": delivery.regional_performance(data),
        "seller_region_share": delivery.seller_region_share(data),
    }


def main() -> int:
    configure_logging()
    ensure_directories()

    logger.info("Loading dataset...")
    data = AnalysisData.load()
    logger.info("Dataset: %s", {k: f"{v:,}" for k, v in data.describe().items()})
    if data.window_applied:
        logger.info("Reporting window: %s to %s", ANALYSIS_START, ANALYSIS_END)

    logger.info("Computing analysis tables...")
    tables = build_analysis_tables(data)

    analysis_dir = REPORTS_DIR / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(analysis_dir / f"{name}.csv", index=False)
    logger.info("Wrote %s analysis tables -> %s", len(tables), analysis_dir)

    logger.info("Generating business insights...")
    insights = generate_insights(data)
    insights_to_frame(insights).to_csv(analysis_dir / "business_insights.csv", index=False)

    insights_path = REPORTS_DIR / "business_insights.md"
    insights_path.write_text(insights_to_markdown(insights, data), encoding="utf-8")
    logger.info("Wrote %s insights -> %s", len(insights), insights_path.name)

    kpis = calculate_headline_kpis(data)
    kpi_path = REPORTS_DIR / "kpi_summary.md"
    kpi_path.write_text(
        "# MarketLens - KPI Summary\n\n"
        "Generated from the Olist dataset by `python -m marketlens.analytics`.\n\n"
        f"Reporting window: **{ANALYSIS_START} to {ANALYSIS_END}** "
        "(see `docs/kpi_definitions.md` for why the sparse tail months are excluded).\n\n"
        + kpi_table(kpis).to_markdown(index=False)
        + "\n\nDefinitions for every KPI above are in `docs/kpi_definitions.md`.\n",
        encoding="utf-8",
    )
    logger.info("Wrote KPI summary -> %s", kpi_path.name)

    logger.info("Analysis complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
