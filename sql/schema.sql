-- ===========================================================================
-- MarketLens - analytical schema for the Olist dataset (PostgreSQL 14+)
-- ===========================================================================
-- Seven tables modelling a real Brazilian marketplace: customers and sellers
-- on either side of the transaction, products as the catalogue, orders and
-- order_items as the transaction spine, and payments and reviews hanging off
-- the order.
--
-- Things worth knowing before reading the analysis queries:
--
--   * customers.customer_id is issued PER ORDER, not per person.
--     customers.customer_unique_id is the actual person. Getting this wrong
--     reports a repeat purchase rate of 0.00% instead of 3.12%, so every
--     customer-level analysis in this project keys on customer_unique_id and
--     the column is indexed for it.
--
--   * order_items has no quantity column. A basket containing three of the
--     same product appears as three rows with order_item_id 1, 2, 3. The
--     primary key is therefore (order_id, order_item_id), and a unit count is
--     a COUNT of rows rather than a SUM of quantities.
--
--   * There is no cost price anywhere in the dataset, so gross margin cannot
--     be computed. This project does not report it. Freight is analysed
--     instead, because it is the one cost Olist does expose.
--
--   * price and freight_value are per ITEM, already net of anything. There is
--     no discount field.
--
-- Run with:  psql -d marketlens -f sql/schema.sql
-- ===========================================================================

DROP VIEW  IF EXISTS v_order_line_revenue CASCADE;
DROP TABLE IF EXISTS order_reviews  CASCADE;
DROP TABLE IF EXISTS order_payments CASCADE;
DROP TABLE IF EXISTS order_items    CASCADE;
DROP TABLE IF EXISTS orders         CASCADE;
DROP TABLE IF EXISTS products       CASCADE;
DROP TABLE IF EXISTS sellers        CASCADE;
DROP TABLE IF EXISTS customers      CASCADE;


-- ---------------------------------------------------------------------------
-- customers - one row per ORDER, not per person
-- ---------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id              VARCHAR(32) PRIMARY KEY,
    -- The stable identity of the person behind the order. 99,441 customer_id
    -- values resolve to 96,096 people.
    customer_unique_id       VARCHAR(32) NOT NULL,
    customer_zip_code_prefix VARCHAR(8)  NOT NULL,
    customer_city            VARCHAR(80) NOT NULL,
    customer_state           CHAR(2)     NOT NULL,
    -- Derived from state via the IBGE macro-regions; not present in the source.
    customer_region          VARCHAR(20) NOT NULL,

    CONSTRAINT ck_customers_region
        CHECK (customer_region IN ('North', 'Northeast', 'Central-West',
                                   'Southeast', 'South', 'Unknown'))
);

COMMENT ON COLUMN customers.customer_id IS
    'Per-order identifier. Do NOT use for customer-level analysis.';
COMMENT ON COLUMN customers.customer_unique_id IS
    'The actual person. Use this for repeat rate, RFM, cohorts and lifetime value.';


-- ---------------------------------------------------------------------------
-- sellers - the supply side of the marketplace
-- ---------------------------------------------------------------------------
CREATE TABLE sellers (
    seller_id              VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(8)  NOT NULL,
    seller_city            VARCHAR(80) NOT NULL,
    seller_state           CHAR(2)     NOT NULL,
    seller_region          VARCHAR(20) NOT NULL,

    CONSTRAINT ck_sellers_region
        CHECK (seller_region IN ('North', 'Northeast', 'Central-West',
                                 'Southeast', 'South', 'Unknown'))
);


-- ---------------------------------------------------------------------------
-- products - the catalogue
-- ---------------------------------------------------------------------------
CREATE TABLE products (
    product_id             VARCHAR(32) PRIMARY KEY,
    -- Source category, in Portuguese. Kept so results can be traced back.
    category_pt            VARCHAR(60),
    -- Translated leaf category (73 of them) and the business grouping used in
    -- reporting, because 73 bars on a chart communicates nothing.
    category_en            VARCHAR(60) NOT NULL,
    category_group         VARCHAR(40) NOT NULL,
    product_name_length    SMALLINT,
    product_description_length SMALLINT,
    product_photos_qty     SMALLINT,
    product_weight_g       INTEGER,
    product_length_cm      SMALLINT,
    product_height_cm      SMALLINT,
    product_width_cm       SMALLINT,
    -- Derived: length x height x width, used in the freight analysis because
    -- bulky items are what make shipping expensive.
    product_volume_cm3     INTEGER,

    CONSTRAINT ck_products_weight CHECK (product_weight_g IS NULL OR product_weight_g >= 0),
    CONSTRAINT ck_products_photos CHECK (product_photos_qty IS NULL OR product_photos_qty >= 0)
);

COMMENT ON COLUMN products.category_en IS
    'Translated category. 610 products have no category in the source and are labelled ''unknown''.';


-- ---------------------------------------------------------------------------
-- orders - one row per placed order
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    order_id                      VARCHAR(32) PRIMARY KEY,
    customer_id                   VARCHAR(32) NOT NULL,
    order_status                  VARCHAR(12) NOT NULL,
    order_purchase_timestamp      TIMESTAMP   NOT NULL,
    order_approved_at             TIMESTAMP,
    order_delivered_carrier_date  TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP   NOT NULL,

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    CONSTRAINT ck_orders_status
        CHECK (order_status IN ('delivered', 'shipped', 'invoiced', 'processing',
                                'approved', 'created', 'canceled', 'unavailable'))
);

COMMENT ON COLUMN orders.order_status IS
    'canceled and unavailable produce no revenue; the rest are stages of fulfilment.';
COMMENT ON COLUMN orders.order_estimated_delivery_date IS
    'The date promised to the customer at purchase. Delivery after this is late.';


-- ---------------------------------------------------------------------------
-- order_items - one row per unit; there is no quantity column
-- ---------------------------------------------------------------------------
CREATE TABLE order_items (
    order_id            VARCHAR(32)   NOT NULL,
    -- Sequence within the order, 1..n. Three of the same product appear as
    -- three rows, which is why this - not product_id - completes the key.
    order_item_id       SMALLINT      NOT NULL,
    product_id          VARCHAR(32)   NOT NULL,
    seller_id           VARCHAR(32)   NOT NULL,
    shipping_limit_date TIMESTAMP,
    price               NUMERIC(10,2) NOT NULL,
    freight_value       NUMERIC(10,2) NOT NULL,

    CONSTRAINT pk_order_items PRIMARY KEY (order_id, order_item_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)   REFERENCES orders   (order_id) ON DELETE CASCADE,
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id) REFERENCES products (product_id),
    CONSTRAINT fk_items_seller
        FOREIGN KEY (seller_id)  REFERENCES sellers  (seller_id),

    CONSTRAINT ck_items_price   CHECK (price > 0),
    CONSTRAINT ck_items_freight CHECK (freight_value >= 0)
);

COMMENT ON TABLE order_items IS
    'One row per unit sold. A unit count is COUNT(*), never SUM(quantity) - there is no quantity column.';


-- ---------------------------------------------------------------------------
-- order_payments - an order can be split across methods and instalments
-- ---------------------------------------------------------------------------
CREATE TABLE order_payments (
    order_id             VARCHAR(32)   NOT NULL,
    payment_sequential   SMALLINT      NOT NULL,
    payment_type         VARCHAR(20)   NOT NULL,
    payment_installments SMALLINT      NOT NULL,
    payment_value        NUMERIC(10,2) NOT NULL,

    CONSTRAINT pk_order_payments PRIMARY KEY (order_id, payment_sequential),
    CONSTRAINT fk_payments_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id) ON DELETE CASCADE,
    CONSTRAINT ck_payments_value CHECK (payment_value >= 0),
    CONSTRAINT ck_payments_installments CHECK (payment_installments >= 0)
);

COMMENT ON TABLE order_payments IS
    '2,961 orders are split across more than one payment row; 2,246 mix payment types.';


-- ---------------------------------------------------------------------------
-- order_reviews - the customer satisfaction signal
-- ---------------------------------------------------------------------------
CREATE TABLE order_reviews (
    review_id              VARCHAR(32) NOT NULL,
    order_id               VARCHAR(32) NOT NULL,
    review_score           SMALLINT    NOT NULL,
    review_comment_title   TEXT,
    review_comment_message TEXT,
    review_creation_date   TIMESTAMP   NOT NULL,
    review_answer_timestamp TIMESTAMP,

    -- One surviving review per order after cleaning; the raw extract contains
    -- duplicates that the cleaning layer resolves and reports.
    CONSTRAINT pk_order_reviews PRIMARY KEY (order_id),
    CONSTRAINT fk_reviews_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id) ON DELETE CASCADE,
    CONSTRAINT ck_reviews_score CHECK (review_score BETWEEN 1 AND 5)
);

COMMENT ON TABLE order_reviews IS
    'Review score 1-5. This is the closest thing the dataset has to a quality signal - there is no returns table.';


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
-- Chosen for the access patterns the analysis uses rather than by indexing
-- every column.

-- The single most important index in the schema: every customer-level
-- analysis groups by the person, not by the per-order id.
CREATE INDEX idx_customers_unique     ON customers (customer_unique_id);
CREATE INDEX idx_customers_state      ON customers (customer_state);
CREATE INDEX idx_customers_region     ON customers (customer_region);

CREATE INDEX idx_orders_purchase_date ON orders (order_purchase_timestamp);
CREATE INDEX idx_orders_customer      ON orders (customer_id);
CREATE INDEX idx_orders_status        ON orders (order_status);
-- Partial index: nearly every revenue query excludes the two dead statuses.
CREATE INDEX idx_orders_revenue_dates ON orders (order_purchase_timestamp)
    WHERE order_status NOT IN ('canceled', 'unavailable');
-- Supports the delivery-performance analysis, which only looks at delivered
-- orders that actually have a delivery date.
CREATE INDEX idx_orders_delivered     ON orders (order_delivered_customer_date)
    WHERE order_status = 'delivered';

CREATE INDEX idx_items_order          ON order_items (order_id);
CREATE INDEX idx_items_product        ON order_items (product_id);
CREATE INDEX idx_items_seller         ON order_items (seller_id);

CREATE INDEX idx_payments_order       ON order_payments (order_id);
CREATE INDEX idx_payments_type        ON order_payments (payment_type);

CREATE INDEX idx_reviews_score        ON order_reviews (review_score);
CREATE INDEX idx_reviews_created      ON order_reviews (review_creation_date);

CREATE INDEX idx_products_category    ON products (category_en);
CREATE INDEX idx_products_group       ON products (category_group);

CREATE INDEX idx_sellers_state        ON sellers (seller_state);


-- ---------------------------------------------------------------------------
-- v_order_line_revenue - the one place the revenue formula is written down
-- ---------------------------------------------------------------------------
-- The analysis queries in sql/*.sql deliberately write their joins out in full
-- rather than leaning on this view, because the joins are part of what those
-- queries demonstrate. The view exists so ad-hoc exploration and the dashboard
-- share a single consistent definition of a revenue line.

CREATE VIEW v_order_line_revenue AS
SELECT
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    o.customer_id,
    c.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    c.customer_city,
    c.customer_state,
    c.customer_region,
    s.seller_state,
    s.seller_region,
    p.category_en,
    p.category_group,
    oi.price,
    oi.freight_value,
    oi.price + oi.freight_value                        AS item_total,
    (o.order_status NOT IN ('canceled', 'unavailable')) AS is_revenue,
    (o.order_status = 'delivered')                      AS is_delivered,
    -- Positive means the order arrived after the date promised at checkout.
    CASE
        WHEN o.order_delivered_customer_date IS NOT NULL
        THEN DATE(o.order_delivered_customer_date) - DATE(o.order_estimated_delivery_date)
    END                                                 AS days_vs_estimate,
    CASE
        WHEN o.order_delivered_customer_date IS NOT NULL
        THEN DATE(o.order_delivered_customer_date) - DATE(o.order_purchase_timestamp)
    END                                                 AS delivery_days,
    r.review_score
FROM order_items oi
INNER JOIN orders        o ON o.order_id    = oi.order_id
INNER JOIN customers     c ON c.customer_id = o.customer_id
INNER JOIN products      p ON p.product_id  = oi.product_id
INNER JOIN sellers       s ON s.seller_id   = oi.seller_id
LEFT  JOIN order_reviews r ON r.order_id    = oi.order_id;

COMMENT ON VIEW v_order_line_revenue IS
    'Order lines enriched with customer, seller, product, delivery and review context. Filter is_revenue for revenue reporting.';
