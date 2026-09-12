# Data Model

Seven tables in third normal form representing the relational structure of the Olist Brazilian E-Commerce dataset: `customers`, `sellers`, and `products` are dimensions; `orders` and `order_items` form the transaction spine; `order_payments` and `order_reviews` store payment methods and customer feedback.

## Entity relationship diagram

```mermaid
erDiagram
    customers ||--o{ orders : "places"
    sellers   ||--o{ order_items : "fulfils"
    products  ||--o{ order_items : "is sold as"
    orders    ||--|{ order_items : "contains"
    orders    ||--o{ order_payments : "paid via"
    orders    ||--o{ order_reviews : "reviewed by"

    customers {
        varchar customer_id PK
        varchar customer_unique_id
        varchar customer_zip_code_prefix
        varchar customer_city
        varchar customer_state
        varchar customer_region
    }

    sellers {
        varchar seller_id PK
        varchar seller_zip_code_prefix
        varchar seller_city
        varchar seller_state
        varchar seller_region
    }

    products {
        varchar product_id PK
        varchar category_pt
        varchar category_en
        varchar category_group
        integer product_name_length
        integer product_description_length
        integer product_photos_qty
        numeric product_weight_g
        numeric product_length_cm
        numeric product_height_cm
        numeric product_width_cm
        numeric product_volume_cm3
    }

    orders {
        varchar order_id PK
        varchar customer_id FK
        varchar order_status
        timestamp order_purchase_timestamp
        timestamp order_approved_at
        timestamp order_delivered_carrier_date
        timestamp order_delivered_customer_date
        timestamp order_estimated_delivery_date
    }

    order_items {
        varchar order_id FK
        integer order_item_id PK
        varchar product_id FK
        varchar seller_id FK
        timestamp shipping_limit_date
        numeric price
        numeric freight_value
    }

    order_payments {
        varchar order_id FK
        integer payment_sequential PK
        varchar payment_type
        integer payment_installments
        numeric payment_value
    }

    order_reviews {
        varchar review_id PK
        varchar order_id FK
        integer review_score
        text review_comment_title
        text review_comment_message
        timestamp review_creation_date
        timestamp review_answer_timestamp
    }
```

## Relationships

| Relationship | Cardinality | Enforced by |
|---|---|---|
| `customers` to `orders` | one to many | `fk_orders_customer` |
| `orders` to `order_items` | one to many | `fk_items_order` |
| `products` to `order_items` | one to many | `fk_items_product` |
| `sellers` to `order_items` | one to many | `fk_items_seller` |
| `orders` to `order_payments` | one to many | `fk_payments_order` |
| `orders` to `order_reviews` | one to many | `fk_reviews_order` |

## Key Design Decisions

1. **`customer_unique_id` vs `customer_id`**: Olist issues a new `customer_id` per order. Any customer-level grouping (RFM, repeat rate, cohort retention) must use `customer_unique_id` to avoid treating repeat orders from the same person as new customers.
2. **Product Category Translation**: Original Portuguese category names (`category_pt`) are mapped to English (`category_en`) and grouped into 9 macro-categories (`category_group`).
3. **Price vs Freight**: Product revenue (`price`) and delivery fee (`freight_value`) are stored separately on `order_items` to evaluate freight burden ratios across regions.
