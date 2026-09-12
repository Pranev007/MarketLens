-- ===========================================================================
-- MarketLens - Customer behaviour and segmentation (Olist)
-- ===========================================================================
-- THE SINGLE MOST IMPORTANT JOIN IN THIS PROJECT
--
-- customers.customer_id is issued per ORDER. customers.customer_unique_id is
-- the person. 99,441 customer_id values resolve to 96,096 people.
--
-- Every query in this file groups on customer_unique_id. Query 12 demonstrates
-- what happens if you do not: the repeat purchase rate comes out at exactly
-- 0.00%, which reads as a catastrophic business failure and is actually a join
-- error. It is the defining trap of this dataset.
--
-- Recency is measured against the newest order in the data rather than
-- CURRENT_DATE. Olist ends in 2018, so wall-clock recency would put every
-- customer in the same bucket and make the segmentation meaningless.
-- ===========================================================================


-- ============================ QUERY 06: The customer_id trap ===============
-- Business question: how many customers does this marketplace actually have,
--   and how many of them come back?
-- Why it matters: this is the query that decides whether every downstream
--   customer number is right or worthless. Computing the same metric both ways
--   in one result makes the difference impossible to miss, and documents why
--   the rest of the file keys on customer_unique_id.
-- Techniques: two independent CTEs over the same population, COUNT(DISTINCT),
--   scalar subqueries, deliberate side-by-side comparison.
WITH revenue_orders AS (
    SELECT
        o.order_id,
        c.customer_id,
        c.customer_unique_id,
        SUM(oi.price) AS order_revenue
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY o.order_id, c.customer_id, c.customer_unique_id
),
by_person AS (
    SELECT customer_unique_id, COUNT(*) AS orders, SUM(order_revenue) AS revenue
    FROM revenue_orders
    GROUP BY customer_unique_id
),
by_account AS (
    SELECT customer_id, COUNT(*) AS orders
    FROM revenue_orders
    GROUP BY customer_id
)
SELECT
    (SELECT COUNT(*) FROM by_person)                                AS unique_customers,
    (SELECT COUNT(*) FROM by_account)                               AS customer_accounts,
    (SELECT COUNT(*) FROM revenue_orders)                           AS orders,

    -- The correct calculation.
    (SELECT COUNT(*) FROM by_person WHERE orders >= 2)              AS repeat_customers,
    ROUND(100.0 * (SELECT COUNT(*) FROM by_person WHERE orders >= 2)
          / NULLIF((SELECT COUNT(*) FROM by_person), 0), 2)         AS repeat_rate_pct,

    -- The same calculation keyed on the per-order id. Always 0.00, because a
    -- customer_id cannot appear on two orders by construction.
    ROUND(100.0 * (SELECT COUNT(*) FROM by_account WHERE orders >= 2)
          / NULLIF((SELECT COUNT(*) FROM by_account), 0), 2)        AS repeat_rate_if_keyed_on_customer_id,

    ROUND((SELECT AVG(orders) FROM by_person), 4)                   AS avg_orders_per_customer,
    (SELECT MAX(orders) FROM by_person)                             AS max_orders_by_one_customer,
    ROUND(
        100.0 * (SELECT SUM(revenue) FROM by_person WHERE orders >= 2)
        / NULLIF((SELECT SUM(revenue) FROM by_person), 0), 2
    )                                                               AS pct_revenue_from_repeat_customers;


-- ============================ QUERY 07: Purchase frequency distribution ====
-- Business question: how is the customer base distributed across order counts,
--   and how much revenue sits in each band?
-- Why it matters: an average of 1.03 orders per customer could describe a base
--   where everyone buys once, or one where most buy once and a few buy often.
--   The distribution shows which - and here it is overwhelmingly the former.
-- Techniques: CASE WHEN banding, GROUP BY on the derived band, window function
--   for share.
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT o.order_id) AS orders,
        SUM(oi.price)              AS revenue
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_unique_id
),
banded AS (
    SELECT
        CASE
            WHEN orders = 1 THEN '1 order'
            WHEN orders = 2 THEN '2 orders'
            WHEN orders = 3 THEN '3 orders'
            WHEN orders BETWEEN 4 AND 5 THEN '4-5 orders'
            ELSE '6+ orders'
        END          AS frequency_band,
        MIN(orders)  AS band_sort,
        COUNT(*)     AS customers,
        SUM(orders)  AS orders,
        SUM(revenue) AS revenue
    FROM customer_orders
    GROUP BY 1
)
SELECT
    frequency_band,
    customers,
    orders,
    ROUND(revenue, 2)                                            AS revenue,
    ROUND(100.0 * customers / SUM(customers) OVER (), 2)         AS pct_of_customers,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 2)             AS pct_of_revenue,
    ROUND(revenue / NULLIF(customers, 0), 2)                     AS revenue_per_customer,
    ROUND(revenue / NULLIF(orders, 0), 2)                        AS avg_order_value
FROM banded
ORDER BY band_sort;


-- ============================ QUERY 08: Customer revenue concentration =====
-- Business question: what share of revenue comes from the top 1%, 5%, 10% and
--   20% of customers?
-- Why it matters: concentration is a risk measure and a targeting guide. This
--   marketplace turns out to be unusually FLAT - because almost everyone buys
--   exactly once, revenue is spread thinly, which means there is no small
--   group worth building a retention programme around.
-- Techniques: NTILE(100) for percentiles, cumulative SUM() OVER, and the
--   filter applied one level OUT - WHERE is evaluated before window functions,
--   so filtering in the same SELECT would make each running total cover only
--   the surviving rows.
WITH customer_revenue AS (
    SELECT
        c.customer_unique_id,
        SUM(oi.price) AS lifetime_revenue
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_unique_id
),
percentiled AS (
    SELECT
        customer_unique_id,
        lifetime_revenue,
        NTILE(100) OVER (ORDER BY lifetime_revenue DESC) AS revenue_percentile
    FROM customer_revenue
),
per_percentile AS (
    SELECT
        revenue_percentile,
        COUNT(*)              AS customers,
        SUM(lifetime_revenue) AS revenue
    FROM percentiled
    GROUP BY revenue_percentile
),
cumulative AS (
    SELECT
        revenue_percentile,
        SUM(customers) OVER (ORDER BY revenue_percentile ROWS UNBOUNDED PRECEDING)
                                             AS cumulative_customers,
        SUM(revenue)   OVER (ORDER BY revenue_percentile ROWS UNBOUNDED PRECEDING)
                                             AS cumulative_revenue,
        SUM(revenue)   OVER ()               AS total_revenue
    FROM per_percentile
)
SELECT
    revenue_percentile           AS top_n_percent,
    cumulative_customers,
    ROUND(cumulative_revenue, 2) AS cumulative_revenue,
    ROUND(100.0 * cumulative_revenue / NULLIF(total_revenue, 0), 2)
                                 AS cumulative_pct_of_revenue
FROM cumulative
WHERE revenue_percentile IN (1, 5, 10, 20, 50, 100)
ORDER BY revenue_percentile;


-- ============================ QUERY 09: RFM segmentation ===================
-- Business question: which customers are worth spending money on, and what
--   should be done with each group?
-- Why it matters: RFM turns a flat customer list into groups a marketing team
--   can treat differently.
--
-- Methodology, stated so it can be challenged:
--   Recency   - days between the customer's last order and the newest order in
--               the dataset. Lower is better.
--   Frequency - distinct revenue-bearing orders.
--   Monetary  - lifetime product revenue.
--   R and M are scored 1-5 with NTILE, so the scores are quintiles of THIS
--   base rather than thresholds borrowed from another business.
--
--   The honest caveat: 97% of these customers have exactly one order, so
--   Frequency carries almost no information and quintiles on it are close to
--   meaningless. The segment rules therefore branch on the RAW order count and
--   lean on Recency and Monetary. That is a property of the business, not a
--   flaw in the method - and it is why these segment names differ from a
--   textbook RFM scheme.
-- Techniques: NTILE for quintile scoring, subquery for the dataset anchor
--   date, nested CTEs, CASE WHEN with compound conditions.
WITH dataset_anchor AS (
    SELECT MAX(order_purchase_timestamp) AS as_of
    FROM orders
    WHERE order_status NOT IN ('canceled', 'unavailable')
      AND order_purchase_timestamp < DATE '2018-09-01'
),
customer_rfm AS (
    SELECT
        c.customer_unique_id,
        DATE((SELECT as_of FROM dataset_anchor))
            - DATE(MAX(o.order_purchase_timestamp))  AS recency_days,
        COUNT(DISTINCT o.order_id)                   AS frequency,
        SUM(oi.price)                                AS monetary
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY c.customer_unique_id
),
scored AS (
    SELECT
        *,
        -- Reversed: the most recent fifth of customers scores 5.
        NTILE(5) OVER (ORDER BY recency_days DESC)  AS r_score,
        NTILE(5) OVER (ORDER BY monetary ASC)       AS m_score
    FROM customer_rfm
),
segmented AS (
    SELECT
        *,
        CASE
            WHEN frequency >= 2 AND r_score >= 4 AND m_score >= 4 THEN 'Champions'
            WHEN frequency >= 2 AND r_score <= 2                  THEN 'Repeat - At Risk'
            WHEN frequency >= 2                                   THEN 'Repeat'
            WHEN frequency = 1 AND m_score = 5 AND r_score >= 3    THEN 'High-Value One-Off'
            WHEN frequency = 1 AND r_score >= 4                    THEN 'Recent One-Off'
            WHEN frequency = 1 AND r_score <= 2 AND m_score >= 4   THEN 'Lapsed - Higher Value'
            WHEN frequency = 1 AND r_score <= 2                    THEN 'Lapsed - Low Value'
            ELSE 'Single Purchase - Mid'
        END AS segment
    FROM scored
)
SELECT
    segment,
    COUNT(*)                                                   AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)         AS pct_of_customers,
    ROUND(AVG(recency_days), 0)                                AS avg_recency_days,
    ROUND(AVG(frequency), 3)                                   AS avg_orders,
    ROUND(AVG(monetary), 2)                                    AS avg_lifetime_revenue,
    ROUND(SUM(monetary), 2)                                    AS segment_revenue,
    ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 2) AS pct_of_revenue,
    -- Above 1 means the segment carries more revenue than its size implies.
    ROUND(
        (SUM(monetary) / SUM(SUM(monetary)) OVER ())
        / NULLIF(COUNT(*)::numeric / SUM(COUNT(*)) OVER (), 0), 2
    )                                                          AS revenue_concentration_index
FROM segmented
GROUP BY segment
ORDER BY segment_revenue DESC;
