-- ===========================================================================
-- MarketLens - Retention and cohort analysis (Olist)
-- ===========================================================================
-- A cohort is the group of customers whose FIRST purchase falls in a given
-- month. Retention in month N is the share of that cohort placing an order N
-- months later.
--
-- Three things shape every number in this file:
--
--   1. Cohorts key on customer_unique_id. Keying on the per-order customer_id
--      produces a matrix of exact zeros - see query 12.
--
--   2. Retention here is genuinely very low: about 3% of customers ever order
--      again. The matrix is mostly fractions of a percent, and that IS the
--      finding rather than a bug. Because the numbers are small, single cells
--      are noisy and the trend is read from a fixed 90-day window instead.
--
--   3. Cells beyond a cohort's observable horizon are NULL, not zero. The
--      August 2018 cohort has no month-3 number because month 3 has not
--      happened; filling it with zero manufactures a decline that is purely a
--      calendar artefact.
--
-- Unlike a retail dataset with a signup event, Olist has no customer
-- registration - the first purchase IS the acquisition. There is therefore no
-- left truncation to correct for beyond the start of the reporting window.
-- ===========================================================================


-- ============================ QUERY 10: Cohort retention matrix ============
-- Business question: of the customers acquired in each month, what share came
--   back in each of the following months?
-- Why it matters: the clearest picture of whether the marketplace holds onto
--   anyone. Read down a column to compare cohorts at the same age, which is
--   the only fair comparison.
-- Techniques: window function to derive the cohort, month arithmetic from date
--   parts, conditional aggregation with FILTER to pivot, NULL handling for
--   cells that cannot yet be observed.
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS order_month,
        MIN(DATE_TRUNC('month', o.order_purchase_timestamp)::date)
            OVER (PARTITION BY c.customer_unique_id)          AS cohort_month
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_unique_id, DATE_TRUNC('month', o.order_purchase_timestamp)
),
cohort_activity AS (
    SELECT
        cohort_month,
        (EXTRACT(YEAR FROM order_month) - EXTRACT(YEAR FROM cohort_month)) * 12
        + (EXTRACT(MONTH FROM order_month) - EXTRACT(MONTH FROM cohort_month)) AS months_since,
        COUNT(DISTINCT customer_unique_id) AS active_customers
    FROM customer_orders
    GROUP BY cohort_month, 2
),
cohort_size AS (
    SELECT cohort_month, active_customers AS cohort_customers
    FROM cohort_activity
    WHERE months_since = 0
),
observable AS (
    SELECT
        cs.cohort_month,
        cs.cohort_customers,
        (EXTRACT(YEAR FROM DATE '2018-08-01') - EXTRACT(YEAR FROM cs.cohort_month)) * 12
        + (EXTRACT(MONTH FROM DATE '2018-08-01') - EXTRACT(MONTH FROM cs.cohort_month))
            AS months_observable
    FROM cohort_size cs
)
SELECT
    o.cohort_month,
    o.cohort_customers,
    o.months_observable,
    CASE WHEN o.months_observable >= 1 THEN
        ROUND(100.0 * COALESCE(MAX(ca.active_customers) FILTER (WHERE ca.months_since = 1), 0)
              / o.cohort_customers, 2) END AS m1,
    CASE WHEN o.months_observable >= 2 THEN
        ROUND(100.0 * COALESCE(MAX(ca.active_customers) FILTER (WHERE ca.months_since = 2), 0)
              / o.cohort_customers, 2) END AS m2,
    CASE WHEN o.months_observable >= 3 THEN
        ROUND(100.0 * COALESCE(MAX(ca.active_customers) FILTER (WHERE ca.months_since = 3), 0)
              / o.cohort_customers, 2) END AS m3,
    CASE WHEN o.months_observable >= 6 THEN
        ROUND(100.0 * COALESCE(MAX(ca.active_customers) FILTER (WHERE ca.months_since = 6), 0)
              / o.cohort_customers, 2) END AS m6,
    CASE WHEN o.months_observable >= 12 THEN
        ROUND(100.0 * COALESCE(MAX(ca.active_customers) FILTER (WHERE ca.months_since = 12), 0)
              / o.cohort_customers, 2) END AS m12
FROM observable o
INNER JOIN cohort_activity ca ON ca.cohort_month = o.cohort_month
GROUP BY o.cohort_month, o.cohort_customers, o.months_observable
ORDER BY o.cohort_month;


-- ============================ QUERY 11: Does a bad first delivery stop them? 
-- Business question: are customers whose first order arrived late less likely
--   to come back?
-- Why it matters: this is the most useful retention cut the dataset supports.
--   Olist has no acquisition-channel field, so "which customers come back" has
--   to be answered from what did happen to them - and delivery experience is
--   the strongest candidate.
--
--   The result is the interesting part: the difference is real but small,
--   because the repeat rate is close to zero either way. That matters, because
--   it stops a delivery programme being sold as a retention programme.
--
--   Association, not proof: customers with a late first delivery may differ in
--   other ways - remote regions, bulky items - that independently suppress
--   repeat purchasing.
-- Techniques: nested CTEs, DISTINCT ON to pick the first order per customer,
--   LEFT JOIN with a date-bounded condition, CASE WHEN grouping.
WITH first_order AS (
    -- DISTINCT ON is the PostgreSQL idiom for "one row per group, chosen by an
    -- ORDER BY" - here the earliest order for each person.
    --
    -- order_id is in the ORDER BY as a tie-breaker, not for display. Some
    -- customers placed two orders on the same timestamp, and without a stable
    -- second key PostgreSQL is free to return either one - which made this
    -- query's output drift by a few customers between runs.
    SELECT DISTINCT ON (c.customer_unique_id)
        c.customer_unique_id,
        o.order_id,
        o.order_purchase_timestamp AS first_order_date,
        o.order_status,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    ORDER BY c.customer_unique_id, o.order_purchase_timestamp, o.order_id
),
classified AS (
    SELECT
        f.customer_unique_id,
        f.first_order_date,
        CASE
            WHEN DATE(f.order_delivered_customer_date)
                 > DATE(f.order_estimated_delivery_date) THEN 'First delivery late'
            ELSE 'First delivery on time'
        END                                                    AS first_experience,
        r.review_score                                         AS first_review_score,
        DATE(f.order_delivered_customer_date)
            - DATE(f.first_order_date)                         AS first_delivery_days
    FROM first_order f
    LEFT JOIN order_reviews r ON r.order_id = f.order_id
    WHERE f.order_delivered_customer_date IS NOT NULL
      -- Only customers with a full 90 days to come back, measured from the
      -- newest order actually present rather than from the window edge.
      AND f.first_order_date
          <= (SELECT MAX(o2.order_purchase_timestamp) FROM orders o2
              INNER JOIN order_items oi2 ON oi2.order_id = o2.order_id
              WHERE o2.order_status NOT IN ('canceled', 'unavailable')
                AND o2.order_purchase_timestamp < DATE '2018-09-01') - INTERVAL '90 days'
),
returned AS (
    SELECT
        cl.customer_unique_id,
        cl.first_experience,
        cl.first_review_score,
        cl.first_delivery_days,
        MAX(CASE
                WHEN o.order_purchase_timestamp >  cl.first_order_date
                 AND o.order_purchase_timestamp <= cl.first_order_date + INTERVAL '90 days'
                THEN 1 ELSE 0
            END) AS returned_within_90d
    FROM classified cl
    INNER JOIN customers c ON c.customer_unique_id = cl.customer_unique_id
    LEFT  JOIN orders    o ON o.customer_id = c.customer_id
                          AND o.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY cl.customer_unique_id, cl.first_experience, cl.first_review_score,
             cl.first_delivery_days
)
SELECT
    first_experience,
    COUNT(*)                                             AS customers,
    SUM(returned_within_90d)                             AS returned,
    ROUND(100.0 * AVG(returned_within_90d), 3)           AS repeat_90d_pct,
    ROUND(AVG(first_review_score), 3)                    AS avg_first_review,
    ROUND(AVG(first_delivery_days), 1)                   AS avg_first_delivery_days,
    -- The gap against the on-time group, in percentage points.
    ROUND(
        100.0 * AVG(returned_within_90d)
        - 100.0 * (SELECT AVG(returned_within_90d) FROM returned
                   WHERE first_experience = 'First delivery on time'), 3
    )                                                    AS vs_on_time_pp
FROM returned
GROUP BY first_experience
ORDER BY repeat_90d_pct DESC;


-- ============================ QUERY 12: Time between orders ================
-- Business question: for the few customers who do return, how long do they
--   wait?
-- Why it matters: supplies the number behind any definition of "lapsed". It
--   describes a small subset - only about 3% of customers produce a gap at all
--   - which the customer count in the output makes explicit.
--
--   One caveat the numbers have to be read with: every gap counts equally, so
--   a customer with several orders contributes several gaps. The final column
--   therefore also reports the median of each customer's own median gap, which
--   weights every customer equally.
-- Techniques: LAG() partitioned by customer, date subtraction,
--   PERCENTILE_CONT for median and quartiles, nested aggregate in a subquery.
WITH ordered_purchases AS (
    SELECT
        c.customer_unique_id,
        o.order_purchase_timestamp,
        LAG(o.order_purchase_timestamp)
            OVER (PARTITION BY c.customer_unique_id ORDER BY o.order_purchase_timestamp)
                AS previous_order
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_unique_id, o.order_purchase_timestamp
),
gaps AS (
    SELECT
        customer_unique_id,
        DATE(order_purchase_timestamp) - DATE(previous_order) AS days_between_orders
    FROM ordered_purchases
    WHERE previous_order IS NOT NULL
),
per_customer AS (
    SELECT
        customer_unique_id,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY days_between_orders) AS customer_median_gap
    FROM gaps
    GROUP BY customer_unique_id
)
SELECT
    COUNT(*)                                                          AS repeat_purchases,
    COUNT(DISTINCT customer_unique_id)                                AS repeat_customers,
    ROUND(AVG(days_between_orders), 1)                                AS avg_days_between,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY days_between_orders) AS p25_days,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY days_between_orders) AS median_days,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY days_between_orders) AS p75_days,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY days_between_orders) AS p90_days,
    ROUND(100.0 * COUNT(*) FILTER (WHERE days_between_orders <= 30) / COUNT(*), 2)
                                                                      AS pct_within_30d,
    ROUND(100.0 * COUNT(*) FILTER (WHERE days_between_orders <= 90) / COUNT(*), 2)
                                                                      AS pct_within_90d,
    ROUND(100.0 * COUNT(*) FILTER (WHERE days_between_orders <= 180) / COUNT(*), 2)
                                                                      AS pct_within_180d,
    -- Every customer weighted equally, rather than every gap.
    (SELECT ROUND(PERCENTILE_CONT(0.50)
                  WITHIN GROUP (ORDER BY customer_median_gap)::numeric, 1)
     FROM per_customer)                                               AS median_of_customer_medians
FROM gaps;
