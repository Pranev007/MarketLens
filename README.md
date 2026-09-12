# MarketLens — E-Commerce Marketplace Business Analytics

**Tech Stack**: Python, SQL, PostgreSQL, Streamlit

An end-to-end e-commerce analytics project on **real marketplace transaction data** — the Brazilian E-Commerce Public Dataset by Olist — covering customer behaviour, logistics, seller performance and revenue.

---

## Key Achievements & Project Highlights

- **Data Cleaning & Validation**: Cleaned and validated **99,440 orders and 112,650 transactions across 7 relational tables**, handling missing values, duplicates, inconsistent categories and invalid records through an automated pipeline of **70 data-quality checks**.
- **SQL Analytics Engine**: 24 analytical SQL queries covering revenue, AOV, customer behaviour, cancellations, delivery SLA performance and seller metrics — built with CTEs, joins, aggregations and window functions.
- **Customer Segmentation & Cohort Analysis**: **RFM segmentation** and **cohort retention analysis** identifying high-value customers, repeat-purchase patterns and retention trends.
- **Interactive BI Dashboard**: A 5-page Streamlit dashboard tracking GMV, customer retention, seller performance and logistics KPIs, with filters that apply across every page.
- **Actionable Business Insights**: Evidence-based findings and recommendations on customer retention, delivery performance and seller reliability.

---

## Headline findings

| Finding | Evidence |
|:--|:--|
| **Late delivery collapses satisfaction** | On-time orders average **4.28 / 5**; late orders **2.26**. Orders missing the date by more than a week average **1.69** — a **2.6-point** fall. |
| **Delays drive the one-star population** | **54.1%** of late orders are rated one star. Of all one-star orders, **69.3%** took longer than a typical order. |
| **The business runs on acquisition** | Only **3.03%** of customers ever order again; **97%** buy exactly once. |
| **Fixing delivery will not fix retention** | Customers with a good first delivery return **2.0%** of the time against **1.8%** for a bad one — reported as-is, because it changes the recommendation. |
| **Seller concentration is the marketplace risk** | The top **1%** of sellers carry **25.8%** of revenue; the top 10% carry **67.3%**. |
| **Distance drives cost and satisfaction together** | A North customer pays **22.7%** of item price in freight and waits **23 days**; a Southeast customer pays 15.2% and waits 11. |

Every figure is computed by the pipeline. Full write-ups with recommendations are in [`reports/business_insights.md`](reports/business_insights.md); the KPI table is in [`reports/kpi_summary.md`](reports/kpi_summary.md).

---

## Project Structure

```
marketlens/
├── data/
│   ├── raw/olist/                raw extract (CSV)
│   └── processed/                cleaned analysis tables (Parquet) + quality log
├── sql/
│   ├── schema.sql                PostgreSQL schema definition
│   ├── revenue_analysis.sql      Q01-05  revenue, AOV, MoM growth, quarterly mix
│   ├── customer_analysis.sql     Q06-09  the customer_id trap, frequency, RFM
│   ├── retention_analysis.sql    Q10-12  cohort matrix, first-delivery effect
│   ├── product_analysis.sql      Q13-17  category & seller performance
│   └── delivery_reviews_analysis.sql
│                                 Q18-24  lateness, review impact, regional KPIs
├── src/marketlens/
│   ├── config.py                 environment settings & reporting window
│   ├── pipeline.py               end-to-end pipeline runner
│   ├── data_ingestion/           dataset download
│   ├── data_processing/          cleaning, validation, PostgreSQL loading
│   └── analytics/                revenue, products, customers, cohorts,
│                                 delivery, insights, KPIs
├── dashboard/
│   ├── app.py                    Streamlit entry point
│   └── views/                    5 pages
├── docs/                         KPI definitions & data model
├── reports/                      generated analysis tables, SQL results, insights
├── tests/                        75 tests, incl. 13 SQL-vs-Python parity checks
└── README.md
```

---

## Quick Start

### 1. Get the data and build the tables
```bash
python -m marketlens.pipeline
```

Downloads the Olist extract, cleans it, runs the validation suite and writes the analysis tables. Add `--with-db` to also load PostgreSQL. Without a database the analytics read the Parquet files instead.

### 2. Run the SQL analyses
```bash
python -m marketlens.data_processing.run_sql_analysis
```

### 3. Launch the dashboard
```bash
streamlit run dashboard/app.py
```

### 4. Run the test suite
```bash
pytest
```

---

## Notes on method

- **Customer identity.** Olist issues a new `customer_id` for every order. Grouped on `customer_id` the repeat purchase rate is exactly 0.00%; keyed on `customer_unique_id` it is 3.03%. Every customer metric here uses the latter — see `sql/customer_analysis.sql` Q06.
- **Reporting window.** January 2017 to August 2018, the contiguous run of complete months, holding 99.65% of orders. The sparse tails (4 orders in September 2016, 1 in December 2016) are loaded but excluded from analysis.
- **No margin is reported.** Olist carries no cost price, so profit cannot be computed. Freight is the one cost the data exposes and stands in for cost pressure.
- **SQL and Python are checked against each other.** Both implementations of each key metric must agree — the parity tests have caught several real defects.

Full definitions: [`docs/kpi_definitions.md`](docs/kpi_definitions.md) · [`docs/data_model.md`](docs/data_model.md)

---

## Data source

Brazilian E-Commerce Public Dataset by Olist, published on Kaggle under **CC BY-NC-SA 4.0**. Real marketplace transactions from 2016–2018, anonymised by the publisher.
