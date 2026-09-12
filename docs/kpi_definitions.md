# KPI Definitions — MarketLens

Every KPI in [`reports/kpi_summary.md`](../reports/kpi_summary.md) is defined here.
Each one is computed twice — once in Pandas (`src/marketlens/analytics/kpis.py`)
and once in SQL (`sql/revenue_analysis.sql`, query 01) — and
`tests/test_sql_python_parity.py` asserts the two agree. A dashboard number and a
SQL number that disagree is worse than having neither.

---

## Scope rules that apply to everything below

**Reporting window — 2017-01-01 to 2018-08-31.**
Olist spans September 2016 to October 2018, but the tails are not real trading
months: September 2016 has 4 orders, December 2016 has 1, and October 2018 has 4.
Charting those next to months of 7,000 orders produces growth rates in the
thousands of percent. The window is the contiguous run of complete months —
20 months holding 99.65% of all orders. Rows outside it are still loaded into the
database; the analysis layer filters them and says so. Set
`MARKETLENS_FULL_WINDOW=1` to analyse everything.

**Revenue-bearing orders.**
An order counts towards revenue when its status is neither `canceled` nor
`unavailable` **and** it has at least one line item. The second condition matters:
a handful of orders sit in `created` or `invoiced` with nothing on them, and
counting them inflates the order count without adding revenue.

**One row is one unit.**
Olist has no quantity column. Each `order_items` row is one unit of one product,
so "units" is a row count, not a `SUM(quantity)`.

**The customer key is `customer_unique_id`.**
Olist issues a fresh `customer_id` for every order. Grouping on `customer_id`
reports a repeat purchase rate of exactly 0.00%. Every customer-level KPI here
keys on `customer_unique_id`; `customer_accounts` is the only figure that
deliberately counts `customer_id`, to show the size of the gap.

**No margin is reported.**
Olist carries no cost price, so gross margin cannot be computed. Freight is the
one cost the dataset exposes, and the freight ratio stands in for it.

---

## Volume

| KPI | Definition |
|:----|:-----------|
| **Total orders** | `COUNT(*)` of distinct orders in the window, every status included. |
| **Delivered orders** | Orders with status `delivered`. |
| **Cancelled orders** | Orders with status `canceled`. |
| **Unavailable orders** | Orders with status `unavailable` — the seller could not supply the item. |
| **Cancellation rate** | Cancelled orders ÷ total orders. |
| **Unfulfilled rate** | (Cancelled + unavailable) ÷ total orders. Reported together because in both cases the customer received nothing. |

## Customer

| KPI | Definition |
|:----|:-----------|
| **Unique customers** | `COUNT(DISTINCT customer_unique_id)` over revenue-bearing orders. |
| **Customer accounts** | `COUNT(DISTINCT customer_id)` over the same orders — one per order by design. Shown only as the counterpoint to the line above. |
| **Repeat purchase rate** | Customers with 2 or more revenue-bearing orders ÷ customers with 1 or more. |
| **Revenue per customer** | Product revenue ÷ unique customers. Not a lifetime value: the observation window is 20 months and most customers appear once. |

## Commercial

| KPI | Definition |
|:----|:-----------|
| **Product revenue** | `SUM(price)` over revenue-bearing order lines. Excludes freight. |
| **Freight revenue** | `SUM(freight_value)` over the same lines. This is what the customer paid to ship, not Olist's cost. |
| **GMV** | Product revenue + freight revenue. |
| **Freight share of GMV** | Freight revenue ÷ GMV. |
| **Average order value** | Product revenue ÷ distinct revenue-bearing orders. Freight is excluded from the numerator, so AOV is what the customer spent on goods. |
| **Average items per order** | Revenue-bearing order lines ÷ distinct revenue-bearing orders. |
| **Average item price** | Product revenue ÷ revenue-bearing order lines. Note this is *per unit*, not per order — the two differ because orders average more than one item. |

## Supply

| KPI | Definition |
|:----|:-----------|
| **Active sellers** | `COUNT(DISTINCT seller_id)` on revenue-bearing lines. Lower than the seller table's row count, which includes sellers with no sales in the window. |
| **Products sold** | `COUNT(DISTINCT product_id)` on revenue-bearing lines. |

## Delivery

All delivery measures are computed on **delivered orders that carry a delivery
date**. Orders still in transit are excluded rather than counted as on time.

| KPI | Definition |
|:----|:-----------|
| **On-time delivery rate** | Orders where `order_delivered_customer_date` ≤ `order_estimated_delivery_date`, compared on the date, ÷ assessable delivered orders. The estimate is the date the customer was shown at checkout. |
| **Late delivery rate** | The complement: delivered after the promised date. |
| **Average delivery days** | Mean of `order_delivered_customer_date − order_purchase_timestamp`, in whole days. Measured from purchase, not from dispatch, because that is what the customer experiences. |
| **Median delivery days** | Median of the same. Reported alongside the mean because the distribution has a long right tail. |
| **Delivery date coverage** | Assessable delivered orders ÷ all delivered orders. A handful of delivered orders carry no delivery date; this says how much of the population the rates above cover. |

## Satisfaction

| KPI | Definition |
|:----|:-----------|
| **Average review score** | Mean `review_score` (1–5) over reviewed revenue-bearing orders. One review per order — where an order had several, the earliest is kept. |
| **Negative review rate** | Reviews scoring 1 or 2 ÷ reviewed orders. |
| **Review coverage** | Reviewed orders ÷ revenue-bearing orders. Olist reviews are near-universal, which is unusual and worth stating rather than assuming. |

---

## Derived measures used in the analysis pages

| Measure | Definition |
|:--------|:-----------|
| **Freight-to-price ratio** | `SUM(freight_value) ÷ SUM(price)` for the group. Used as the closest available proxy for cost pressure. |
| **Serious delay** | More than 7 days past the promised date. Reported separately from "late" because late is dominated by orders that missed by a day or two: the on-time/late gap is 2.0 points of review score, while on-time against more-than-a-week-late is 2.6. |
| **One-star attribution** | Two different figures that get conflated. Of *late* orders, the share rated one star (54.1%); and of *one-star* orders, the share that shipped slower than a typical order (69.3%) or that formally missed the promised date (36.6%). Both directions are computed. |
| **Lateness band** | Days between actual and promised delivery, bucketed. The relationship to satisfaction is a cliff at the promised date, not a slope. |
| **RFM segment** | Recency and Monetary scored as quintiles of this customer base. Frequency is *not* usefully scoreable — 97% of customers have exactly one order — so the segment rules branch on the raw order count instead. That is a property of the business, not a flaw in the method, and it is why these segment names differ from a textbook RFM scheme. |
| **Cohort retention** | Share of a month's first-time customers who place another order N months later. Cells beyond a cohort's observable horizon are left empty, not zero: "not yet observable" and "nobody came back" are different facts. |
| **First delivery experience** | Whether a customer's *first* order arrived late. The first order is the earliest by timestamp, ties broken on `order_id` so SQL and Pandas pick the same row — 281 customers placed two orders on an identical timestamp. |
| **90-day repeat** | Whether a customer placed another order within 90 days of their first, compared on the timestamp rather than on whole days, on both sides. |

---

## What is deliberately not reported

- **Gross margin, profit, contribution** — no cost price exists in Olist.
- **Return rate** — there is no returns table. Delivery lateness and review score
  carry the weight that returns analysis would in a retail dataset.
- **Discount or promotion effect** — there is no discount field.
- **Acquisition channel or CAC** — not in the dataset.
- **Customer lifetime value** — a 20-month window in which most customers appear
  once does not support a lifetime estimate. Revenue per customer is reported
  instead, and labelled as what it is.
