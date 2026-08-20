# Growth Decision Engine — Data Dictionary

This document defines the raw-data contract for the platform-neutral Growth Decision Engine. The same contract can be used for ecommerce, quick commerce, food delivery and other transaction marketplaces.

## 1. weekly_kpis.csv

Required columns:

```text
week,mau,orders,revenue,new_users,acquisition_spend,contribution_profit
```

| Column | Meaning | Type |
|---|---|---|
| `week` | Reporting period identifier such as W01, W02, W100 | text |
| `mau` | Monthly active users for the reporting period | numeric |
| `orders` | Completed transaction count | numeric |
| `revenue` | Marketplace revenue for the period | numeric |
| `new_users` | Newly acquired users | numeric |
| `acquisition_spend` | Spend used to acquire new users | numeric |
| `contribution_profit` | Contribution profit for the period | numeric |

Derived by Python:

- OPU = orders / mau
- ARPU = revenue / mau
- AOV = revenue / orders
- CAC = acquisition_spend / new_users
- Contribution Margin = contribution_profit / revenue × 100

## 2. weekly_plan.csv

Required columns:

```text
week,mau_plan,orders_plan,revenue_plan,cm_plan
```

Derived plan metrics:

- OPU plan = orders_plan / mau_plan
- ARPU plan = revenue_plan / mau_plan
- AOV plan = revenue_plan / orders_plan

## 3. funnel.csv

Required columns:

```text
week,visitors,browse_users,product_viewers,cart_users,checkout_users
```

| Column | Meaning |
|---|---|
| `visitors` | Unique users entering the marketplace journey during the period |
| `browse_users` | Unique users who browse/search/category-discover inventory or listings |
| `product_viewers` | Unique users who view a product/item/detail surface |
| `cart_users` | Unique users who add at least one item to cart |
| `checkout_users` | Unique users who reach checkout |

Derived rates:

- Marketplace engagement = visitors / MAU × 100
- Browse rate = browse_users / visitors × 100
- Product view rate = product_viewers / browse_users × 100
- Cart rate = cart_users / product_viewers × 100
- Checkout rate = checkout_users / cart_users × 100

Orders are deliberately not used as the funnel denominator because orders are transactions rather than unique users.

Backward compatibility: the upload layer recognises the old food-delivery columns `food_visitors`, `restaurant_viewers` and `menu_viewers` and maps them to `visitors`, `browse_users` and `product_viewers`.

## 4. segments.csv

Required columns:

```text
week,segment,users,orders,revenue,retained_users,promo_users,contribution_profit
```

Derived segment metrics:

- Orders per user = orders / users
- AOV = revenue / orders
- Retention = retained_users / users
- Promotion usage = promo_users / users
- Contribution margin = contribution_profit / revenue

Segments are platform-neutral labels such as New Users, Occasional, Regular, Power or Lapsed, but the uploaded dataset may use any consistent business segmentation.

## 5. cohorts.csv

Required base columns:

```text
cohort,users
```

Plus one or more dynamic retention columns:

```text
week_1_retained_users
week_2_retained_users
...
week_N_retained_users
```

The number of retention weeks is determined from the uploaded data. Retention percentages are derived by Python as retained users / cohort users.

## 6. initiatives.csv

Required columns:

```text
initiative,target_problem,target_segment,expected_order_uplift,expected_conversion_uplift,expected_revenue,implementation_effort,confidence,time_to_impact,cm_impact,risk,owner
```

These are planning inputs rather than calculated KPIs. `target_problem` can include Retention, Frequency, Conversion, AOV, Monetisation or Acquisition.

## Data quality rules

- Keep required column names exactly as defined.
- Week identifiers must match the dynamic W-number format.
- Required values cannot be blank.
- Numeric fields must be numeric.
- Counts and monetary measures cannot be negative.
- Weekly datasets must cover the same periods.
- Funnel populations must not increase from one stage to the next.
- Segment totals must reconcile to weekly MAU, orders and revenue, subject only to the existing small-revenue warning tolerance.
- Cohort retained-user counts cannot exceed original cohort users and cannot increase across cohort weeks.

The raw CSVs contain facts; Python derives the analytical metrics.
