# Growth Decision Engine

**Turn marketplace data into quantified growth decisions.**

An explainable AI system designed to demonstrate Growth Manager, Strategy, Commercial Growth, Product Growth and Marketplace thinking.

## Portfolio positioning

The engine follows:

**Diagnose -> Quantify -> Prioritise -> Experiment -> Measure**

It is deliberately not a generic AI chatbot. Python performs the deterministic calculations first. The AI layer interprets the calculated evidence and produces a business narrative.

## Synthetic data disclaimer

All included data is synthetic. It does not represent internal data from Careem, Talabat, Deliveroo, Noon, Amazon, or any other company.

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

No database, React, JavaScript, Docker or cloud infrastructure is required for version 1.

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

## Validate the data

The validation script can still be run directly:

```bash
python test_validation.py
```

The project also contains a pytest-discoverable validation suite:

```bash
python -m pytest -v
```

The pytest suite is intended to verify both clean data and controlled data-quality failures, including missing columns, invalid numeric values, negative values, duplicate weeks, funnel inconsistencies, cross-dataset mismatches and malformed cohort data.

A clean demo dataset should pass validation with a data quality score of 100/100.

## Run the application

```bash
streamlit run app.py
```

Streamlit will show a local URL in the terminal.

## AI layer

The deterministic engine works without an API key.

The current AI layer uses the Gemini API through the `google-genai` package.

Set the API key locally through an environment variable or `.env` file:

```bash
export GEMINI_API_KEY="your_key_here"
```

Do not hardcode the API key into Python, commit it to the repository, or expose it in the UI.

The AI receives the calculated analysis package. Python remains the source of truth for numerical calculations, diagnosis, opportunity sizing, prioritisation and experiment logic. Gemini is used primarily to explain, synthesise and communicate the deterministic evidence.

## Data input principle

The upload template asks for raw facts and planning inputs only. Derived metrics such as OPU, ARPU, AOV, CAC, contribution margin, funnel rates and segment ratios are calculated by Python.

The upload layer also accepts the previous calculated-KPI schema and normalises it for B2 backward compatibility.

## Cohort data

Cohort retention is designed to support a variable number of weeks.

The raw cohort dataset uses:

```text
cohort
users
week_1_retained_users
week_2_retained_users
...
week_N_retained_users
```

The number of retention weeks is determined from the uploaded dataset. The application does not require the data to stop at Week 4; for example, a dataset can contain Week 1 through Week 12 or more weeks.

The raw `week_N_retained_users` fields represent retained-user counts, not percentages.

Retention percentages are derived by Python:

```text
Week N Retention = week_N_retained_users / users x 100
```

The Streamlit UI dynamically detects and displays all available cohort retention weeks in numerical order.

For example:

```text
Cohort | Users | Week 1 Retention | Week 2 Retention | ... | Week 12 Retention
```

The raw cohort counts remain the source of truth; the displayed percentages are derived metrics.

## Funnel data

The funnel uses user populations at each stage:

```text
MAU
  ↓
Food Visitors
  ↓
Restaurant Viewers
  ↓
Menu Viewers
  ↓
Cart Users
  ↓
Checkout Users
```

The engine derives stage conversion rates from the available user counts.

Orders are transaction counts rather than unique converting users. Therefore the engine does not present:

```text
Orders / Checkout Users
```

as a user conversion rate, because this can legitimately exceed 100% when users place multiple orders.

A true checkout-to-order user conversion metric would require a raw field representing unique users who completed an order.

## Core analytical principles

- No metric -> no conclusion.
- No quantified opportunity -> no priority.
- No economic evaluation -> no commercial recommendation.
- No measurable KPI -> no experiment.
- No guardrail -> no scale decision.
- Insufficient evidence must be explicitly stated.

## Core formulas

`OPU = Orders / MAU`

`ARPU = Revenue / MAU`

`AOV = Revenue / Orders`

`Contribution Margin = Contribution Profit / Revenue x 100`

`Revenue approximately equals MAU x OPU x AOV`

`Incremental Orders = MAU x (Target OPU - Current OPU)`

`Incremental Revenue = Incremental Orders x Current AOV`

`Incremental Contribution = Incremental Revenue x Current Contribution Margin`

## Validation philosophy

Validation protects data integrity before analysis.

The validation layer checks:

- Required columns
- Missing values
- Numeric types
- Negative values where not permitted
- Week validity and uniqueness
- Cohort retention integrity
- Funnel stage ordering
- Cross-dataset period alignment
- Segment-to-KPI reconciliation
- Segment period coverage
- Data quality score

Validation uses three states:

```text
PASS
WARNING
FAIL
```

A small reconciliation difference caused by rounding may produce a warning. Material inconsistencies remain blocking failures.

Validation should not be weakened simply to make an uploaded dataset pass.

When a cross-dataset validation check fails, the Streamlit interface should explain:

1. What failed
2. Where it failed
3. Why it failed
4. What needs to be corrected

## Development order

1. Data validation
2. KPI analysis
3. Funnel analysis
4. Root-cause diagnosis
5. Opportunity sizing
6. Initiative prioritisation
7. Experiment design
8. Visualisation
9. AI interpretation
10. Streamlit interface

## Current development phase

The core deterministic analysis stack and Streamlit decision cockpit are implemented through:

**Validation -> KPI analysis -> Funnel analysis -> Diagnosis -> Opportunity -> Prioritisation -> Experiment -> Visualisation -> AI interpretation -> UI**

The current hardening phase is **evidence-grounded action selection**.

This phase connects the deterministic diagnosis to initiative prioritisation so the recommended action is influenced by:

- the observed revenue-driver evidence;
- quantified opportunity drivers;
- segment deterioration where available;
- the existing commercial priority score.

The commercial priority score is retained for transparency, but the final decision score gives greater weight to evidence alignment.

The recommendation package is then reused by the experiment designer and AI narrative rather than independently selecting a top action in multiple places.

## Testing order

For development changes, run:

```bash
python -m pytest -v
python test_validation.py
python -m compileall app.py engine ai visuals test_validation.py
streamlit run app.py
```

The clean demo dataset should pass end-to-end.

Controlled bad-data cases should also be tested to prove that validation catches genuine data-quality problems rather than only validating the clean demo dataset.

## Development principles

- Reuse existing functions and architecture.
- Do not create duplicate files or alternate application versions.
- Keep the six-dataset architecture unless a genuine product or data-model requirement requires change.
- Keep deterministic calculations deterministic.
- Keep Gemini as the narrative and explanation layer.
- Prefer raw data over manually entered derived metrics.
- Do not hardcode credentials.
- Do not expose `.env` or API keys.
- Do not add dependencies unnecessarily.
- Run syntax checks, pytest, standalone validation and a Streamlit smoke test before considering a change complete.

## Interview narrative

The project is intended to demonstrate that the candidate can move from:

**business signal -> diagnosis -> quantified opportunity -> prioritisation -> experiment -> measurement**

rather than simply demonstrate an LLM integration.
