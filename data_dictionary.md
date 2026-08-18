# Growth Decision Engine: Data Dictionary

## 1. Purpose

The Growth Decision Engine converts raw marketplace facts into:

**Diagnose -> Quantify -> Prioritise -> Action -> Experiment -> Measure**

The input contract follows one principle:

> Upload raw business facts. Let Python calculate derived KPIs.

The dashboard must not require users to manually calculate OPU, ARPU, AOV, CAC, contribution margin, funnel rates, or segment ratios.

All supplied demo data is synthetic and does not represent internal data from any real company.

## 2. Required datasets

The application uses six CSV files:

1. `weekly_kpis.csv`
2. `weekly_plan.csv`
3. `funnel.csv`
4. `segments.csv`
5. `cohorts.csv`
6. `initiatives.csv`

## 3. Weekly KPI input

File: `weekly_kpis.csv`

Required columns:

```text
week
mau
orders
revenue
new_users
acquisition_spend
contribution_profit
```

These are raw facts.

The engine derives:

```text
OPU = orders / mau
ARPU = revenue / mau
AOV = revenue / orders
CAC = acquisition_spend / new_users
Contribution Margin % = contribution_profit / revenue * 100
```

## 4. Weekly plan input

File: `weekly_plan.csv`

Required columns:

```text
week
mau_plan
orders_plan
revenue_plan
cm_plan
```

The engine derives plan-side KPIs:

```text
OPU plan = orders_plan / mau_plan
ARPU plan = revenue_plan / mau_plan
AOV plan = revenue_plan / orders_plan
```

Plan variance is calculated by Python.

For value metrics:

```text
Variance % = (Actual - Plan) / Plan * 100
```

For contribution margin:

```text
CM Gap = Actual CM - Plan CM
```

## 5. Funnel input

File: `funnel.csv`

Required columns:

```text
week
food_visitors
restaurant_viewers
menu_viewers
cart_users
checkout_users
```

MAU and completed orders are deliberately not duplicated here. They come from `weekly_kpis.csv`.

The funnel derives:

```text
Food engagement = food_visitors / MAU
Restaurant view rate = restaurant_viewers / food_visitors
Menu view rate = menu_viewers / restaurant_viewers
Cart rate = cart_users / menu_viewers
Checkout rate = checkout_users / cart_users
```

The engine must not calculate `orders / checkout_users` as a user conversion rate because `orders` represents transactions while `checkout_users` represents users. One user can generate multiple orders, so that ratio can legitimately exceed 100% and is not a conversion metric.

Funnel stage populations must not exceed their upstream populations.

## 6. Segment input

File: `segments.csv`

Required columns:

```text
week
segment
users
orders
revenue
retained_users
promo_users
contribution_profit
```

The engine derives:

```text
Orders per user = orders / users
AOV = revenue / orders
Retention = retained_users / users
Promotion usage = promo_users / users
Contribution margin = contribution_profit / revenue
```

Segment totals must reconcile to weekly MAU, orders and revenue.

## 7. Cohort input

File: `cohorts.csv`

Required base columns:

```text
cohort
users
```

Retention is represented as retained-user counts. Use one column for every cohort week that is available in the source data:

```text
week_1_retained_users
week_2_retained_users
week_3_retained_users
...
week_N_retained_users
```

For example, a 12-week cohort dataset can contain:

```text
cohort
users
week_1_retained_users
week_2_retained_users
week_3_retained_users
week_4_retained_users
week_5_retained_users
week_6_retained_users
week_7_retained_users
week_8_retained_users
week_9_retained_users
week_10_retained_users
week_11_retained_users
week_12_retained_users
```

The UI derives and displays:

```text
Week N retention = week_N_retained_users / users * 100
```

The raw retained-user columns must remain counts. Do not pre-calculate or upload retention percentages in these columns.

### Cohort integrity rules

For every cohort:

- retained users cannot be greater than the original cohort users;
- retained users should not increase from an earlier cohort week to a later cohort week;
- retained-user values cannot be negative;
- cohort identifiers must be unique.

### Cohort horizon

The UI is designed to recognise cohort retention columns dynamically. It does not assume that the dataset ends at Week 4. If the uploaded file contains Week 12 retention, the UI can display Week 1 through Week 12 retention.

The deterministic cohort-analysis engine should use the complete supplied retention horizon rather than silently discarding later weeks. Any change required to make the deterministic engine fully dynamic should be implemented in the cohort engine/validation layer rather than by duplicating cohort logic in the UI.

## 8. Initiative input

File: `initiatives.csv`

Required columns:

```text
initiative
target_problem
target_segment
expected_order_uplift
expected_conversion_uplift
expected_revenue
implementation_effort
confidence
time_to_impact
cm_impact
risk
owner
```

These are decision and planning inputs, not dashboard calculations.

## 9. Validation philosophy

Validation checks:

- Required datasets are present
- Required columns are present
- Missing values
- Numeric types
- Negative values
- Week identifiers
- Duplicate business keys
- Weekly period alignment
- Funnel stage integrity
- Segment aggregate reconciliation
- Segment period coverage
- Cohort retention integrity

Statuses:

- `PASS`: no issue detected
- `WARNING`: non-blocking issue that does not compromise structural integrity
- `FAIL`: structural or integrity issue that blocks analysis

Small rounding differences in cross-dataset monetary reconciliation may be treated as warnings. Material mismatches remain failures.

### 10. Week identifier format

Weekly datasets use identifiers in the format:

- `W01`
- `W02`
- `W03`
- ...
- `W99`
- `W100`
- `W101`
- ...

There is no hard-coded maximum week number. The application accepts any positive week number using the `W##...` format, provided the identifiers are valid and unique within the dataset.

Weekly datasets must use the same set of week identifiers for cross-dataset period alignment.

## 11. Backward compatibility

For B2, the upload layer can recognise the previous calculated-KPI schema and convert it into the raw-data contract before validation.

This means an existing six-file dataset containing fields such as `opu`, `arpu`, `aov`, `cac`, `contribution_margin`, or segment ratios can still be uploaded while the new template remains intentionally minimal.

For cohorts, legacy columns such as:

```text
week_1_retention
week_2_retention
...
week_N_retention
```

can be converted to retained-user counts using:

```text
week_N_retained_users = users * week_N_retention
```

The converted values are calculated only as an input migration step. The deterministic analysis continues to calculate dashboard retention metrics from raw retained-user counts.

## 12. Business framework

Revenue is decomposed through:

```text
Revenue -> MAU x OPU x ARPU
```

Interpretation:

- MAU: acquisition and active-user scale
- OPU: engagement, frequency and retention
- ARPU: monetisation, AOV, mix, pricing and promotions

No business conclusion should be generated without quantitative evidence.
