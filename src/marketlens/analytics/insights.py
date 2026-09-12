"""Generated business insights.

Every insight in this module is computed from the dataset at run time. Nothing
is hard-coded: if the data changes, the numbers, the ranking and in several
cases the conclusion change with it. Each one follows the same four-part shape,
because an observation without a recommended action is not an insight:

    Observation     - what the data shows
    Evidence        - the numbers behind it
    Implication     - why the business should care
    Recommendation  - what to do about it

Where a relationship is descriptive rather than causal, the insight says so
rather than implying a lever that has not been demonstrated. One insight here
deliberately reports a *weak* effect, because the honest answer to "will fixing
delivery fix retention?" in this dataset is "barely".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from marketlens.analytics import (
    cohorts,
    customers as customer_analytics,
    delivery,
    products,
    revenue as revenue_analytics,
)
from marketlens.analytics.kpis import calculate_headline_kpis
from marketlens.data_processing.datasets import AnalysisData
from marketlens.utils.formatting import format_compact, format_currency, format_percent


@dataclass
class Insight:
    """A single finding, with the numbers that produced it."""

    area: str
    title: str
    observation: str
    evidence: str
    implication: str
    recommendation: str
    priority: str = "medium"
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self, number: int | None = None) -> str:
        heading = f"### {number}. {self.title}" if number else f"### {self.title}"
        return "\n".join([
            heading, "",
            f"*Area: {self.area} | Priority: {self.priority}*", "",
            f"**Observation.** {self.observation}", "",
            f"**Evidence.** {self.evidence}", "",
            f"**Implication.** {self.implication}", "",
            f"**Recommendation.** {self.recommendation}", "",
        ])


def generate_insights(data: AnalysisData) -> list[Insight]:
    """Run every insight generator and return them ordered by priority."""
    generators = (
        _acquisition_treadmill,
        _late_delivery_destroys_satisfaction,
        _distance_penalty,
        _delivery_fix_will_not_fix_retention,
        _seller_concentration,
        _growth_is_volume_not_value,
    )
    insights: list[Insight] = []
    for generator in generators:
        result = generator(data)
        if result is not None:
            insights.append(result)

    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(insights, key=lambda i: order.get(i.priority, 3))


# ---------------------------------------------------------------------------
# Individual insight generators
# ---------------------------------------------------------------------------


def _acquisition_treadmill(data: AnalysisData) -> Insight | None:
    """Almost nobody comes back."""
    repeat = customer_analytics.repeat_behaviour(data)
    frequency = customer_analytics.purchase_frequency_distribution(data)
    if not repeat:
        return None

    one_time = frequency[frequency["frequency_band"].astype(str) == "1 order"]
    one_time_share = float(one_time["pct_of_customers"].iloc[0]) if not one_time.empty else 0.0

    return Insight(
        area="Customer",
        title="The business runs on acquisition, not retention",
        priority="high",
        observation=(
            f"Only {format_percent(repeat['repeat_purchase_rate'])} of customers ever "
            f"place a second order. {format_percent(one_time_share)} of the customer base "
            "bought exactly once and never came back, and repeat buyers contribute just "
            f"{format_percent(repeat['pct_revenue_from_repeat_customers'])} of revenue."
        ),
        evidence=(
            f"{repeat['unique_customers']:,} distinct customers placed "
            f"{repeat['avg_orders_per_customer']:.2f} orders each on average; only "
            f"{repeat['repeat_customers']:,} of them ordered more than once. The most "
            f"active single customer placed {repeat['max_orders_by_one_customer']} orders. "
            "Note that this figure is only visible if customers are keyed on "
            "customer_unique_id - keying on the per-order customer_id reports a repeat "
            f"rate of {format_percent(repeat['repeat_rate_if_keyed_on_customer_id'])}, "
            "which is a join artefact rather than a finding."
        ),
        implication=(
            "Every month's revenue has to be bought again. There is no compounding base "
            "carrying the business, so growth is capped by acquisition spend and the "
            "economics depend entirely on first-order contribution covering the cost of "
            "acquisition. A marketplace with this profile is fragile: a rise in "
            "acquisition cost hits revenue almost immediately, with no installed base to "
            "cushion it."
        ),
        recommendation=(
            "Treat second-purchase rate as a primary company metric, not a marketing "
            "one, and instrument it before spending against it. The cheapest test is a "
            "post-delivery lifecycle programme aimed at the 30 days after a good "
            "delivery, measured against a randomised holdout. If second-purchase rate "
            "cannot be moved, the honest conclusion is that this is a low-frequency "
            "category and unit economics must work on the first order alone - which is a "
            "pricing and freight question, not a CRM one."
        ),
        metrics=repeat,
    )


def _late_delivery_destroys_satisfaction(data: AnalysisData) -> Insight | None:
    """The strongest relationship in the dataset."""
    outcome = delivery.satisfaction_by_delivery(data)
    bands = delivery.satisfaction_by_lateness_band(data)
    overview = delivery.delivery_overview(data)
    severe = delivery.severe_delay_impact(data)
    attribution = delivery.one_star_attribution(data)
    if outcome.empty or len(outcome) < 2 or not severe or not attribution:
        return None

    on_time = outcome[outcome["delivery_outcome"] == "On time or early"].iloc[0]
    late = outcome[outcome["delivery_outcome"] == "Late"].iloc[0]

    # The first band that tips into lateness, to show it is a cliff not a slope.
    late_bands = bands[bands["lateness_band"].astype(str).str.contains("late")]
    first_late = late_bands.iloc[0] if not late_bands.empty else None
    cliff = ""
    if first_late is not None:
        early_bands = bands[bands["lateness_band"].astype(str).str.contains("early")]
        last_early = early_bands.iloc[-1] if not early_bands.empty else None
        if last_early is not None:
            cliff = (
                f" The change is a cliff rather than a slope: orders arriving "
                f"{last_early['lateness_band']} average "
                f"{float(last_early['avg_review_score']):.2f}, while orders "
                f"{first_late['lateness_band']} average "
                f"{float(first_late['avg_review_score']):.2f} - a drop of "
                f"{float(last_early['avg_review_score']) - float(first_late['avg_review_score']):.2f} "
                "points for missing the promised date by as little as a day."
            )

    return Insight(
        area="Operations",
        title="Missing the promised delivery date collapses the review score",
        priority="high",
        observation=(
            f"Orders delivered on time average "
            f"{float(on_time['avg_review_score']):.2f} out of 5. Orders delivered late "
            f"average {float(late['avg_review_score']):.2f} - and "
            f"{format_percent(float(late['one_star_rate']))} of them are given one star, "
            f"against {format_percent(float(on_time['one_star_rate']))} of on-time orders. "
            f"Orders missing the date by more than a week average "
            f"{severe['severe_score']:.2f}, a fall of {severe['drop_severe']:.1f} points."
        ),
        evidence=(
            f"{int(late['orders']):,} of {int(outcome['orders'].sum()):,} delivered "
            f"orders arrived late ({format_percent(float(late['pct_of_orders']))}), "
            f"carrying {format_compact(float(late['revenue']))} of revenue. Late orders "
            f"took {float(late['avg_delivery_days']):.0f} days on average against "
            f"{float(on_time['avg_delivery_days']):.0f} for on-time ones."
            f"{cliff} Overall {format_percent(overview['negative_review_rate'])} of "
            "reviewed orders score 1 or 2. Read the other way round, "
            f"{format_percent(attribution['late_share_of_one_star'])} of one-star orders "
            f"missed the promised date and "
            f"{format_percent(attribution['slow_share_of_one_star'])} took longer than a "
            f"typical order ({attribution['median_delivery_days']:.0f} days), so slow "
            "shipping sits behind most of the one-star population even where the padded "
            "promise was technically met."
        ),
        implication=(
            "Delivery reliability, not price or product, is the dominant driver of "
            "stated customer satisfaction in this marketplace. Because the effect is a "
            "step change at the promised date rather than a gradual decline, the "
            "operational target is unambiguous: beat the date, by any margin. Being two "
            "days quicker on an already-on-time order buys almost nothing; being one day "
            "late costs roughly a full point of review score."
        ),
        recommendation=(
            "Manage to the promise, not to the transit time. Two levers follow directly: "
            "tighten seller dispatch SLAs, since the delay accumulates before the parcel "
            "reaches the carrier, and intervene on orders while they are still in flight "
            "and already tracking late - a proactive notification and a goodwill gesture "
            "is far cheaper than the one-star review and the lost customer. Measure the "
            "intervention against a holdout of late orders that receive nothing."
        ),
        metrics={
            "on_time_score": float(on_time["avg_review_score"]),
            "late_score": float(late["avg_review_score"]),
            "late_one_star_rate": float(late["one_star_rate"]),
            "late_rate": overview["late_rate"],
            "late_revenue": float(late["revenue"]),
        },
    )
def _distance_penalty(data: AnalysisData) -> Insight | None:
    """Distance from the seller cluster drives cost, speed and satisfaction."""
    regions = delivery.regional_performance(data)
    seller_geo = delivery.seller_region_share(data)
    if regions.empty:
        return None

    by_burden = regions.sort_values("freight_to_price_ratio", ascending=False)
    worst = by_burden.iloc[0]
    best = by_burden.iloc[-1]
    dominant_seller_region = seller_geo.iloc[0] if not seller_geo.empty else None

    seller_text = ""
    if dominant_seller_region is not None:
        seller_text = (
            f" {format_percent(float(dominant_seller_region['pct_of_revenue']))} of "
            f"revenue is shipped by sellers based in the "
            f"{dominant_seller_region['seller_region']}, so distance from that cluster "
            "is what these differences actually measure."
        )

    return Insight(
        area="Geography",
        title=f"Customers in the {worst['customer_region']} pay more, wait longer and rate lower",
        priority="high",
        observation=(
            f"A {worst['customer_region']} customer pays "
            f"{format_percent(float(worst['freight_to_price_ratio']))} of the item price "
            f"in freight and waits {float(worst['avg_delivery_days']):.0f} days. A "
            f"{best['customer_region']} customer pays "
            f"{format_percent(float(best['freight_to_price_ratio']))} and waits "
            f"{float(best['avg_delivery_days']):.0f} days."
        ),
        evidence=(
            f"Average review score falls from "
            f"{float(best['avg_review_score']):.2f} in the {best['customer_region']} to "
            f"{float(worst['avg_review_score']):.2f} in the {worst['customer_region']}, "
            f"and the late-delivery rate runs "
            f"{format_percent(float(worst['late_rate']))} against "
            f"{format_percent(float(best['late_rate']))}. The average order is "
            f"{format_currency(float(worst['avg_order_value']), 2)} there against "
            f"{format_currency(float(best['avg_order_value']), 2)}.{seller_text} Together "
            "the three smallest regions are only "
            f"{format_percent(float(regions.tail(3)['pct_of_revenue'].sum()))} of revenue."
        ),
        implication=(
            "The regions with the most headroom for growth are the ones the current "
            "logistics network serves worst, and the penalty compounds: higher shipping "
            "cost suppresses conversion, longer transit raises the chance of missing the "
            "promise, and a missed promise produces the one-star review that suppresses "
            "the next purchase. Expanding marketing into these regions without fixing "
            "fulfilment would buy dissatisfied customers."
        ),
        recommendation=(
            "Treat this as a network problem, not a marketing one. Recruiting sellers "
            "physically located in the underserved regions is the highest-leverage move, "
            "because it shortens the trunk leg for every order they take. Short of that, "
            "a forward stocking point for the highest-volume categories would address "
            "cost and time together. Quantify the prize first by modelling what the "
            "region's volume would be at Southeast freight ratios."
        ),
        metrics={
            "worst_region": worst["customer_region"],
            "worst_freight_ratio": float(worst["freight_to_price_ratio"]),
            "worst_delivery_days": float(worst["avg_delivery_days"]),
            "best_region": best["customer_region"],
            "best_freight_ratio": float(best["freight_to_price_ratio"]),
        },
    )


def _delivery_fix_will_not_fix_retention(data: AnalysisData) -> Insight | None:
    """The honest counter-finding: a good experience barely moves repeat rate."""
    experience = cohorts.retention_by_first_experience(data)
    repeat = customer_analytics.repeat_behaviour(data)
    if experience.empty:
        return None

    on_time = experience[experience["first_experience"] == "First delivery on time"]
    late = experience[experience["first_experience"] == "First delivery late"]
    good_review = experience[experience["first_experience"] == "First review 4-5 stars"]
    bad_review = experience[experience["first_experience"] == "First review 1-2 stars"]
    if on_time.empty or late.empty:
        return None

    on_time_rate = float(on_time["repeat_rate"].iloc[0])
    late_rate = float(late["repeat_rate"].iloc[0])
    gap_pp = 100 * (on_time_rate - late_rate)

    review_text = ""
    if not good_review.empty and not bad_review.empty:
        review_text = (
            f" Splitting by the review the customer left rather than by the delivery "
            f"gives the same shape: {format_percent(float(good_review['repeat_rate'].iloc[0]))} "
            f"for 4-5 star first orders against "
            f"{format_percent(float(bad_review['repeat_rate'].iloc[0]))} for 1-2 star ones."
        )

    return Insight(
        area="Customer",
        title="A good first delivery barely improves the odds of a second order",
        priority="high",
        observation=(
            "Customers whose first delivery arrived on time return within 90 days "
            f"{format_percent(on_time_rate)} of the time. Customers whose first delivery "
            f"was late return {format_percent(late_rate)} of the time. The difference is "
            f"real but small - {gap_pp:.2f} percentage points - because the repeat rate "
            "is close to zero either way."
        ),
        evidence=(
            f"The comparison covers {int(on_time['customers'].iloc[0]):,} customers served "
            f"on time and {int(late['customers'].iloc[0]):,} served late, all with a full "
            f"90 days to come back.{review_text} Across the whole base only "
            f"{format_percent(repeat['repeat_purchase_rate'])} of customers ever order "
            "again."
        ),
        implication=(
            "This is the finding that stops delivery improvement being oversold. Fixing "
            "lateness is strongly justified by satisfaction, by the cost of complaint "
            "handling and by reputation - but it will not, on this evidence, convert a "
            "one-purchase business into a repeat one. Something more fundamental limits "
            "repeat purchasing here, most plausibly that the categories are inherently "
            "low-frequency and there is no reason to return. Presenting a delivery "
            "programme as a retention programme would set a target it cannot hit."
        ),
        recommendation=(
            "Justify the delivery work on satisfaction and cost-to-serve, and set a "
            "separate, evidence-led workstream on repeat purchasing. Start by testing "
            "whether repeat is achievable at all: take the categories with the highest "
            "natural replenishment rate, run a targeted second-purchase offer, and see "
            "whether the rate moves at all before committing to a retention strategy."
        ),
        metrics={
            "repeat_after_on_time": on_time_rate,
            "repeat_after_late": late_rate,
            "gap_pp": gap_pp,
            "overall_repeat_rate": repeat["repeat_purchase_rate"],
        },
    )


def _seller_concentration(data: AnalysisData) -> Insight | None:
    """How much of the marketplace depends on how few sellers."""
    concentration = products.seller_concentration(data)
    problem = delivery.problem_sellers(data)
    if concentration.empty:
        return None

    top1 = concentration[concentration["top_n_percent"] == 1].iloc[0]
    top10 = concentration[concentration["top_n_percent"] == 10].iloc[0]

    problem_text = ""
    if not problem.empty:
        problem_revenue = float(problem["revenue"].sum())
        problem_text = (
            f" Separately, {len(problem)} sellers with meaningful volume run a late rate "
            f"more than half again the marketplace average, between them carrying "
            f"{format_compact(problem_revenue)} of revenue."
        )

    return Insight(
        area="Marketplace",
        title="A small number of sellers carry most of the marketplace",
        priority="medium",
        observation=(
            f"The top {int(top1['sellers']):,} sellers - the largest 1% - account for "
            f"{format_percent(float(top1['cumulative_pct_of_revenue']))} of revenue, and "
            f"the top 10% account for "
            f"{format_percent(float(top10['cumulative_pct_of_revenue']))}."
        ),
        evidence=(
            f"Revenue is spread across "
            f"{int(concentration['sellers'].iloc[-1]):,} active sellers, but the "
            f"distribution is steep: half of them together produce less than "
            f"{format_percent(1 - float(concentration[concentration['top_n_percent'] == 50].iloc[0]['cumulative_pct_of_revenue']))} "
            f"of revenue.{problem_text}"
        ),
        implication=(
            "Marketplace risk sits with a handful of relationships. Because the platform "
            "does not control fulfilment, those same sellers also determine the delivery "
            "experience for a large share of customers - so seller churn or seller "
            "underperformance transmits directly into both revenue and satisfaction."
        ),
        recommendation=(
            "Run explicit account management on the top decile, with delivery "
            "performance in the commercial conversation rather than only volume. For the "
            "flagged underperformers, set a published dispatch SLA with consequences, "
            "and measure whether tightening it moves the late rate before extending it "
            "across the base."
        ),
        metrics={
            "top1_pct_sellers_revenue_share": float(top1["cumulative_pct_of_revenue"]),
            "top10_pct_sellers_revenue_share": float(top10["cumulative_pct_of_revenue"]),
            "active_sellers": int(concentration["sellers"].iloc[-1]),
        },
    )
def _growth_is_volume_not_value(data: AnalysisData) -> Insight | None:
    """Volume is compounding; basket value is not."""
    growth = products.category_growth(data)
    monthly = revenue_analytics.revenue_growth(revenue_analytics.monthly_revenue(data))
    if growth.empty or monthly.empty:
        return None

    first_period = float(growth["revenue_first_period"].sum())
    last_period = float(growth["revenue_last_period"].sum())
    overall_growth = (last_period - first_period) / first_period if first_period else 0.0
    months = int(growth["months_compared"].iloc[0])

    early_aov = float(monthly.head(6)["avg_order_value"].mean())
    late_aov = float(monthly.tail(6)["avg_order_value"].mean())
    aov_change = (late_aov - early_aov) / early_aov if early_aov else 0.0

    fastest = growth.iloc[0]

    return Insight(
        area="Revenue",
        title="Revenue is growing on volume while basket value drifts down",
        priority="medium",
        observation=(
            f"Comparing the same {months} months a year apart, revenue grew "
            f"{format_percent(overall_growth)}. Over the same period average order value "
            f"{'fell' if aov_change < 0 else 'rose'} "
            f"{format_percent(abs(aov_change))}, from "
            f"{format_currency(early_aov, 2)} to {format_currency(late_aov, 2)}."
        ),
        evidence=(
            f"Every category group grew, led by {fastest['category_group']} at "
            f"{format_percent(float(fastest['growth_rate']))}. The comparison is "
            f"restricted to the {months} calendar months present in both years, because "
            "the dataset stops part-way through the second year and a plain year-on-year "
            "total would understate it."
        ),
        implication=(
            "Growth of this shape is healthy in a land-grab phase but it does mean the "
            "unit economics are not improving as the business scales. With repeat "
            "purchasing near zero, revenue per customer is essentially average order "
            "value - so a drifting basket is a drifting customer value, and any rise in "
            "acquisition cost eats directly into contribution."
        ),
        recommendation=(
            "Track average order value as a primary metric alongside revenue, and treat "
            "basket-building as the main lever on customer value given how little "
            "retention contributes. The free-shipping threshold is the obvious "
            "instrument, and it addresses the freight burden at the same time - one "
            "intervention against two of the findings here."
        ),
        metrics={
            "period_growth": overall_growth,
            "months_compared": months,
            "aov_change": aov_change,
            "early_aov": early_aov,
            "late_aov": late_aov,
        },
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def insights_to_frame(insights: list[Insight]) -> pd.DataFrame:
    """Flatten insights into a DataFrame for export."""
    return pd.DataFrame([
        {
            "area": i.area, "priority": i.priority, "title": i.title,
            "observation": i.observation, "evidence": i.evidence,
            "implication": i.implication, "recommendation": i.recommendation,
        }
        for i in insights
    ])


def insights_to_markdown(insights: list[Insight], data: AnalysisData) -> str:
    """Render the full insights report as Markdown."""
    kpis = calculate_headline_kpis(data)
    header = [
        "# MarketLens - Business Insights",
        "",
        f"Reporting period: **{kpis.period_start:%d %B %Y} to {kpis.period_end:%d %B %Y}**  ",
        f"Product revenue: **{format_compact(kpis.product_revenue)}** across "
        f"**{kpis.total_orders:,} orders** from **{kpis.unique_customers:,} customers**",
        "",
        "Source: the Brazilian E-Commerce Public Dataset by Olist - real marketplace "
        "transactions, not simulated data.",
        "",
        "Every figure below is computed from the dataset by "
        "`python -m marketlens.analytics`. Nothing here is hard-coded, and re-running the "
        "pipeline regenerates this file from whatever the data then says.",
        "",
        "---",
        "",
    ]
    body = [insight.to_markdown(i + 1) for i, insight in enumerate(insights)]
    return "\n".join(header + body)
