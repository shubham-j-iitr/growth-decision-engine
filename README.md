# Growth Decision Engine

**Turn marketplace data into quantified growth decisions.**

An explainable, AI-assisted decision cockpit for **ecommerce, quick commerce, food delivery and other transaction marketplaces**. The engine converts raw marketplace facts into diagnosis, quantified opportunity, evidence-grounded prioritisation, experiment design and an executive recommendation.

## Product positioning

The engine is deliberately not a generic BI dashboard or AI chatbot.

**Data Quality → Performance → Diagnosis → Root Cause → Opportunity → Prioritisation → Experiment → Decision Explanation → AI Executive Recommendation**

Python remains the source of truth for numerical calculations. Gemini interprets the deterministic evidence and communicates the decision; it does not recalculate or override the underlying numbers.

## Platform-neutral design

The raw data contract is intentionally generic so the same application can analyse: 

- Ecommerce marketplaces
- Quick-commerce marketplaces
- Food-delivery marketplaces
- Retail / grocery marketplaces
- Other consumer transaction marketplaces

The core business model remains:

`Revenue = MAU × OPU × AOV`

The application does not hard-code a food-delivery business model. Funnel labels are generic and can represent the equivalent customer journey for the platform being analysed.

## Architecture

```text
growth-decision-engine/
├── app.py
├── requirements.txt
├── README.md
├── data_dictionary.md
├── test_validation.py
├── test_decision_engine.py
├── data/
│   ├── weekly_kpis.csv
│   ├── weekly_plan.csv
│   ├── funnel.csv
│   ├── segments.csv
│   ├── cohorts.csv
│   └── initiatives.csv
├── engine/
│   ├── validation.py
│   ├── kpi_engine.py
│   ├── funnel_engine.py
│   ├── decision_engine.py
│   └── experiment_engine.py
├── ai/
│   └── decision_agent.py
└── visuals/
    ├── charts.py
    └── decision_tree.py
```

No database, React, JavaScript, Docker or cloud infrastructure is required for the current version.

## Setup

Use Python 3.11+.

```bash
cd growth-decision-engine
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run the application

```bash
streamlit run app.py
```

## AI layer

The deterministic engine works without an API key. The current AI layer uses Gemini through `google-genai`.

Set the API key locally through an environment variable or `.env` file:

```bash
export GEMINI_API_KEY="your_key_here"
```

For Streamlit Community Cloud, store the key in the app Secrets settings. Never commit `.env` or the actual API key to GitHub.

## Raw data principle

Input CSVs contain underlying business facts and planning assumptions. Derived KPIs are calculated by Python. Do not add manually calculated KPI columns to the raw-data contract.

## Funnel model

The funnel uses generic user populations:

```text
MAU
  ↓
Visitors
  ↓
Browse Users
  ↓
Product Viewers
  ↓
Cart Users
  ↓
Checkout Users
```

The names are intentionally platform-neutral. For an ecommerce platform, `Product Viewers` can represent product-detail viewers; for quick commerce it can represent SKU/item-detail viewers; for food delivery it can represent menu viewers. The underlying column contract remains the same.

Orders are transaction counts rather than unique converting users. Therefore the engine does not calculate `orders / checkout_users` as a user conversion rate because one user can place multiple orders. A true user-level checkout-to-purchase conversion metric would require a raw count of unique users who completed an order.

For backward compatibility, the upload layer can normalise the previous food-delivery funnel columns (`food_visitors`, `restaurant_viewers`, `menu_viewers`) into the generic columns. New datasets should use the generic contract.

## Core formulas

`OPU = Orders / MAU`

`ARPU = Revenue / MAU`

`AOV = Revenue / Orders`

`CAC = Acquisition Spend / New Users`

`Contribution Margin = Contribution Profit / Revenue × 100`

`Revenue ≈ MAU × OPU × AOV`

## Validation philosophy

Validation protects data integrity before analysis. It checks required columns, missing values, numeric types, negative values, week validity, cohort integrity, funnel stage ordering, cross-dataset period alignment, segment reconciliation and segment period coverage.

Validation states are:

```text
PASS
WARNING
FAIL
```

Structural and integrity failures block analysis. Warnings do not block analysis.

## Current development phase

The core deterministic stack and Streamlit decision cockpit are implemented through:

**Validation → KPI → Funnel → Diagnosis → Opportunity → Prioritisation → Experiment → Visualisation → AI interpretation → UI**

The current hardening layer is **evidence-grounded action selection**, which connects observed revenue-driver evidence, quantified opportunities, segment deterioration and commercial priority into one deterministic recommendation.

## Testing

Run the full suite before deployment:

```bash
python -m pytest -v
python test_validation.py
python -m py_compile app.py
python -m compileall app.py engine ai visuals test_validation.py test_decision_engine.py
streamlit run app.py
```

The included synthetic dataset should pass validation with a 100/100 data-quality score.

## Synthetic data

All included data is synthetic and is intended only to demonstrate the engine. It does not represent internal data from any company.
