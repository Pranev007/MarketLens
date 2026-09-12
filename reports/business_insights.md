# MarketLens - Business Insights

Reporting period: **05 January 2017 to 29 August 2018**  
Product revenue: **R$13.45M** across **99,092 orders** from **94,703 customers**

Source: the Brazilian E-Commerce Public Dataset by Olist - real marketplace transactions, not simulated data.

Every figure below is computed from the dataset by `python -m marketlens.analytics`. Nothing here is hard-coded, and re-running the pipeline regenerates this file from whatever the data then says.

---

### 1. The business runs on acquisition, not retention

*Area: Customer | Priority: high*

**Observation.** Only 3.0% of customers ever place a second order. 97.0% of the customer base bought exactly once and never came back, and repeat buyers contribute just 5.6% of revenue.

**Evidence.** 94,703 distinct customers placed 1.03 orders each on average; only 2,874 of them ordered more than once. The most active single customer placed 16 orders. Note that this figure is only visible if customers are keyed on customer_unique_id - keying on the per-order customer_id reports a repeat rate of 0.0%, which is a join artefact rather than a finding.

**Implication.** Every month's revenue has to be bought again. There is no compounding base carrying the business, so growth is capped by acquisition spend and the economics depend entirely on first-order contribution covering the cost of acquisition. A marketplace with this profile is fragile: a rise in acquisition cost hits revenue almost immediately, with no installed base to cushion it.

**Recommendation.** Treat second-purchase rate as a primary company metric, not a marketing one, and instrument it before spending against it. The cheapest test is a post-delivery lifecycle programme aimed at the 30 days after a good delivery, measured against a randomised holdout. If second-purchase rate cannot be moved, the honest conclusion is that this is a low-frequency category and unit economics must work on the first order alone - which is a pricing and freight question, not a CRM one.

### 2. Missing the promised delivery date collapses the review score

*Area: Operations | Priority: high*

**Observation.** Orders delivered on time average 4.28 out of 5. Orders delivered late average 2.26 - and 54.1% of them are given one star, against 6.8% of on-time orders. Orders missing the date by more than a week average 1.69, a fall of 2.6 points.

**Evidence.** 6,531 of 96,200 delivered orders arrived late (6.8%), carrying R$985,618 of revenue. Late orders took 34 days on average against 11 for on-time ones. The change is a cliff rather than a slope: orders arriving 0-2 early average 4.10, while orders 1-3 days late average 3.28 - a drop of 0.82 points for missing the promised date by as little as a day. Overall 13.1% of reviewed orders score 1 or 2. Read the other way round, 36.6% of one-star orders missed the promised date and 69.3% took longer than a typical order (10 days), so slow shipping sits behind most of the one-star population even where the padded promise was technically met.

**Implication.** Delivery reliability, not price or product, is the dominant driver of stated customer satisfaction in this marketplace. Because the effect is a step change at the promised date rather than a gradual decline, the operational target is unambiguous: beat the date, by any margin. Being two days quicker on an already-on-time order buys almost nothing; being one day late costs roughly a full point of review score.

**Recommendation.** Manage to the promise, not to the transit time. Two levers follow directly: tighten seller dispatch SLAs, since the delay accumulates before the parcel reaches the carrier, and intervene on orders while they are still in flight and already tracking late - a proactive notification and a goodwill gesture is far cheaper than the one-star review and the lost customer. Measure the intervention against a holdout of late orders that receive nothing.

### 3. Customers in the North pay more, wait longer and rate lower

*Area: Geography | Priority: high*

**Observation.** A North customer pays 22.7% of the item price in freight and waits 23 days. A Southeast customer pays 15.2% and waits 11 days.

**Evidence.** Average review score falls from 4.13 in the Southeast to 3.96 in the North, and the late-delivery rate runs 8.6% against 6.1%. The average order is R$181.96 there against R$130.98. 78.4% of revenue is shipped by sellers based in the Southeast, so distance from that cluster is what these differences actually measure. Together the three smallest regions are only 20.3% of revenue.

**Implication.** The regions with the most headroom for growth are the ones the current logistics network serves worst, and the penalty compounds: higher shipping cost suppresses conversion, longer transit raises the chance of missing the promise, and a missed promise produces the one-star review that suppresses the next purchase. Expanding marketing into these regions without fixing fulfilment would buy dissatisfied customers.

**Recommendation.** Treat this as a network problem, not a marketing one. Recruiting sellers physically located in the underserved regions is the highest-leverage move, because it shortens the trunk leg for every order they take. Short of that, a forward stocking point for the highest-volume categories would address cost and time together. Quantify the prize first by modelling what the region's volume would be at Southeast freight ratios.

### 4. A good first delivery barely improves the odds of a second order

*Area: Customer | Priority: high*

**Observation.** Customers whose first delivery arrived on time return within 90 days 2.0% of the time. Customers whose first delivery was late return 1.8% of the time. The difference is real but small - 0.25 percentage points - because the repeat rate is close to zero either way.

**Evidence.** The comparison covers 69,332 customers served on time and 5,686 served late, all with a full 90 days to come back. Splitting by the review the customer left rather than by the delivery gives the same shape: 2.1% for 4-5 star first orders against 2.0% for 1-2 star ones. Across the whole base only 3.0% of customers ever order again.

**Implication.** This is the finding that stops delivery improvement being oversold. Fixing lateness is strongly justified by satisfaction, by the cost of complaint handling and by reputation - but it will not, on this evidence, convert a one-purchase business into a repeat one. Something more fundamental limits repeat purchasing here, most plausibly that the categories are inherently low-frequency and there is no reason to return. Presenting a delivery programme as a retention programme would set a target it cannot hit.

**Recommendation.** Justify the delivery work on satisfaction and cost-to-serve, and set a separate, evidence-led workstream on repeat purchasing. Start by testing whether repeat is achievable at all: take the categories with the highest natural replenishment rate, run a targeted second-purchase offer, and see whether the rate moves at all before committing to a retention strategy.

### 5. A small number of sellers carry most of the marketplace

*Area: Marketplace | Priority: medium*

**Observation.** The top 30 sellers - the largest 1% - account for 25.8% of revenue, and the top 10% account for 67.3%.

**Evidence.** Revenue is spread across 3,029 active sellers, but the distribution is steep: half of them together produce less than 3.3% of revenue. Separately, 25 sellers with meaningful volume run a late rate more than half again the marketplace average, between them carrying R$991,888 of revenue.

**Implication.** Marketplace risk sits with a handful of relationships. Because the platform does not control fulfilment, those same sellers also determine the delivery experience for a large share of customers - so seller churn or seller underperformance transmits directly into both revenue and satisfaction.

**Recommendation.** Run explicit account management on the top decile, with delivery performance in the commercial conversation rather than only volume. For the flagged underperformers, set a published dispatch SLA with consequences, and measure whether tightening it moves the late rate before extending it across the base.

### 6. Revenue is growing on volume while basket value drifts down

*Area: Revenue | Priority: medium*

**Observation.** Comparing the same 8 months a year apart, revenue grew 138.3%. Over the same period average order value fell 2.1%, from R$142.86 to R$139.89.

**Evidence.** Every category group grew, led by Industry & Construction at 353.5%. The comparison is restricted to the 8 calendar months present in both years, because the dataset stops part-way through the second year and a plain year-on-year total would understate it.

**Implication.** Growth of this shape is healthy in a land-grab phase but it does mean the unit economics are not improving as the business scales. With repeat purchasing near zero, revenue per customer is essentially average order value - so a drifting basket is a drifting customer value, and any rise in acquisition cost eats directly into contribution.

**Recommendation.** Track average order value as a primary metric alongside revenue, and treat basket-building as the main lever on customer value given how little retention contributes. The free-shipping threshold is the obvious instrument, and it addresses the freight burden at the same time - one intervention against two of the findings here.
