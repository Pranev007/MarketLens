-- ===========================================================================
-- MarketLens - Delivery performance and customer satisfaction (Olist)
-- ===========================================================================
-- Olist has no returns table, so this file carries the weight that returns
-- analysis would in a retail dataset. It is arguably a better signal:
-- dissatisfaction is stated directly by the customer as a 1-5 review score,
-- and the data also records what the customer was PROMISED at checkout and
-- when the parcel actually arrived.
--
-- Definitions:
--   late          = order_delivered_customer_date > order_estimated_delivery_date
--   delivery days = purchase date to delivery date, in calendar days
--   negative      = review score of 1 or 2
--
-- Only delivered orders that have a delivery date can be assessed. Orders in
-- transit, cancelled, or delivered without a recorded date are excluded from
-- the denominator rather than counted as on time.
-- ===========================================================================


-- ============================ QUERY 18: Delivery vs satisfaction ===========
-- Business question: what does missing the promised delivery date do to the
--   customer's review?
-- Why it matters: this is the strongest relationship in the entire dataset,
--   and it is the closest thing Olist has to a quality-cost measure. It turns
--   "improve delivery" from a platitude into a quantified case.
-- Techniques: CASE WHEN classification, conditional aggregation with FILTER,
--   window function for share of total, INNER JOIN to reviews.
WITH delivered AS (
    SELECT
        o.order_id,
        r.review_score,
        DATE(o.order_delivered_customer_date) - DATE(o.order_purchase_timestamp)
                                                                AS delivery_days,
        DATE(o.order_delivered_customer_date) - DATE(o.order_estimated_delivery_date)
                                                                AS days_vs_estimate,
        SUM(oi.price)                                           AS order_revenue
    FROM orders o
    INNER JOIN order_items  oi ON oi.order_id = o.order_id
    INNER JOIN order_reviews r ON r.order_id  = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY o.order_id, r.review_score, o.order_delivered_customer_date,
             o.order_purchase_timestamp, o.order_estimated_delivery_date
)
SELECT
    CASE WHEN days_vs_estimate > 0 THEN 'Late' ELSE 'On time or early' END
                                                                AS delivery_outcome,
    COUNT(*)                                                    AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)          AS pct_of_orders,
    ROUND(AVG(review_score), 3)                                 AS avg_review_score,
    ROUND(AVG(delivery_days), 1)                                AS avg_delivery_days,
    ROUND(100.0 * COUNT(*) FILTER (WHERE review_score = 1) / COUNT(*), 2)
                                                                AS one_star_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE review_score <= 2) / COUNT(*), 2)
                                                                AS negative_review_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE review_score = 5) / COUNT(*), 2)
                                                                AS five_star_rate_pct,
    ROUND(SUM(order_revenue), 2)                                AS revenue
FROM delivered
GROUP BY 1
ORDER BY avg_review_score DESC;


-- ============================ QUERY 19: Where the satisfaction cliff is ====
-- Business question: does the review score decline gradually with lateness, or
--   fall off a cliff at the promised date?
-- Why it matters: the shape determines the operational target. A gradual slope
--   would mean "be faster"; a cliff means "beat the promised date, by any
--   margin" - a completely different instruction to a logistics team.
-- Techniques: CASE WHEN banding on a signed day difference, ordered banding
--   with a sort key, aggregation with FILTER.
WITH delivered AS (
    SELECT
        o.order_id,
        r.review_score,
        DATE(o.order_delivered_customer_date) - DATE(o.order_estimated_delivery_date)
                                                        AS days_vs_estimate,
        DATE(o.order_delivered_customer_date) - DATE(o.order_purchase_timestamp)
                                                        AS delivery_days
    FROM orders o
    INNER JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
),
banded AS (
    SELECT
        CASE
            WHEN days_vs_estimate <= -15 THEN '15+ days early'
            WHEN days_vs_estimate <=  -7 THEN '7-14 days early'
            WHEN days_vs_estimate <=  -3 THEN '3-6 days early'
            WHEN days_vs_estimate <=   0 THEN '0-2 days early'
            WHEN days_vs_estimate <=   3 THEN '1-3 days late'
            WHEN days_vs_estimate <=   7 THEN '4-7 days late'
            WHEN days_vs_estimate <=  15 THEN '8-15 days late'
            ELSE '15+ days late'
        END AS lateness_band,
        CASE
            WHEN days_vs_estimate <= -15 THEN 1
            WHEN days_vs_estimate <=  -7 THEN 2
            WHEN days_vs_estimate <=  -3 THEN 3
            WHEN days_vs_estimate <=   0 THEN 4
            WHEN days_vs_estimate <=   3 THEN 5
            WHEN days_vs_estimate <=   7 THEN 6
            WHEN days_vs_estimate <=  15 THEN 7
            ELSE 8
        END AS band_sort,
        review_score,
        delivery_days
    FROM delivered
)
SELECT
    lateness_band,
    COUNT(*)                                                     AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)           AS pct_of_orders,
    ROUND(AVG(review_score), 3)                                  AS avg_review_score,
    ROUND(100.0 * COUNT(*) FILTER (WHERE review_score = 1) / COUNT(*), 2)
                                                                 AS one_star_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE review_score <= 2) / COUNT(*), 2)
                                                                 AS negative_review_rate_pct,
    ROUND(AVG(delivery_days), 1)                                 AS avg_delivery_days,
    -- The drop against the previous (less late) band, which is what makes the
    -- cliff visible in a single column.
    ROUND(AVG(review_score)
          - LAG(AVG(review_score)) OVER (ORDER BY MIN(band_sort)), 3)
                                                                 AS change_vs_prev_band
FROM banded
GROUP BY lateness_band
ORDER BY MIN(band_sort);


-- ============================ QUERY 20: Sellers with a delivery problem ====
-- Business question: which sellers are materially less reliable than the rest
--   of the marketplace?
-- Why it matters: Olist does not control fulfilment, so a seller with a high
--   late rate is one of the few operational levers the platform actually has.
--   This is the marketplace equivalent of a product-level returns problem.
-- Techniques: HAVING for a minimum sample size, scalar subquery for the market
--   benchmark, ratio comparison, CASE WHEN severity banding.
WITH seller_delivery AS (
    SELECT
        oi.seller_id,
        s.seller_state,
        COUNT(DISTINCT o.order_id)                                    AS orders,
        AVG(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1.0 ELSE 0.0 END)                               AS late_rate,
        AVG(DATE(o.order_delivered_customer_date)
            - DATE(o.order_purchase_timestamp))                       AS avg_delivery_days,
        AVG(r.review_score)                                           AS avg_review_score,
        SUM(oi.price)                                                 AS revenue
    FROM orders o
    INNER JOIN order_items  oi ON oi.order_id = o.order_id
    INNER JOIN sellers      s  ON s.seller_id = oi.seller_id
    LEFT  JOIN order_reviews r ON r.order_id  = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY oi.seller_id, s.seller_state
    -- Below 50 delivered orders a single late parcel moves the rate by two
    -- points, so smaller sellers cannot be judged fairly.
    HAVING COUNT(DISTINCT o.order_id) >= 50
),
market AS (
    SELECT
        AVG(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1.0 ELSE 0.0 END) AS market_late_rate,
        AVG(r.review_score)             AS market_review_score
    FROM orders o
    LEFT JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
)
SELECT
    sd.seller_id,
    sd.seller_state,
    sd.orders,
    ROUND(100.0 * sd.late_rate, 2)                        AS late_rate_pct,
    ROUND(100.0 * m.market_late_rate, 2)                  AS market_late_rate_pct,
    ROUND(sd.late_rate / NULLIF(m.market_late_rate, 0), 2) AS late_vs_market_multiple,
    ROUND(sd.avg_delivery_days, 1)                        AS avg_delivery_days,
    ROUND(sd.avg_review_score, 3)                         AS avg_review_score,
    ROUND(sd.avg_review_score - m.market_review_score, 3) AS score_vs_market,
    ROUND(sd.revenue, 2)                                  AS revenue,
    CASE
        WHEN sd.late_rate > m.market_late_rate * 2.0 THEN 'severe - review seller'
        WHEN sd.late_rate > m.market_late_rate * 1.5 THEN 'elevated - monitor'
        ELSE 'within norm'
    END                                                   AS severity
FROM seller_delivery sd
CROSS JOIN market m
WHERE sd.late_rate > m.market_late_rate * 1.5
ORDER BY sd.revenue DESC
LIMIT 25;


-- ============================ QUERY 21: Delivery performance over time =====
-- Business question: is delivery reliability improving or deteriorating?
-- Why it matters: cohorted on the month the order was PLACED, not the month it
--   arrived. Cohorting on arrival would make a spike in late deliveries simply
--   follow the previous month's sales spike and say nothing about capacity.
-- Techniques: DATE_TRUNC, LAG for month-on-month change, conditional
--   aggregation, moving average window.
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date        AS order_month,
        COUNT(DISTINCT o.order_id)                                   AS delivered_orders,
        AVG(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1.0 ELSE 0.0 END)                              AS late_rate,
        AVG(DATE(o.order_delivered_customer_date)
            - DATE(o.order_purchase_timestamp))                      AS avg_delivery_days,
        AVG(r.review_score)                                          AS avg_review_score,
        AVG(CASE WHEN r.review_score <= 2 THEN 1.0 ELSE 0.0 END)     AS negative_review_rate
    FROM orders o
    LEFT JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY DATE_TRUNC('month', o.order_purchase_timestamp)
)
SELECT
    order_month,
    delivered_orders,
    ROUND(100.0 * late_rate, 2)                                      AS late_rate_pct,
    ROUND(100.0 * late_rate - LAG(100.0 * late_rate) OVER (ORDER BY order_month), 2)
                                                                     AS change_vs_prev_month_pp,
    ROUND(AVG(100.0 * late_rate) OVER (ORDER BY order_month
                                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2)
                                                                     AS late_rate_3m_avg,
    ROUND(avg_delivery_days, 1)                                      AS avg_delivery_days,
    ROUND(avg_review_score, 3)                                       AS avg_review_score,
    ROUND(100.0 * negative_review_rate, 2)                           AS negative_review_rate_pct
FROM monthly
ORDER BY order_month;


-- ============================ QUERY 22: Review score distribution ==========
-- Business question: how are the 1-5 scores distributed, and what revenue sits
--   behind each?
-- Why it matters: an average of 4.1 could be everyone giving 4, or most giving
--   5 and a large minority giving 1. It is the latter here, which means the
--   business has a polarised experience rather than a mediocre one - and that
--   points at a specific failure mode rather than general quality.
-- Techniques: GROUP BY on the score, window function for share, LEFT JOIN to
--   the delivery facts.
WITH reviewed AS (
    SELECT
        o.order_id,
        r.review_score,
        SUM(oi.price)                                                AS order_revenue,
        MAX(DATE(o.order_delivered_customer_date)
            - DATE(o.order_purchase_timestamp))                      AS delivery_days,
        MAX(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1 ELSE 0 END)                                  AS is_late
    FROM orders o
    INNER JOIN order_items  oi ON oi.order_id = o.order_id
    INNER JOIN order_reviews r ON r.order_id  = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY o.order_id, r.review_score
)
SELECT
    review_score,
    COUNT(*)                                                   AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)         AS pct_of_orders,
    ROUND(SUM(order_revenue), 2)                               AS revenue,
    ROUND(100.0 * SUM(order_revenue) / SUM(SUM(order_revenue)) OVER (), 2)
                                                               AS pct_of_revenue,
    ROUND(AVG(order_revenue), 2)                               AS avg_order_value,
    ROUND(AVG(delivery_days), 1)                               AS avg_delivery_days,
    ROUND(100.0 * AVG(is_late), 2)                             AS late_rate_pct,
    -- Running share, so "what fraction of orders score 3 or less" is readable
    -- straight off the table.
    ROUND(100.0 * SUM(COUNT(*)) OVER (ORDER BY review_score ROWS UNBOUNDED PRECEDING)
          / SUM(COUNT(*)) OVER (), 2)                          AS cumulative_pct_of_orders
FROM reviewed
GROUP BY review_score
ORDER BY review_score;


-- ============================ QUERY 23: Regional performance ===============
-- Business question: how do the five regions compare on revenue, freight
--   burden, delivery time and satisfaction?
-- Why it matters: this is the query that shows the distance penalty as one
--   coherent picture - the further from the seller cluster, the more the
--   customer pays, the longer they wait and the lower they rate. Each of those
--   alone is a statistic; together they are a strategy problem.
-- Techniques: three independently-scoped CTEs joined together, conditional
--   aggregation, window share.
WITH regional_orders AS (
    SELECT
        c.customer_region,
        COUNT(DISTINCT o.order_id)                                    AS all_orders,
        COUNT(DISTINCT c.customer_unique_id)                          AS customers,
        COUNT(DISTINCT o.order_id) FILTER (
            WHERE o.order_status IN ('canceled', 'unavailable'))      AS unfulfilled_orders
    FROM orders o
    INNER JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_region
),
regional_revenue AS (
    SELECT
        c.customer_region,
        COUNT(DISTINCT o.order_id) AS orders,
        COUNT(*)                   AS units,
        SUM(oi.price)              AS product_revenue,
        SUM(oi.freight_value)      AS freight_revenue,
        AVG(oi.price)              AS avg_item_price
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_region
),
regional_delivery AS (
    SELECT
        c.customer_region,
        AVG(DATE(o.order_delivered_customer_date)
            - DATE(o.order_purchase_timestamp))                  AS avg_delivery_days,
        AVG(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1.0 ELSE 0.0 END)                          AS late_rate,
        AVG(r.review_score)                                      AS avg_review_score,
        AVG(CASE WHEN r.review_score <= 2 THEN 1.0 ELSE 0.0 END) AS negative_review_rate
    FROM orders o
    INNER JOIN customers    c  ON c.customer_id = o.customer_id
    LEFT  JOIN order_reviews r ON r.order_id    = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_region
)
SELECT
    ro.customer_region,
    ro.customers,
    rr.orders,
    ROUND(rr.product_revenue, 2)                                     AS product_revenue,
    ROUND(100.0 * rr.product_revenue / SUM(rr.product_revenue) OVER (), 2)
                                                                     AS pct_of_revenue,
    ROUND(rr.product_revenue / NULLIF(rr.orders, 0), 2)              AS avg_order_value,
    ROUND(rr.product_revenue / NULLIF(ro.customers, 0), 2)           AS revenue_per_customer,
    ROUND(rr.avg_item_price, 2)                                      AS avg_item_price,
    ROUND(rr.freight_revenue / NULLIF(rr.units, 0), 2)               AS avg_freight_per_item,
    ROUND(100.0 * rr.freight_revenue / NULLIF(rr.product_revenue, 0), 2)
                                                                     AS freight_to_price_pct,
    ROUND(rd.avg_delivery_days, 1)                                   AS avg_delivery_days,
    ROUND(100.0 * rd.late_rate, 2)                                   AS late_rate_pct,
    ROUND(rd.avg_review_score, 3)                                    AS avg_review_score,
    ROUND(100.0 * rd.negative_review_rate, 2)                        AS negative_review_rate_pct,
    ROUND(100.0 * ro.unfulfilled_orders / NULLIF(ro.all_orders, 0), 2)
                                                                     AS unfulfilled_rate_pct
FROM regional_orders ro
LEFT JOIN regional_revenue  rr ON rr.customer_region = ro.customer_region
LEFT JOIN regional_delivery rd ON rd.customer_region = ro.customer_region
ORDER BY rr.product_revenue DESC;


-- ============================ QUERY 24: How deep does a serious delay cut? =
-- Business question: the on-time versus late split reports a 2.0-point gap in
--   review score. Does that understate what a serious delay does?
-- Why it matters: "late" is dominated by orders that missed the promised date
--   by a day or two. Averaging those together with the parcels that turned up
--   two weeks after the promise hides how far the score actually falls, and
--   the two cases need different operational responses.
-- Technique: conditional aggregation with FILTER, which reads closer to the
--   intent than SUM(CASE WHEN ...) and lets several populations be measured in
--   a single pass over the table.
WITH delivered AS (
    SELECT
        o.order_id,
        r.review_score,
        DATE(o.order_delivered_customer_date)
            - DATE(o.order_estimated_delivery_date)          AS days_vs_estimate,
        DATE(o.order_delivered_customer_date)
            - DATE(o.order_purchase_timestamp)               AS delivery_days
    FROM orders o
    INNER JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
),
median_days AS (
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delivery_days) AS median_days
    FROM delivered
)
SELECT
    COUNT(*) FILTER (WHERE days_vs_estimate <= 0)               AS on_time_orders,
    ROUND(AVG(review_score) FILTER (WHERE days_vs_estimate <= 0)::numeric, 3)
                                                               AS on_time_score,
    COUNT(*) FILTER (WHERE days_vs_estimate > 0)                AS late_orders,
    ROUND(AVG(review_score) FILTER (WHERE days_vs_estimate > 0)::numeric, 3)
                                                               AS late_score,
    COUNT(*) FILTER (WHERE days_vs_estimate > 7)                AS over_a_week_late,
    ROUND(AVG(review_score) FILTER (WHERE days_vs_estimate > 7)::numeric, 3)
                                                               AS over_a_week_score,
    -- The headline: how far the score falls once the delay is serious.
    ROUND(
        (AVG(review_score) FILTER (WHERE days_vs_estimate <= 0)
         - AVG(review_score) FILTER (WHERE days_vs_estimate > 7))::numeric, 2
    )                                                          AS drop_when_over_a_week,
    -- Read the other way round: what explains the one-star population.
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE review_score = 1 AND days_vs_estimate > 0)
        / NULLIF(COUNT(*) FILTER (WHERE days_vs_estimate > 0), 0), 1
    )                                                          AS pct_of_late_rated_one_star,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE review_score = 1 AND days_vs_estimate > 0)
        / NULLIF(COUNT(*) FILTER (WHERE review_score = 1), 0), 1
    )                                                          AS pct_of_one_star_that_was_late,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE review_score = 1 AND delivery_days > (SELECT median_days FROM median_days)
        ) / NULLIF(COUNT(*) FILTER (WHERE review_score = 1), 0), 1
    )                                                          AS pct_of_one_star_slower_than_median
FROM delivered;
