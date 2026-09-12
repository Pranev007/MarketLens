-- ===========================================================================
-- MarketLens - Revenue and KPI analysis (Olist)
-- ===========================================================================
-- Definitions applied consistently across every query in this repository:
--
--   product revenue = SUM(oi.price)          -- the goods
--   freight revenue = SUM(oi.freight_value)  -- what shipping was charged at
--   GMV             = product revenue + freight revenue
--   units           = COUNT(*) on order_items -- there is NO quantity column
--   revenue-bearing = order_status NOT IN ('canceled', 'unavailable')
--   AOV             = product revenue / distinct revenue-bearing orders
--
-- REPORTING WINDOW: 2017-01-01 to 2018-08-31.
-- Olist spans Sep 2016 to Oct 2018, but the tails are not real trading months
-- (Sep 2016 has 4 orders, Dec 2016 has 1, Oct 2018 has 4). Including them
-- produces month-over-month growth rates in the thousands of percent. The
-- window holds 99.65% of all orders. Every query below applies it explicitly.
--
-- Olist carries no cost price, so there is no margin analysis anywhere in this
-- project. Freight is analysed instead - it is the one cost the data exposes.
-- ===========================================================================


-- ============================ QUERY 01: Headline KPIs ======================
-- Business question: what are the marketplace's top-line numbers for the
--   reporting period?
-- Why it matters: this is the row an executive summary is built from, and
--   every other query has to reconcile to it. Computing the KPIs in one pass
--   guarantees orders, revenue and AOV are measured on the same population
--   rather than drifting apart across separate queries.
-- Techniques: CTEs, COUNT(DISTINCT), aggregate FILTER, LEFT JOIN.
WITH order_revenue AS (
    -- Roll order lines up to one row per order FIRST. Aggregating revenue and
    -- counting orders in the same pass over the line table would multiply the
    -- order count by basket size.
    SELECT
        o.order_id,
        c.customer_unique_id,          -- the person, not the per-order id
        o.order_status,
        COUNT(*)                  AS units,
        SUM(oi.price)             AS product_revenue,
        SUM(oi.freight_value)     AS freight_revenue
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY o.order_id, c.customer_unique_id, o.order_status
),
-- Orders with no line items exist (almost all 'unavailable' or 'canceled')
-- and must still be counted in the order and cancellation totals.
all_orders AS (
    SELECT o.order_id, o.order_status, c.customer_unique_id
    FROM orders o
    INNER JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
),
delivery AS (
    SELECT
        o.order_id,
        DATE(o.order_delivered_customer_date) - DATE(o.order_purchase_timestamp)
                                                          AS delivery_days,
        DATE(o.order_delivered_customer_date) - DATE(o.order_estimated_delivery_date)
                                                          AS days_vs_estimate
    FROM orders o
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
),
reviews AS (
    SELECT r.order_id, r.review_score
    FROM order_reviews r
    INNER JOIN orders o ON o.order_id = r.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
)
SELECT
    (SELECT COUNT(*) FROM all_orders)                                AS total_orders,
    (SELECT COUNT(*) FROM all_orders WHERE order_status = 'delivered')
                                                                     AS delivered_orders,
    (SELECT COUNT(*) FROM all_orders WHERE order_status = 'canceled')
                                                                     AS cancelled_orders,
    (SELECT COUNT(*) FROM all_orders WHERE order_status = 'unavailable')
                                                                     AS unavailable_orders,
    ROUND(
        100.0 * (SELECT COUNT(*) FROM all_orders WHERE order_status = 'canceled')
        / NULLIF((SELECT COUNT(*) FROM all_orders), 0), 2
    )                                                                AS cancellation_rate_pct,
    ROUND(
        100.0 * (SELECT COUNT(*) FROM all_orders
                 WHERE order_status IN ('canceled', 'unavailable'))
        / NULLIF((SELECT COUNT(*) FROM all_orders), 0), 2
    )                                                                AS unfulfilled_rate_pct,

    -- The person, not the per-order id. Using customer_id here would report
    -- one customer per order and a repeat rate of exactly zero.
    COUNT(DISTINCT customer_unique_id) FILTER (
        WHERE order_status NOT IN ('canceled', 'unavailable'))       AS unique_customers,
    COUNT(*) FILTER (WHERE order_status NOT IN ('canceled', 'unavailable'))
                                                                     AS revenue_orders,

    ROUND(SUM(product_revenue) FILTER (
        WHERE order_status NOT IN ('canceled', 'unavailable')), 2)   AS product_revenue,
    ROUND(SUM(freight_revenue) FILTER (
        WHERE order_status NOT IN ('canceled', 'unavailable')), 2)   AS freight_revenue,
    ROUND(SUM(product_revenue + freight_revenue) FILTER (
        WHERE order_status NOT IN ('canceled', 'unavailable')), 2)   AS gmv,
    ROUND(
        100.0 * SUM(freight_revenue) FILTER (
            WHERE order_status NOT IN ('canceled', 'unavailable'))
        / NULLIF(SUM(product_revenue + freight_revenue) FILTER (
            WHERE order_status NOT IN ('canceled', 'unavailable')), 0), 2
    )                                                                AS freight_share_of_gmv_pct,

    ROUND(
        SUM(product_revenue) FILTER (WHERE order_status NOT IN ('canceled', 'unavailable'))
        / NULLIF(COUNT(*) FILTER (
            WHERE order_status NOT IN ('canceled', 'unavailable')), 0), 2
    )                                                                AS avg_order_value,
    ROUND(
        SUM(units) FILTER (WHERE order_status NOT IN ('canceled', 'unavailable'))::numeric
        / NULLIF(COUNT(*) FILTER (
            WHERE order_status NOT IN ('canceled', 'unavailable')), 0), 2
    )                                                                AS avg_items_per_order,
    ROUND(
        SUM(product_revenue) FILTER (WHERE order_status NOT IN ('canceled', 'unavailable'))
        / NULLIF(COUNT(DISTINCT customer_unique_id) FILTER (
            WHERE order_status NOT IN ('canceled', 'unavailable')), 0), 2
    )                                                                AS revenue_per_customer,

    (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE days_vs_estimate > 0)
                  / NULLIF(COUNT(*), 0), 2) FROM delivery)           AS late_delivery_rate_pct,
    (SELECT ROUND(AVG(delivery_days), 1) FROM delivery)              AS avg_delivery_days,
    (SELECT ROUND(AVG(review_score), 3) FROM reviews)                AS avg_review_score,
    (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE review_score <= 2)
                  / NULLIF(COUNT(*), 0), 2) FROM reviews)            AS negative_review_rate_pct
FROM order_revenue;


-- ============================ QUERY 02: Monthly revenue trend ==============
-- Business question: how did revenue, orders and basket value move month by
--   month?
-- Why it matters: the monthly series is the backbone of every performance
--   conversation. Splitting revenue into orders x AOV in the same table shows
--   immediately whether a good month came from more baskets or bigger ones -
--   which for this marketplace turns out to be the whole story.
-- Techniques: DATE_TRUNC, GROUP BY, window functions for share and ranking.
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
        COUNT(DISTINCT o.order_id)                            AS orders,
        COUNT(DISTINCT c.customer_unique_id)                  AS customers,
        COUNT(*)                                              AS units,
        SUM(oi.price)                                         AS product_revenue,
        SUM(oi.freight_value)                                 AS freight_revenue
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY DATE_TRUNC('month', o.order_purchase_timestamp)
)
SELECT
    month,
    orders,
    customers,
    units,
    ROUND(product_revenue, 2)                                  AS product_revenue,
    ROUND(freight_revenue, 2)                                  AS freight_revenue,
    ROUND(product_revenue / NULLIF(orders, 0), 2)              AS avg_order_value,
    ROUND(units::numeric / NULLIF(orders, 0), 2)               AS items_per_order,
    ROUND(100.0 * freight_revenue / NULLIF(product_revenue + freight_revenue, 0), 2)
                                                               AS freight_share_pct,
    ROUND(100.0 * product_revenue / SUM(product_revenue) OVER (), 2)
                                                               AS pct_of_total_revenue,
    RANK() OVER (ORDER BY product_revenue DESC)                AS revenue_rank
FROM monthly
ORDER BY month;


-- ============================ QUERY 03: Month-over-month growth ============
-- Business question: what is the growth rate, and is it accelerating?
-- Why it matters: absolute revenue hides the trend. LAG puts the previous
--   month on the current row so growth can be computed in SQL rather than in a
--   spreadsheet, and LAG(12) gives the same month a year earlier - the only
--   fair comparison once seasonality exists.
-- Techniques: LAG(), window frames, running total with SUM() OVER, CASE WHEN.
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
        COUNT(DISTINCT o.order_id)                            AS orders,
        SUM(oi.price)                                         AS product_revenue
    FROM orders o
    INNER JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY DATE_TRUNC('month', o.order_purchase_timestamp)
),
with_lags AS (
    SELECT
        month,
        orders,
        product_revenue,
        LAG(product_revenue, 1)  OVER (ORDER BY month) AS prev_month_revenue,
        LAG(product_revenue, 12) OVER (ORDER BY month) AS same_month_last_year,
        LAG(orders, 1)           OVER (ORDER BY month) AS prev_month_orders,
        SUM(product_revenue) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING)
                                                       AS running_revenue,
        AVG(product_revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
                                                       AS revenue_3m_moving_avg
    FROM monthly
)
SELECT
    month,
    orders,
    ROUND(product_revenue, 2)       AS product_revenue,
    ROUND(running_revenue, 2)       AS running_revenue,
    ROUND(revenue_3m_moving_avg, 2) AS revenue_3m_moving_avg,
    ROUND(100.0 * (product_revenue - prev_month_revenue)
          / NULLIF(prev_month_revenue, 0), 2)          AS mom_revenue_growth_pct,
    ROUND(100.0 * (orders - prev_month_orders)::numeric
          / NULLIF(prev_month_orders, 0), 2)           AS mom_order_growth_pct,
    ROUND(100.0 * (product_revenue - same_month_last_year)
          / NULLIF(same_month_last_year, 0), 2)        AS yoy_revenue_growth_pct,
    CASE
        WHEN prev_month_revenue IS NULL              THEN 'no prior month'
        WHEN product_revenue > prev_month_revenue * 1.10 THEN 'strong growth'
        WHEN product_revenue > prev_month_revenue    THEN 'growth'
        WHEN product_revenue > prev_month_revenue * 0.90 THEN 'mild decline'
        ELSE 'sharp decline'
    END                             AS mom_trend
FROM with_lags
ORDER BY month;


-- ============================ QUERY 04: Best and worst trading months ======
-- Business question: which months over- and under-performed the period
--   average?
-- Why it matters: identifies the seasonal peaks a marketplace needs to staff
--   and stock for. Brazilian retail has a November spike (Black Friday) that
--   this dataset captures clearly.
-- Techniques: subquery in FROM, window aggregate as a benchmark, HAVING,
--   ROW_NUMBER(), EXTRACT.
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
        COUNT(DISTINCT o.order_id)                            AS orders,
        SUM(oi.price)                                         AS product_revenue
    FROM orders o
    INNER JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY DATE_TRUNC('month', o.order_purchase_timestamp)
    -- Guard against a partially-loaded month distorting the comparison.
    HAVING COUNT(DISTINCT o.order_id) > 100
)
SELECT
    month,
    TO_CHAR(month, 'Mon YYYY')                    AS month_label,
    orders,
    ROUND(product_revenue, 2)                     AS product_revenue,
    ROUND(AVG(product_revenue) OVER (), 2)        AS period_avg_revenue,
    ROUND(100.0 * (product_revenue - AVG(product_revenue) OVER ())
          / AVG(product_revenue) OVER (), 2)      AS vs_period_avg_pct,
    ROW_NUMBER() OVER (ORDER BY product_revenue DESC) AS best_month_rank,
    ROW_NUMBER() OVER (ORDER BY product_revenue ASC)  AS worst_month_rank,
    CASE
        WHEN EXTRACT(MONTH FROM month) = 11 THEN 'Black Friday month'
        WHEN EXTRACT(MONTH FROM month) = 12 THEN 'Christmas'
        WHEN EXTRACT(MONTH FROM month) IN (1, 2) THEN 'post-holiday'
        ELSE 'regular trading'
    END                                           AS trading_period
FROM monthly
ORDER BY product_revenue DESC;


-- ============================ QUERY 05: Revenue composition by quarter =====
-- Business question: how does the split between goods and shipping move, and
--   what is happening to basket value?
-- Why it matters: with no cost price in the dataset there is no margin to
--   track, so freight share is the closest available read on the economics of
--   an order. A rising freight share means the marketplace is shipping more
--   cheap, bulky things - which is a different business from the one the
--   revenue line alone suggests.
-- Techniques: DATE_TRUNC to quarter, multiple CTEs, LEFT JOIN to an
--   independently-computed aggregate, arithmetic on aggregates.
WITH quarterly_lines AS (
    SELECT
        DATE_TRUNC('quarter', o.order_purchase_timestamp)::date AS quarter,
        o.order_id,
        oi.price,
        oi.freight_value
    FROM orders o
    INNER JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
),
quarterly_delivery AS (
    SELECT
        DATE_TRUNC('quarter', o.order_purchase_timestamp)::date AS quarter,
        AVG(DATE(o.order_delivered_customer_date) - DATE(o.order_purchase_timestamp))
                                                                AS avg_delivery_days,
        AVG(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date) THEN 1.0 ELSE 0.0 END)
                                                                AS late_rate,
        AVG(r.review_score)                                     AS avg_review_score
    FROM orders o
    LEFT JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY DATE_TRUNC('quarter', o.order_purchase_timestamp)
)
SELECT
    ql.quarter,
    COUNT(DISTINCT ql.order_id)                     AS orders,
    COUNT(*)                                        AS units,
    ROUND(SUM(ql.price), 2)                         AS product_revenue,
    ROUND(SUM(ql.freight_value), 2)                 AS freight_revenue,
    ROUND(SUM(ql.price + ql.freight_value), 2)      AS gmv,
    ROUND(100.0 * SUM(ql.freight_value)
          / NULLIF(SUM(ql.price + ql.freight_value), 0), 2) AS freight_share_pct,
    ROUND(SUM(ql.price) / NULLIF(COUNT(DISTINCT ql.order_id), 0), 2)
                                                    AS avg_order_value,
    ROUND(AVG(ql.price), 2)                         AS avg_item_price,
    ROUND(qd.avg_delivery_days, 1)                  AS avg_delivery_days,
    ROUND(100.0 * qd.late_rate, 2)                  AS late_delivery_rate_pct,
    ROUND(qd.avg_review_score, 3)                   AS avg_review_score
FROM quarterly_lines ql
LEFT JOIN quarterly_delivery qd ON qd.quarter = ql.quarter
GROUP BY ql.quarter, qd.avg_delivery_days, qd.late_rate, qd.avg_review_score
ORDER BY ql.quarter;
