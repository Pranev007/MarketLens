-- ===========================================================================
-- MarketLens - Product, category and seller analysis (Olist)
-- ===========================================================================
-- Olist carries no cost price, so nothing here reports margin. What it does
-- carry is the customer's own verdict - a 1-5 review score - and the freight
-- cost of moving the goods. Those are the two lenses used to separate a
-- category that sells well from one that performs well.
--
-- Categories exist at two levels: 73 leaf categories translated from the
-- Portuguese source, grouped into 8 business categories. A chart with 73 bars
-- communicates nothing, so reporting uses the group and drills to the leaf.
-- ===========================================================================


-- ============================ QUERY 13: Category performance ===============
-- Business question: which categories drive revenue, how concentrated is the
--   business on them, and what do customers think of each?
-- Why it matters: category mix decides seller recruitment and marketing spend.
--   The running cumulative share answers the Pareto question directly, and
--   pairing revenue with review score stops a big category being read as a
--   healthy one.
-- Techniques: INNER JOIN chain, LEFT JOIN to an independently-computed quality
--   aggregate, SUM() OVER () for share, running total, DENSE_RANK.
WITH category_sales AS (
    SELECT
        p.category_group,
        COUNT(DISTINCT o.order_id)           AS orders,
        COUNT(DISTINCT c.customer_unique_id) AS customers,
        COUNT(DISTINCT oi.product_id)        AS products_sold,
        COUNT(DISTINCT oi.seller_id)         AS sellers,
        COUNT(*)                             AS units,
        SUM(oi.price)                        AS product_revenue,
        SUM(oi.freight_value)                AS freight_revenue,
        AVG(oi.price)                        AS avg_item_price,
        AVG(p.product_weight_g)              AS avg_weight_g
    FROM orders o
    INNER JOIN customers   c  ON c.customer_id = o.customer_id
    INNER JOIN order_items oi ON oi.order_id   = o.order_id
    INNER JOIN products    p  ON p.product_id  = oi.product_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY p.category_group
),
category_quality AS (
    -- Delivery and satisfaction are only knowable for delivered orders that
    -- actually have a delivery date, so they are computed separately rather
    -- than being diluted by orders still in transit.
    SELECT
        p.category_group,
        AVG(r.review_score)                                            AS avg_review_score,
        AVG(DATE(o.order_delivered_customer_date)
            - DATE(o.order_purchase_timestamp))                        AS avg_delivery_days,
        AVG(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1.0 ELSE 0.0 END)                                AS late_rate,
        AVG(CASE WHEN r.review_score <= 2 THEN 1.0 ELSE 0.0 END)       AS negative_review_rate
    FROM orders o
    INNER JOIN order_items  oi ON oi.order_id  = o.order_id
    INNER JOIN products     p  ON p.product_id = oi.product_id
    LEFT  JOIN order_reviews r ON r.order_id   = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY p.category_group
)
SELECT
    cs.category_group,
    cs.orders,
    cs.customers,
    cs.products_sold,
    cs.sellers,
    cs.units,
    ROUND(cs.product_revenue, 2)                                  AS product_revenue,
    ROUND(cs.avg_item_price, 2)                                   AS avg_item_price,
    ROUND(100.0 * cs.product_revenue / SUM(cs.product_revenue) OVER (), 2)
                                                                  AS pct_of_revenue,
    ROUND(
        100.0 * SUM(cs.product_revenue) OVER (ORDER BY cs.product_revenue DESC
                                              ROWS UNBOUNDED PRECEDING)
        / SUM(cs.product_revenue) OVER (), 2
    )                                                             AS cumulative_pct,
    ROUND(100.0 * cs.freight_revenue
          / NULLIF(cs.product_revenue + cs.freight_revenue, 0), 2) AS freight_share_pct,
    ROUND(cs.avg_weight_g, 0)                                     AS avg_weight_g,
    ROUND(cq.avg_review_score, 3)                                 AS avg_review_score,
    ROUND(100.0 * cq.negative_review_rate, 2)                     AS negative_review_rate_pct,
    ROUND(100.0 * cq.late_rate, 2)                                AS late_delivery_rate_pct,
    ROUND(cq.avg_delivery_days, 1)                                AS avg_delivery_days,
    DENSE_RANK() OVER (ORDER BY cs.product_revenue DESC)          AS revenue_rank
FROM category_sales cs
LEFT JOIN category_quality cq ON cq.category_group = cs.category_group
ORDER BY cs.product_revenue DESC;


-- ============================ QUERY 14: Revenue rank vs satisfaction rank ==
-- Business question: do the categories that sell the most also leave customers
--   happiest?
-- Why it matters: with no cost data there is no "big on revenue, thin on
--   profit" analysis to run - but there is an equivalent. A category ranking
--   far worse on the customer's verdict than on revenue is one where growth is
--   being bought at the cost of experience, and the rank gap makes that
--   visible rather than asserted.
-- Techniques: two independent RANK() windows compared against each other,
--   CASE WHEN interpretation, LEFT JOIN.
WITH category_metrics AS (
    SELECT
        p.category_group,
        SUM(oi.price)                                              AS product_revenue,
        COUNT(*)                                                   AS units,
        AVG(r.review_score)                                        AS avg_review_score,
        AVG(CASE WHEN r.review_score <= 2 THEN 1.0 ELSE 0.0 END)   AS negative_review_rate,
        AVG(CASE WHEN o.order_delivered_customer_date IS NOT NULL
                  AND DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1.0 ELSE 0.0 END)                            AS late_rate,
        SUM(oi.freight_value) / NULLIF(SUM(oi.price), 0)           AS freight_to_price
    FROM orders o
    INNER JOIN order_items  oi ON oi.order_id  = o.order_id
    INNER JOIN products     p  ON p.product_id = oi.product_id
    LEFT  JOIN order_reviews r ON r.order_id   = o.order_id
    -- Delivered only, matching query 06 and the Python implementation. A
    -- review left against an order that never arrived measures something
    -- different, and mixing the two makes the two queries disagree.
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY p.category_group
)
SELECT
    category_group,
    ROUND(product_revenue, 2)                                       AS product_revenue,
    ROUND(100.0 * product_revenue / SUM(product_revenue) OVER (), 2) AS pct_of_revenue,
    RANK() OVER (ORDER BY product_revenue DESC)                     AS revenue_rank,
    ROUND(avg_review_score, 3)                                      AS avg_review_score,
    RANK() OVER (ORDER BY avg_review_score DESC)                    AS satisfaction_rank,
    ROUND(100.0 * negative_review_rate, 2)                          AS negative_review_rate_pct,
    ROUND(100.0 * late_rate, 2)                                     AS late_delivery_rate_pct,
    ROUND(100.0 * freight_to_price, 2)                              AS freight_to_price_pct,
    -- Positive means the category ranks worse on satisfaction than on revenue.
    (RANK() OVER (ORDER BY avg_review_score DESC))
        - (RANK() OVER (ORDER BY product_revenue DESC))             AS rank_gap,
    CASE
        WHEN (RANK() OVER (ORDER BY avg_review_score DESC))
             - (RANK() OVER (ORDER BY product_revenue DESC)) >= 2
            THEN 'sells well, satisfies poorly - investigate'
        WHEN (RANK() OVER (ORDER BY avg_review_score DESC))
             - (RANK() OVER (ORDER BY product_revenue DESC)) <= -2
            THEN 'satisfies better than its size suggests'
        ELSE 'revenue and satisfaction aligned'
    END                                                             AS assessment
FROM category_metrics
ORDER BY product_revenue DESC;


-- ============================ QUERY 15: Top products within each category ==
-- Business question: what are the three best-selling products in every
--   category group?
-- Why it matters: a global top-20 is dominated by whichever categories have
--   the highest price points, so smaller categories never appear. Ranking
--   inside each category surfaces the local winners a merchandising team plans
--   against.
-- Techniques: PARTITION BY with ROW_NUMBER, RANK and DENSE_RANK shown side by
--   side. ROW_NUMBER always yields a unique 1,2,3 - which is why the filter
--   uses it; RANK leaves gaps after a tie and DENSE_RANK does not, so on tied
--   revenue either would return more than three rows per category.
WITH product_revenue AS (
    SELECT
        p.category_group,
        p.category_en,
        oi.product_id,
        COUNT(*)          AS units_sold,
        SUM(oi.price)     AS product_revenue,
        AVG(oi.price)     AS avg_price
    FROM orders o
    INNER JOIN order_items oi ON oi.order_id  = o.order_id
    INNER JOIN products    p  ON p.product_id = oi.product_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY p.category_group, p.category_en, oi.product_id
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY category_group ORDER BY product_revenue DESC) AS rn,
        RANK()       OVER (PARTITION BY category_group ORDER BY product_revenue DESC) AS rnk,
        DENSE_RANK() OVER (PARTITION BY category_group ORDER BY product_revenue DESC) AS dense_rnk,
        ROUND(100.0 * product_revenue
              / SUM(product_revenue) OVER (PARTITION BY category_group), 2)
                                                                                      AS pct_of_category
    FROM product_revenue
)
SELECT
    category_group,
    rn                        AS rank_in_category,
    rnk                       AS rank_with_gaps,
    dense_rnk                 AS dense_rank,
    product_id,
    category_en               AS leaf_category,
    units_sold,
    ROUND(product_revenue, 2) AS product_revenue,
    ROUND(avg_price, 2)       AS avg_price,
    pct_of_category
FROM ranked
WHERE rn <= 3
ORDER BY category_group, rn;


-- ============================ QUERY 16: Seller performance =================
-- Business question: which sellers carry the marketplace, and are they
--   delivering reliably?
-- Why it matters: Olist does not own the inventory, so seller performance IS
--   operational performance. A high-revenue seller with a poor delivery record
--   damages the platform's reputation at scale, and this is the lens the
--   synthetic version of this project could not have.
-- Techniques: multi-table JOIN, HAVING to enforce a minimum sample, correlated
--   subquery for the marketplace benchmark, NTILE for banding.
WITH seller_sales AS (
    SELECT
        oi.seller_id,
        s.seller_state,
        s.seller_region,
        COUNT(DISTINCT oi.order_id)   AS orders,
        COUNT(*)                      AS units,
        COUNT(DISTINCT oi.product_id) AS products,
        SUM(oi.price)                 AS product_revenue,
        AVG(oi.price)                 AS avg_item_price
    FROM orders o
    INNER JOIN order_items oi ON oi.order_id  = o.order_id
    INNER JOIN sellers     s  ON s.seller_id  = oi.seller_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY oi.seller_id, s.seller_state, s.seller_region
    -- Below 50 orders a single late delivery moves the rate by two points and
    -- the ranking becomes noise.
    HAVING COUNT(DISTINCT oi.order_id) >= 50
),
seller_quality AS (
    SELECT
        oi.seller_id,
        AVG(r.review_score)                                      AS avg_review_score,
        AVG(DATE(o.order_delivered_customer_date)
            - DATE(o.order_purchase_timestamp))                  AS avg_delivery_days,
        AVG(CASE WHEN DATE(o.order_delivered_customer_date)
                      > DATE(o.order_estimated_delivery_date)
                 THEN 1.0 ELSE 0.0 END)                          AS late_rate
    FROM orders o
    INNER JOIN order_items  oi ON oi.order_id = o.order_id
    LEFT  JOIN order_reviews r ON r.order_id  = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY oi.seller_id
)
SELECT
    ss.seller_id,
    ss.seller_state,
    ss.seller_region,
    ss.orders,
    ss.units,
    ss.products,
    ROUND(ss.product_revenue, 2)                                  AS product_revenue,
    ROUND(100.0 * ss.product_revenue / SUM(ss.product_revenue) OVER (), 2)
                                                                  AS pct_of_ranked_revenue,
    ROUND(ss.avg_item_price, 2)                                   AS avg_item_price,
    ROUND(sq.avg_review_score, 3)                                 AS avg_review_score,
    ROUND(100.0 * sq.late_rate, 2)                                AS late_delivery_rate_pct,
    ROUND(sq.avg_delivery_days, 1)                                AS avg_delivery_days,
    NTILE(4) OVER (ORDER BY ss.product_revenue DESC)              AS revenue_quartile,
    -- How far this seller's late rate sits from the marketplace as a whole.
    ROUND(
        100.0 * sq.late_rate - (
            SELECT 100.0 * AVG(CASE WHEN DATE(o2.order_delivered_customer_date)
                                         > DATE(o2.order_estimated_delivery_date)
                                    THEN 1.0 ELSE 0.0 END)
            FROM orders o2
            WHERE o2.order_status = 'delivered'
              AND o2.order_delivered_customer_date IS NOT NULL
              AND o2.order_purchase_timestamp >= DATE '2017-01-01'
              AND o2.order_purchase_timestamp <  DATE '2018-09-01'
        ), 2
    )                                                             AS late_vs_market_pp
FROM seller_sales ss
LEFT JOIN seller_quality sq ON sq.seller_id = ss.seller_id
ORDER BY ss.product_revenue DESC
LIMIT 25;


-- ============================ QUERY 17: Seller concentration ===============
-- Business question: how much of the marketplace depends on how few sellers?
-- Why it matters: concentration is a risk measure. Because Olist does not
--   control fulfilment, the largest sellers determine both revenue and the
--   delivery experience for a large share of customers, so losing one is worse
--   than losing an equivalent amount of spread-out revenue.
-- Techniques: NTILE(100) to build percentiles, cumulative SUM() OVER, and a
--   filter applied one level OUT from the window - WHERE is evaluated before
--   window functions, so filtering in the same SELECT would make each running
--   total cover only the surviving rows.
WITH seller_revenue AS (
    SELECT
        oi.seller_id,
        SUM(oi.price) AS product_revenue
    FROM orders o
    INNER JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= DATE '2017-01-01'
      AND o.order_purchase_timestamp <  DATE '2018-09-01'
    GROUP BY oi.seller_id
),
percentiled AS (
    SELECT
        seller_id,
        product_revenue,
        NTILE(100) OVER (ORDER BY product_revenue DESC) AS revenue_percentile
    FROM seller_revenue
),
per_percentile AS (
    SELECT
        revenue_percentile,
        COUNT(*)              AS sellers,
        SUM(product_revenue)  AS revenue
    FROM percentiled
    GROUP BY revenue_percentile
),
cumulative AS (
    SELECT
        revenue_percentile,
        SUM(sellers) OVER (ORDER BY revenue_percentile ROWS UNBOUNDED PRECEDING)
                                                       AS cumulative_sellers,
        SUM(revenue) OVER (ORDER BY revenue_percentile ROWS UNBOUNDED PRECEDING)
                                                       AS cumulative_revenue,
        SUM(revenue) OVER ()                           AS total_revenue
    FROM per_percentile
)
SELECT
    revenue_percentile           AS top_n_percent,
    cumulative_sellers,
    ROUND(cumulative_revenue, 2) AS cumulative_revenue,
    ROUND(100.0 * cumulative_revenue / NULLIF(total_revenue, 0), 2)
                                 AS cumulative_pct_of_revenue
FROM cumulative
WHERE revenue_percentile IN (1, 5, 10, 20, 50, 100)
ORDER BY revenue_percentile;


