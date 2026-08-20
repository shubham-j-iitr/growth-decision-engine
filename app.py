from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_scroll_to_top import scroll_to_here

from engine.validation import (
    DATASET_CONFIG,
    finalise_validation,
    validate_data_package,
)
from engine.kpi_engine import build_kpi_analysis
from engine.funnel_engine import build_funnel_analysis
from engine.decision_engine import build_decision_package
from engine.experiment_engine import build_top_experiment
from ai.decision_agent import generate_decision_narrative
from visuals.charts import (
    kpi_trend,
    revenue_driver_chart,
    segment_share_chart,
    initiative_priority_chart,
)
from visuals.decision_tree import root_cause_tree


# ============================================================
# PAGE CONFIGURATION
# ============================================================

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

st.set_page_config(
    page_title="Growth Decision Engine",
    page_icon="📈",
    layout="wide",
)

st.title("Growth Decision Engine")
st.caption("Turn marketplace data into quantified growth decisions.")


# ============================================================
# DATA INPUT / TEMPLATE SYSTEM
# ============================================================

DATASET_FILES = {
    "kpi": "weekly_kpis.csv",
    "plan": "weekly_plan.csv",
    "funnel": "funnel.csv",
    "segments": "segments.csv",
    "cohorts": "cohorts.csv",
    "initiatives": "initiatives.csv",
}

DATASET_LABELS = {
    key: config["label"]
    for key, config in DATASET_CONFIG.items()
}

TEMPLATE_README = """Growth Decision Engine - Data Template

Purpose
-------
Upload six small CSV datasets containing raw marketplace facts and business inputs.
The engine derives OPU, ARPU, AOV, CAC, contribution margin, funnel rates,
segment metrics and plan variances automatically.

Required files
--------------
1. weekly_kpis.csv
2. weekly_plan.csv
3. funnel.csv
4. segments.csv
5. cohorts.csv
6. initiatives.csv

RAW-DATA PRINCIPLE
------------------
Do not manually calculate derived KPIs in the CSVs. Provide the underlying
business facts and let the engine calculate the dashboard metrics.

weekly_kpis.csv
----------------
week,mau,orders,revenue,new_users,acquisition_spend,contribution_profit
Derived automatically:
OPU = orders / mau
ARPU = revenue / mau
AOV = revenue / orders
CAC = acquisition_spend / new_users
Contribution Margin = contribution_profit / revenue * 100

weekly_plan.csv
----------------
week,mau_plan,orders_plan,revenue_plan,cm_plan
Derived automatically:
OPU plan = orders_plan / mau_plan
ARPU plan = revenue_plan / mau_plan
AOV plan = revenue_plan / orders_plan

funnel.csv
-----------
week,visitors,browse_users,product_viewers,cart_users,checkout_users
MAU and completed orders are taken from weekly_kpis.csv, so they are not duplicated.
The generic stages can represent traffic, browsing, product/category detail, cart and checkout behavior across ecommerce, quick commerce, food delivery or other marketplaces.

segments.csv
------------
week,segment,users,orders,revenue,retained_users,promo_users,contribution_profit
Derived automatically:
Orders per user, AOV, retention, promotion usage and contribution margin.

cohorts.csv
-----------
cohort,users,week_1_retained_users,...,week_N_retained_users
Include one retained-user column for each cohort week you want to analyse.
For example, week_1_retained_users through week_12_retained_users are supported.
Retention percentages are derived from retained users / cohort users.

initiatives.csv
---------------
Candidate interventions and their expected impact, effort, confidence, speed,
economics, risk and owner. These are planning inputs rather than calculated KPIs.

General conventions
-------------------
- Keep the column names exactly as provided.
- Week identifiers use W01, W02, W03 ... format.
- Do not leave required cells blank.
- Numeric fields must contain numeric values only.
- Counts, revenue and monetary measures cannot be negative.
- Do not add currency symbols, commas or percentage signs inside numeric CSV cells.
- The supplied synthetic dataset is intentionally not included in the user template.

Validation
----------
Validation checks schema, missing values, duplicates, numeric types, negative values,
week coverage, funnel structure and reconciliation between weekly KPIs and segment totals.
PASS, WARNING and FAIL are used for data quality. Structural or integrity failures block analysis.
"""


def _template_bytes() -> bytes:
    """Create a schema-only ZIP template from the current validation contract."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for key, filename in DATASET_FILES.items():
            columns = DATASET_CONFIG[key]["required_columns"]
            csv_content = pd.DataFrame(columns=columns).to_csv(index=False)
            archive.writestr(filename, csv_content)
        archive.writestr("README.txt", TEMPLATE_README)
    return buffer.getvalue()


def _demo_zip_bytes() -> bytes:
    """Create a downloadable ZIP containing the same synthetic demo data used by the app."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for key, filename in DATASET_FILES.items():
            file_path = DATA / filename
            archive.writestr(filename, file_path.read_bytes())
        archive.writestr(
            "README.txt",
            TEMPLATE_README.replace(
                "The supplied synthetic dataset is intentionally not included in this template.",
                "This ZIP contains the included synthetic dataset so you can inspect a completed example before preparing your own data."
            )
        )
    return buffer.getvalue()


def _read_csv_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(file_bytes))


def _normalise_dataset_schema(key: str, df: pd.DataFrame) -> pd.DataFrame:
    """Accept the previous calculated-KPI schema and convert it to the raw-data contract."""
    out = df.copy()

    if key == "kpi" and "opu" in out.columns:
        out["acquisition_spend"] = out["cac"] * out["new_users"]
        out["contribution_profit"] = out["revenue"] * out["contribution_margin"] / 100
        return out[[
            "week", "mau", "orders", "revenue", "new_users",
            "acquisition_spend", "contribution_profit",
        ]]

    if key == "plan" and "opu_plan" in out.columns:
        return out[["week", "mau_plan", "orders_plan", "revenue_plan", "cm_plan"]]

    if key == "funnel":
        # Backward compatibility for the original food-delivery schema.
        legacy_columns = {
            "food_visitors", "restaurant_viewers", "menu_viewers",
            "cart_users", "checkout_users",
        }
        if legacy_columns.issubset(out.columns):
            out = out.rename(
                columns={
                    "food_visitors": "visitors",
                    "restaurant_viewers": "browse_users",
                    "menu_viewers": "product_viewers",
                }
            )

        return out[[
            "week", "visitors", "browse_users", "product_viewers",
            "cart_users", "checkout_users",
        ]]

    if key == "segments" and "orders_per_user" in out.columns:
        out["retained_users"] = (out["users"] * out["retention"]).round()
        out["promo_users"] = (out["users"] * out["promo_usage"]).round()
        out["contribution_profit"] = out["revenue"] * out["contribution_margin"]
        return out[[
            "week", "segment", "users", "orders", "revenue",
            "retained_users", "promo_users", "contribution_profit",
        ]]

    if key == "cohorts":
        legacy_retention_columns = []
        for column in out.columns:
            match = re.fullmatch(r"week_(\d+)_retention", str(column))
            if match:
                legacy_retention_columns.append((int(match.group(1)), column))

        if legacy_retention_columns:
            for week_number, retention_column in sorted(legacy_retention_columns):
                out[f"week_{week_number}_retained_users"] = (
                    out["users"] * out[retention_column]
                ).round()

            retained_columns = [
                f"week_{week_number}_retained_users"
                for week_number, _ in sorted(legacy_retention_columns)
            ]

            return out[["cohort", "users", *retained_columns]]

    return out


def _normalise_dataset_name(filename: str):
    basename = Path(filename).name.lower()
    for key, expected_filename in DATASET_FILES.items():
        if basename == expected_filename.lower():
            return key
    return None


def _read_uploaded_files(uploaded_files) -> tuple[dict, list[str]]:
    """Read either a ZIP or individual CSV uploads into the six dataset keys."""
    data = {}
    errors = []

    for uploaded_file in uploaded_files or []:
        filename = uploaded_file.name

        if filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(uploaded_file.getvalue())) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        key = _normalise_dataset_name(member.filename)
                        if not key:
                            continue
                        try:
                            data[key] = _normalise_dataset_schema(
                                key,
                                _read_csv_bytes(archive.read(member), DATASET_FILES[key]),
                            )
                        except Exception as exc:
                            errors.append(f"{DATASET_FILES[key]}: {exc}")
            except zipfile.BadZipFile:
                errors.append(f"{filename}: invalid ZIP file.")
            except Exception as exc:
                errors.append(f"{filename}: {exc}")
            continue

        key = _normalise_dataset_name(filename)
        if not key:
            errors.append(
                f"{filename}: filename does not match one of the six required template files."
            )
            continue

        try:
            data[key] = _normalise_dataset_schema(
                key,
                _read_csv_bytes(uploaded_file.getvalue(), filename),
            )
        except Exception as exc:
            errors.append(f"{filename}: {exc}")

    return data, errors


def _load_demo_data() -> dict:
    return {
        key: pd.read_csv(DATA / filename)
        for key, filename in DATASET_FILES.items()
    }


def _reset_application():
    for key in [
        "input_data",
        "input_source",
        "input_validation",
        "analysis_started",
        "ai_result",
        "scroll_to_top",
    ]:
        st.session_state.pop(key, None)



def _status_icon(status: str) -> str:
    return {
        "PASS": "✓",
        "WARNING": "⚠",
        "FAIL": "✕",
    }.get(status, "•")


def _render_validation_summary(validation: dict, data: dict):
    st.markdown("### Data Quality")

    score = float(validation.get("data_quality_score", 0))
    overall_status = validation.get("overall_status", "FAIL")

    cols = st.columns(3)
    cols[0].metric("Data Quality", f"{score:.0f}/100")
    cols[1].metric("Validation", overall_status)
    cols[2].metric(
        "Datasets",
        f"{sum(name in data for name in DATASET_FILES)}/6"
    )

    rows = []

    for key in DATASET_FILES:
        result = validation.get(
            key,
            {
                "overall_status": "FAIL",
                "message": "Dataset not available."
            }
        )

        # Dataset-level status is stored as overall_status.
        dataset_status = result.get(
            "overall_status",
            result.get("status", "FAIL")
        )

        # Collect WARNING / FAIL messages from individual checks.
        messages = []

        for check_name, check_result in result.items():
            if not isinstance(check_result, dict):
                continue

            check_status = check_result.get("status")
            check_message = check_result.get("message")

            if (
                check_status in {"WARNING", "FAIL"}
                and check_message
            ):
                messages.append(str(check_message))

        # Remove duplicate messages while preserving order.
        messages = list(dict.fromkeys(messages))

        if messages:
            dataset_message = " ".join(messages)
        elif dataset_status == "PASS":
            dataset_message = "All validation checks passed."
        elif dataset_status == "WARNING":
            dataset_message = "Validation passed with warnings."
        else:
            dataset_message = "One or more validation checks failed."

        icon = {
            "PASS": "✓",
            "WARNING": "⚠",
            "FAIL": "✕"
        }.get(dataset_status, "•")

        rows.append(
            {
                "Dataset": DATASET_LABELS[key],
                "Status": f"{icon} {dataset_status}",
                "Message": dataset_message,
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

def _render_data_input():
    st.header("Data Input")
    st.caption(
        "Bring your marketplace data into the engine, validate it, then run the existing growth analysis."
    )

    st.info(
        "Demo Dataset uses the included synthetic portfolio data. Uploaded data is held only in this Streamlit session."
    )

    st.markdown("### 1. Prepare your data")
    st.write(
        "Use the blank template for your own data, or download the completed demo "
        "dataset if you want to understand the expected format and values first."
    )

    template_col, demo_download_col, demo_run_col = st.columns(3)

    with template_col:
        st.markdown("**Blank template**")
        st.caption("Six CSVs with the required columns and no records.")
        st.download_button(
            "Download Data Template",
            data=_template_bytes(),
            file_name="growth-decision-template.zip",
            mime="application/zip",
            use_container_width=True,
        )

    with demo_download_col:
        st.markdown("**Completed example**")
        st.caption("Same synthetic dataset used by the Try Demo option.")
        st.download_button(
            "Download Demo Dataset",
            data=_demo_zip_bytes(),
            file_name="growth-decision-demo-dataset.zip",
            mime="application/zip",
            use_container_width=True,
        )

    with demo_run_col:
        st.markdown("**Instant demo**")
        st.caption("Load the completed demo directly into the engine.")
        if st.button("Try Demo Dataset", type="secondary", use_container_width=True):
            st.session_state["input_data"] = _load_demo_data()
            st.session_state["input_source"] = "Demo Dataset"
            st.session_state["input_validation"] = validate_data_package(
                st.session_state["input_data"]
            )
            st.session_state["analysis_started"] = False
            st.rerun()

    st.divider()
    st.markdown("### Upload Your Data")
    st.write("Upload one ZIP containing the six CSVs, or upload the six CSV files individually.")

    uploaded_files = st.file_uploader(
        "Upload ZIP or CSV files",
        type=["zip", "csv"],
        accept_multiple_files=True,
        key="growth_data_upload",
        help="ZIP uploads must contain weekly_kpis.csv, weekly_plan.csv, funnel.csv, segments.csv, cohorts.csv and initiatives.csv.",
    )

    if uploaded_files:
        uploaded_data, upload_errors = _read_uploaded_files(uploaded_files)

        if upload_errors:
            st.warning("Some uploaded files could not be read:")
            for error in upload_errors:
                st.write(f"• {error}")

        if uploaded_data:
            st.session_state["input_data"] = uploaded_data
            st.session_state["input_source"] = "Uploaded Data"
            st.session_state["analysis_started"] = False
            st.session_state["input_validation"] = validate_data_package(uploaded_data)

    data = st.session_state.get("input_data", {})
    validation = st.session_state.get("input_validation")

    st.divider()
    st.markdown("### Upload Status")

    status_rows = []
    for key, filename in DATASET_FILES.items():
        present = key in data
        status_rows.append(
            {
                "Dataset": DATASET_LABELS[key],
                "File": filename,
                "Status": "✓ Uploaded" if present else "Missing",
            }
        )

    st.dataframe(
        pd.DataFrame(status_rows),
        use_container_width=True,
        hide_index=True,
    )

    if validation:
        _render_validation_summary(validation, data)

        if validation["overall_status"] == "FAIL":
            st.error("Analysis is blocked until all structural/data-integrity validation failures are fixed.")
        else:
            if validation["overall_status"] == "WARNING":
                st.warning("Validation passed with warnings. You can continue because no blocking failures were found.")
            else:
                st.success("All required datasets passed validation.")

            if st.button("Run Growth Analysis", type="primary", use_container_width=True):
                st.session_state["analysis_started"] = True
                st.session_state["scroll_to_top"] = True
                st.rerun()

    if data and st.button("Reset Data & Start Again", use_container_width=True):
        _reset_application()
        st.rerun()


if not st.session_state.get("analysis_started", False):
    _render_data_input()
    st.stop()


# ============================================================
# ACTIVE DATASET
# ============================================================

# At this point analysis_started can only be true after validation passed.
# A stage-changing rerun should open the Decision Cockpit at the top rather
# than inheriting the user's previous scroll position on the Data Input view.
if st.session_state.pop("scroll_to_top", False):
    scroll_to_here(0, key="analysis_top")

data = st.session_state["input_data"]
validation = st.session_state["input_validation"]

if validation["overall_status"] == "FAIL":
    st.session_state["analysis_started"] = False
    st.error("Analysis is blocked because the current data package failed validation.")
    st.stop()

st.caption(
    f"Data source: {st.session_state.get('input_source', 'Uploaded Data')} | "
    "All calculations are driven by the supplied dataset."
)

if st.session_state.get("input_source") == "Demo Dataset":
    st.info(
        "Demo Dataset: synthetic data for portfolio/interview demonstration only. "
        "It does not represent internal data from any real company."
    )

if st.sidebar.button("Change Dataset"):
    _reset_application()
    st.rerun()


# ============================================================
# DETERMINISTIC ANALYSIS
# ============================================================

kpi_analysis = build_kpi_analysis(
    data["kpi"],
    data["plan"],
)

funnel_analysis = build_funnel_analysis(
    data["funnel"],
    data["kpi"],
)

decision = build_decision_package(
    kpi_analysis,
    funnel_analysis,
    data["segments"],
    data["cohorts"],
    data["initiatives"],
)

latest = kpi_analysis["weekly"].iloc[-1]

top_experiment = build_top_experiment(
    decision["initiatives"],
    decision["diagnosis"],
    latest,
)

# ============================================================
# FORMATTING HELPERS
# ============================================================

def safe_float(value, default=0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_money(value: float) -> str:
    value = safe_float(value)

    if abs(value) >= 1_000_000:
        return f"AED {value / 1_000_000:.1f}M"

    if abs(value) >= 1_000:
        return f"AED {value / 1_000:.1f}K"

    return f"AED {value:,.0f}"


def fmt_number(value: float) -> str:
    value = safe_float(value)

    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"

    return f"{value:,.0f}"


def fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{safe_float(value):.{decimals}f}%"


def fmt_signed_pct(value: float, decimals: int = 1) -> str:
    return f"{safe_float(value):+.{decimals}f}%"


def fmt_pp(value: float, decimals: int = 1) -> str:
    return f"{safe_float(value):+.{decimals}f}pp"


def gap_status(value: float) -> str:
    value = safe_float(value)
    return "Healthy" if value >= 0 else "Below Plan"


def status_icon(value: float) -> str:
    value = safe_float(value)
    return "🟢" if value >= 0 else "🔴"


def render_gap_metric(
    label: str,
    gap: float,
    actual_text: str,
    plan_text: str,
    decimals: int = 1,
):
    """Render an actual-vs-plan metric with direction based on the numeric gap."""
    gap_value = safe_float(gap)
    if gap_value > 0.0001:
        icon = "↑"
        tone = "#4ade80"
    elif gap_value < -0.0001:
        icon = "↓"
        tone = "#ff4d4f"
    else:
        icon = "→"
        tone = "#facc15"

    st.markdown(
        f"""
        <div style="min-height:115px;">
            <div style="font-size:14px; opacity:0.75;">{label}</div>
            <div style="font-size:34px; font-weight:700; margin-top:6px;">
                {gap_value:+.{decimals}f}%
            </div>
            <div style="
                display:inline-block;
                margin-top:8px;
                padding:5px 9px;
                border-radius:14px;
                background:rgba(128,128,128,0.12);
                color:{tone};
                font-size:13px;
                font-weight:600;
            ">
                {icon} Actual {actual_text} | Plan {plan_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card(
    label: str,
    actual: str,
    plan: str,
    gap: float,
    gap_label: str = "vs plan",
):
    icon = status_icon(gap)

    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 12px;
            padding: 16px;
            min-height: 145px;
        ">
            <div style="font-size: 14px; opacity: 0.75;">
                {label}
            </div>
            <div style="
                font-size: 28px;
                font-weight: 700;
                margin-top: 6px;
            ">
                {actual}
            </div>
            <div style="font-size: 13px; opacity: 0.7;">
                Plan: {plan}
            </div>
            <div style="
                font-size: 15px;
                font-weight: 600;
                margin-top: 8px;
            ">
                {icon} {gap:+.1f}% {gap_label}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_experiment(experiment: dict):
    if not experiment:
        st.warning("No experiment is available.")
        return

    if experiment.get("status") == "insufficient evidence":
        st.warning(
            experiment.get(
                "reason",
                "Insufficient evidence to create an experiment.",
            )
        )
        return

    st.markdown(
        f"### {experiment.get('initiative', 'Recommended Experiment')}"
    )

    st.write(
        experiment.get(
            "hypothesis",
            "No hypothesis was generated.",
        )
    )

    cols = st.columns(4)

    cols[0].metric(
        "Primary KPI",
        experiment.get("primary_kpi", "N/A"),
    )

    cols[1].metric(
        "Expected Uplift",
        fmt_pct(
            experiment.get(
                "expected_uplift_pct",
                0,
            )
        ),
    )

    cols[2].metric(
        "Target",
        experiment.get(
            "target_population",
            "N/A",
        ),
    )

    cols[3].metric(
        "Owner",
        experiment.get(
            "owner",
            "N/A",
        ),
    )

    design_cols = st.columns(2)

    with design_cols[0]:
        st.markdown("**Control**")
        st.write(
            experiment.get(
                "control",
                "Not specified.",
            )
        )

    with design_cols[1]:
        st.markdown("**Treatment**")
        st.write(
            experiment.get(
                "treatment",
                "Not specified.",
            )
        )

    st.markdown("**Secondary KPIs**")
    secondary = experiment.get("secondary_kpis", [])

    if secondary:
        st.write(" • ".join(str(item) for item in secondary))
    else:
        st.write("Not specified.")

    st.markdown("**Decision threshold**")
    st.info(
        experiment.get(
            "decision_threshold",
            "Not specified.",
        )
    )


def render_ai_result(result: dict):
    if not result:
        return

    status = result.get("status", "Unknown")
    mode = result.get("mode", "Unknown")

    cols = st.columns(2)

    cols[0].metric("Agent Mode", mode)
    cols[1].metric("Status", status)

    if status == "success":
        st.markdown("### AI Decision Narrative")
        st.markdown(
            result.get(
                "summary",
                "No narrative returned.",
            )
        )
    else:
        st.warning(
            result.get(
                "summary",
                "AI narrative unavailable.",
            )
        )


def _collect_validation_detail_rows(validation: dict) -> list[dict]:
    """Flatten the validation contract into user-facing status rows.

    Dataset validators expose their status as ``overall_status`` while
    individual checks expose ``status``. The dashboard should surface both
    instead of showing N/A for valid dataset-level results.
    """
    rows = []
    valid_statuses = {"PASS", "WARNING", "FAIL"}

    for key in DATASET_FILES:
        result = validation.get(key)

        if not isinstance(result, dict):
            rows.append(
                {
                    "Check": DATASET_LABELS.get(key, key),
                    "Status": "FAIL",
                    "Details": "Dataset not available.",
                }
            )
            continue

        dataset_status = result.get("overall_status")
        if dataset_status in valid_statuses:
            if dataset_status == "PASS":
                details = "All dataset-level validation checks passed."
            elif dataset_status == "WARNING":
                details = "Dataset passed with one or more warnings."
            else:
                details = "One or more dataset-level validation checks failed."

            rows.append(
                {
                    "Check": DATASET_LABELS.get(key, key),
                    "Status": dataset_status,
                    "Details": details,
                }
            )

    cross_dataset = validation.get("cross_dataset")
    if isinstance(cross_dataset, dict):
        for check_name, check_result in cross_dataset.items():
            if not isinstance(check_result, dict):
                continue

            status = check_result.get("status")
            if status not in valid_statuses:
                continue

            details = check_result.get(
                "message",
                check_result.get("details", ""),
            )

            rows.append(
                {
                    "Check": check_name,
                    "Status": status,
                    "Details": str(details or ""),
                }
            )

    return rows


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Engine Status")

st.sidebar.metric(
    "Data Quality",
    f"{safe_float(validation['data_quality_score']):.0f}/100",
)

st.sidebar.write(
    f"Validation: **{validation['overall_status']}**"
)

st.sidebar.write(
    f"Latest period: **{latest['week']}**"
)

st.sidebar.divider()

st.sidebar.caption(
    "Decision flow: Diagnose → Quantify → Prioritise → "
    "Experiment → Measure"
)


# ============================================================
# 1. EXECUTIVE DASHBOARD
# ============================================================

st.header("1. Executive Dashboard")

st.caption(
    "Decision cockpit: performance → primary gap → quantified opportunity "
    "→ recommended action → experiment."
)

# ------------------------------------------------------------
# Executive scorecard
# ------------------------------------------------------------

st.markdown("### Business Scorecard")

plan_cols = st.columns(6)

plan_metrics = [
    (
        "Revenue",
        latest["revenue"],
        latest["revenue_plan"],
        latest["revenue_plan_variance_pct"],
        "money",
    ),
    (
        "MAU",
        latest["mau"],
        latest["mau_plan"],
        latest["mau_plan_variance_pct"],
        "number",
    ),
    (
        "Orders",
        latest["orders"],
        latest["orders_plan"],
        latest["orders_plan_variance_pct"],
        "number",
    ),
    (
        "OPU",
        latest["opu"],
        latest["opu_plan"],
        latest["opu_plan_variance_pct"],
        "decimal",
    ),
    (
        "ARPU",
        latest["arpu"],
        latest["arpu_plan"],
        latest["arpu_plan_variance_pct"],
        "aed",
    ),
    (
        "CM",
        latest["contribution_margin"],
        latest["cm_plan"],
        latest["cm_gap_pp"],
        "pp",
    ),
]

for col, (label, actual, plan, gap, value_type) in zip(
    plan_cols,
    plan_metrics,
):
    with col:
        if value_type == "money":
            actual_text = fmt_money(actual)
            plan_text = fmt_money(plan)

        elif value_type == "number":
            actual_text = fmt_number(actual)
            plan_text = fmt_number(plan)

        elif value_type == "decimal":
            actual_text = f"{safe_float(actual):.2f}"
            plan_text = f"{safe_float(plan):.2f}"

        elif value_type == "aed":
            actual_text = f"AED {safe_float(actual):.2f}"
            plan_text = f"AED {safe_float(plan):.2f}"

        else:
            actual_text = fmt_pct(actual)
            plan_text = fmt_pct(plan)

        if value_type == "pp":
            gap_value = safe_float(gap)
            icon = status_icon(gap_value)

            st.markdown(
                f"""
                <div style="
                    border: 1px solid rgba(128,128,128,0.25);
                    border-radius: 10px;
                    padding: 12px;
                    min-height: 130px;
                ">
                    <div style="font-size:13px; opacity:0.7;">
                        {label}
                    </div>
                    <div style="
                        font-size:24px;
                        font-weight:700;
                        margin-top:4px;
                    ">
                        {actual_text}
                    </div>
                    <div style="font-size:12px; opacity:0.65;">
                        Plan: {plan_text}
                    </div>
                    <div style="
                        margin-top:8px;
                        font-weight:600;
                    ">
                        {icon} {fmt_pp(gap_value)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            render_kpi_card(
                label,
                actual_text,
                plan_text,
                safe_float(gap),
            )

# Keep the detailed trend available without pushing it into the
# first-view decision hierarchy.
with st.expander("View performance trend", expanded=False):
    st.plotly_chart(
        kpi_trend(
            kpi_analysis["weekly"],
            "revenue",
            "Revenue: Actual vs Plan",
            "revenue_plan",
        ),
        use_container_width=True,
    )

# ------------------------------------------------------------
# Primary growth gap
# ------------------------------------------------------------

diagnosis = decision["diagnosis"]
latest_diagnosis = diagnosis.get("latest", {})

revenue_gap = safe_float(
    latest_diagnosis.get(
        "revenue_gap_pct",
        latest.get("revenue_plan_variance_pct", 0),
    )
)
mau_gap = safe_float(
    latest_diagnosis.get(
        "mau_gap_pct",
        latest.get("mau_plan_variance_pct", 0),
    )
)
opu_gap = safe_float(
    latest_diagnosis.get(
        "opu_gap_pct",
        latest.get("opu_plan_variance_pct", 0),
    )
)
arpu_gap = safe_float(
    latest_diagnosis.get(
        "arpu_gap_pct",
        latest.get("arpu_plan_variance_pct", 0),
    )
)

drivers = diagnosis.get("drivers", [])
evidence = diagnosis.get("evidence", [])

primary_driver = (
    str(drivers[0])
    if drivers
    else "The deterministic diagnosis did not identify a sufficiently strong primary driver."
)

st.markdown("### Primary Growth Gap")

gap_cols = st.columns([2.2, 1.4, 1.4])

with gap_cols[0]:
    with st.container(border=True):
        st.caption("PRIMARY BUSINESS ISSUE")

        if revenue_gap < 0:
            st.markdown(
                f"### Revenue is {abs(revenue_gap):.1f}% below plan"
            )
        elif revenue_gap > 0:
            st.markdown(
                f"### Revenue is {revenue_gap:.1f}% above plan"
            )
        else:
            st.markdown("### Revenue is on plan")

        st.write(
            f"Latest period: **{latest['week']}** · "
            f"Actual **{fmt_money(latest['revenue'])}** vs "
            f"Plan **{fmt_money(latest['revenue_plan'])}**"
        )

with gap_cols[1]:
    with st.container(border=True):
        st.caption("PRIMARY DRIVER")
        st.markdown(
            f"**{primary_driver}**"
        )
        opu_actual = safe_float(latest["opu"])
        opu_plan = safe_float(latest["opu_plan"])
        opu_gap_display = safe_float(latest.get("opu_plan_variance_pct", 0))

        st.write(
            f"OPU: **{opu_actual:.3f}** vs "
            f"**{opu_plan:.3f}** plan "
            f"({opu_gap_display:+.1f}%)"
        )

with gap_cols[2]:
    with st.container(border=True):
        st.caption("ACQUISITION CHECK")
        acquisition_status = "On plan" if mau_gap >= 0 else "Below plan"
        st.markdown(
            f"### {status_icon(mau_gap)} {acquisition_status}"
        )
        st.write(f"MAU: **{fmt_signed_pct(mau_gap)}** vs plan")

with st.expander("View supporting diagnosis evidence", expanded=False):
    if drivers:
        for driver in drivers[:3]:
            st.write(f"• {driver}")

    if evidence:
        st.dataframe(
            pd.DataFrame(evidence).head(6),
            use_container_width=True,
            hide_index=True,
        )

# ------------------------------------------------------------
# Quantified opportunity
# ------------------------------------------------------------

st.markdown("### Quantified Opportunity")

opportunities = decision["opportunities"].copy()

total_revenue_upside = (
    safe_float(opportunities["incremental_revenue"].sum())
    if "incremental_revenue" in opportunities.columns
    else 0.0
)

total_contribution_upside = (
    safe_float(opportunities["incremental_contribution"].sum())
    if "incremental_contribution" in opportunities.columns
    else 0.0
)

total_incremental_orders = (
    safe_float(opportunities["incremental_orders"].sum())
    if "incremental_orders" in opportunities.columns
    else 0.0
)

if not opportunities.empty:
    opportunity_cols = st.columns(3)

    with opportunity_cols[0]:
        with st.container(border=True):
            st.caption("ILLUSTRATIVE REVENUE UPSIDE")
            st.markdown(f"### {fmt_money(total_revenue_upside)}")
            st.write("Scenario-based opportunity")

    with opportunity_cols[1]:
        with st.container(border=True):
            st.caption("INCREMENTAL ORDERS")
            st.markdown(f"### {fmt_number(total_incremental_orders)}")
            st.write("Across generated opportunity cases")

    with opportunity_cols[2]:
        with st.container(border=True):
            st.caption("CONTRIBUTION UPSIDE")
            st.markdown(f"### {fmt_money(total_contribution_upside)}")
            st.write("Scenario-based contribution")

    st.caption(
        "Opportunity values are deterministic scenario calculations based on "
        "explicit assumptions. They are not forecasts."
    )
else:
    st.info("No quantified opportunity was generated from the supplied evidence.")

# ------------------------------------------------------------
# Recommended action + top experiment
# ------------------------------------------------------------

st.markdown("### Recommended Action")

if not decision["initiatives"].empty:
    top = decision["initiatives"].iloc[0]

    action_cols = st.columns([2.2, 1.2, 1.2])

    with action_cols[0]:
        with st.container(border=True):
            st.caption("TOP PRIORITY")
            st.markdown(
                f"### {top.get('initiative', 'Recommended Initiative')}"
            )
            st.write(
                f"Target segment: **{top.get('target_segment', 'N/A')}**"
            )
            st.write(
                f"Expected revenue: **{fmt_money(top.get('expected_revenue', 0))}**"
            )

    with action_cols[1]:
        with st.container(border=True):
            st.caption("DECISION SCORE")
            st.markdown(
                f"### {safe_float(top.get('decision_score', top.get('priority_score', 0))):.2f}"
            )
            st.write(
                f"Evidence alignment: **{safe_float(top.get('evidence_alignment_score', 0)):.2f}**"
            )

    with action_cols[2]:
        with st.container(border=True):
            st.caption("ECONOMIC UPSIDE")
            st.markdown(
                f"### {fmt_money(top.get('expected_revenue', 0))}"
            )
            st.write("Initiative input; not a forecast")

    st.markdown("### Top Experiment")

    render_experiment(top_experiment)

else:
    st.warning(
        "No initiative can be prioritised from the supplied dataset."
    )

# ------------------------------------------------------------
# AI executive brief
# ------------------------------------------------------------

st.markdown("### AI Executive Brief")

st.caption(
    "Gemini explains the deterministic decision package. It does not "
    "recalculate or override the underlying numbers."
)

if st.button(
    "Generate AI Executive Brief",
    type="primary",
    key="generate_ai_decision",
):
    with st.spinner("Generating evidence-based executive brief..."):
        result = generate_decision_narrative(
            {
                "diagnosis": decision["diagnosis"],
                "opportunities": decision["opportunities"],
                "initiatives": decision["initiatives"].head(5),
                "recommendation": decision.get("recommendation", {}),
                "experiment": top_experiment,
            }
        )

        st.session_state["ai_result"] = result

if "ai_result" in st.session_state:
    render_ai_result(st.session_state["ai_result"])


# ============================================================
# 2. DEEP DIVE
# ============================================================

st.header("2. Deep Dive")

st.caption(
    "Detailed analysis is available when you need to understand "
    "the decision, validate assumptions or design execution."
)

tab_diagnosis, tab_opportunity, tab_priority, tab_experiment, tab_explanation, tab_quality = st.tabs(
    [
        "Diagnosis",
        "Opportunity",
        "Prioritisation",
        "Experiment",
        "Decision Explanation",
        "Data Quality",
    ]
)


# ============================================================
# DEEP DIVE: DIAGNOSIS
# ============================================================

with tab_diagnosis:

    st.subheader("KPI Diagnosis")

    kpi_cols = st.columns(3)

    for col, metric, plan_metric, label in [
        (
            kpi_cols[0],
            "mau",
            "mau_plan",
            "MAU",
        ),
        (
            kpi_cols[1],
            "opu",
            "opu_plan",
            "OPU",
        ),
        (
            kpi_cols[2],
            "arpu",
            "arpu_plan",
            "ARPU",
        ),
    ]:
        gap = safe_float(latest[f"{metric}_plan_variance_pct"])
        actual = latest[metric]
        plan = latest[plan_metric]

        if metric == "mau":
            actual_text = fmt_number(actual)
            plan_text = fmt_number(plan)
        elif metric == "opu":
            actual_text = f"{safe_float(actual):.2f}"
            plan_text = f"{safe_float(plan):.2f}"
        else:
            actual_text = f"AED {safe_float(actual):.2f}"
            plan_text = f"AED {safe_float(plan):.2f}"

        with col:
            render_gap_metric(label, gap, actual_text, plan_text)

    st.subheader("Root Cause Tree")

    st.plotly_chart(
        root_cause_tree(
            decision["diagnosis"]
        ),
        use_container_width=True,
    )

    st.subheader("Funnel")

    funnel_cols = st.columns(2)

    with funnel_cols[0]:
        engagement_fig = kpi_trend(
            funnel_analysis["weekly"],
            "engagement_rate",
            "Marketplace Engagement Rate",
        )
        engagement_fig.update_yaxes(ticksuffix="%")
        st.plotly_chart(
            engagement_fig,
            use_container_width=True,
        )

    with funnel_cols[1]:
        checkout_fig = kpi_trend(
            funnel_analysis["weekly"],
            "checkout_rate",
            "Checkout Rate",
        )
        checkout_fig.update_yaxes(ticksuffix="%")
        st.plotly_chart(
            checkout_fig,
            use_container_width=True,
        )

    with st.expander(
        "View funnel stage detail",
        expanded=False,
    ):
        funnel_stage_display = funnel_analysis["stages"].copy()

        # Funnel rate columns are already stored as percentage-point values
        # (e.g. 74.0 means 74%). Format only the display copy.
        for column in funnel_stage_display.columns:
            if "rate" in str(column).lower():
                numeric_values = pd.to_numeric(
                    funnel_stage_display[column],
                    errors="coerce",
                )
                if numeric_values.notna().any():
                    funnel_stage_display[column] = numeric_values.map(
                        lambda value: (
                            f"{value:.1f}%" if pd.notna(value) else ""
                        )
                    )

                # Round percentage-point change for display only.
        # Example: -1.9998 -> -2
        if "change_pp" in funnel_stage_display.columns:
            funnel_stage_display["change_pp"] = (
                pd.to_numeric(
                    funnel_stage_display["change_pp"],
                    errors="coerce",
                )
                .round(0)
                .astype("Int64")
            )
        st.dataframe(
            funnel_stage_display,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Segments")

    segment_cols = st.columns(2)

    with segment_cols[0]:
        st.plotly_chart(
            segment_share_chart(
                data["segments"],
                "revenue",
            ),
            use_container_width=True,
        )

    with segment_cols[1]:
        st.plotly_chart(
            segment_share_chart(
                data["segments"],
                "orders",
            ),
            use_container_width=True,
        )

    latest_segments = data["segments"][
        data["segments"]["week"]
        == data["segments"]["week"].max()
    ].copy()

    with st.expander(
        "View segment detail",
        expanded=False,
    ):
        st.dataframe(
            latest_segments,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Cohorts")

    with st.expander(
        "View cohort retention detail",
        expanded=False,
    ):
        cohort_source = data["cohorts"].copy()

        # Cohort files can contain any number of retention weeks, e.g.
        # week_1_retained_users ... week_12_retained_users.
        # Retained-user columns are raw counts, so convert them to retention
        # percentages using the cohort's original user count.
        retention_columns = []
        for column in cohort_source.columns:
            match = re.fullmatch(
                r"week_(\d+)_retained_users",
                str(column),
            )
            if match:
                retention_columns.append((int(match.group(1)), column))

        retention_columns.sort(key=lambda item: item[0])

        if retention_columns and "users" in cohort_source.columns:
            cohort_display = cohort_source[["cohort", "users"]].copy()

            for week_number, retained_column in retention_columns:
                display_column = f"Week {week_number} Retention"
                cohort_display[display_column] = (
                    pd.to_numeric(
                        cohort_source[retained_column],
                        errors="coerce",
                    )
                    / pd.to_numeric(
                        cohort_source["users"],
                        errors="coerce",
                    ).replace(0, pd.NA)
                    * 100
                ).round(1)

            st.dataframe(
                cohort_display,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "No cohort retention columns were found. Expected columns "
                "such as week_1_retained_users, week_2_retained_users, etc."
            )


# ============================================================
# DEEP DIVE: OPPORTUNITY
# ============================================================

with tab_opportunity:

    st.subheader("Opportunity Sizing")

    opportunities = decision["opportunities"].copy()

    total_revenue = (
        opportunities["incremental_revenue"].sum()
        if "incremental_revenue" in opportunities
        else 0
    )

    total_contribution = (
        opportunities["incremental_contribution"].sum()
        if "incremental_contribution" in opportunities
        else 0
    )

    cols = st.columns(3)

    cols[0].metric(
        "Illustrative Revenue Upside",
        fmt_money(total_revenue),
    )

    cols[1].metric(
        "Illustrative Contribution Upside",
        fmt_money(total_contribution),
    )

    cols[2].metric(
        "Opportunity Cases",
        str(len(opportunities)),
    )

    display = opportunities.copy()

    for col in [
        "current_value",
        "target_value",
    ]:
        if col in display.columns:
            display[col] = display[col].round(2)

    for col in [
        "incremental_orders",
        "incremental_revenue",
        "incremental_contribution",
    ]:
        if col in display.columns:
            display[col] = display[col].round(0)

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Opportunity values are scenario calculations based on "
        "explicit assumptions. They are not forecasts."
    )


# ============================================================
# DEEP DIVE: PRIORITISATION
# ============================================================

with tab_priority:

    st.subheader("Initiative Prioritisation")

    st.caption(
        "Impact × Confidence × Speed × Economics ÷ Effort"
    )

    st.plotly_chart(
        initiative_priority_chart(
            decision["initiatives"]
        ),
        use_container_width=True,
    )

    st.dataframe(
        decision["initiatives"],
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# DEEP DIVE: EXPERIMENT
# ============================================================

with tab_experiment:

    st.subheader("Experiment Designer")

    render_experiment(
        top_experiment
    )

    st.divider()

    st.subheader("Measurement & Guardrails")

    guardrails = top_experiment.get(
        "guardrails",
        [],
    )

    if guardrails:

        guardrail_rows = []

        for guardrail in guardrails:
            guardrail_rows.append(
                {
                    "Guardrail": guardrail,
                    "Baseline": "Current period",
                    "Scale Rule": "Remain stable or improve",
                }
            )

        st.dataframe(
            pd.DataFrame(guardrail_rows),
            use_container_width=True,
            hide_index=True,
        )

        st.success(
            "Scale only if the primary KPI reaches the expected "
            "uplift threshold and guardrails remain within acceptable "
            "limits."
        )

    else:
        st.warning(
            "No guardrails were defined."
        )


# ============================================================
# DEEP DIVE: DECISION EXPLANATION
# ============================================================

with tab_explanation:

    st.subheader("Decision Explanation")

    diagnosis = decision["diagnosis"]
    latest_diagnosis = diagnosis.get(
        "latest",
        {},
    )

    cols = st.columns(4)

    cols[0].metric(
        "Revenue Gap",
        fmt_signed_pct(
            latest_diagnosis.get(
                "revenue_gap_pct",
                0,
            )
        ),
    )

    cols[1].metric(
        "MAU Gap",
        fmt_signed_pct(
            latest_diagnosis.get(
                "mau_gap_pct",
                0,
            )
        ),
    )

    cols[2].metric(
        "OPU Gap",
        fmt_signed_pct(
            latest_diagnosis.get(
                "opu_gap_pct",
                0,
            )
        ),
    )

    cols[3].metric(
        "ARPU Gap",
        fmt_signed_pct(
            latest_diagnosis.get(
                "arpu_gap_pct",
                0,
            )
        ),
    )

    st.markdown("### Decision Chain")

    revenue_gap = safe_float(latest_diagnosis.get("revenue_gap_pct", latest.get("revenue_plan_variance_pct", 0)))
    mau_gap = safe_float(latest_diagnosis.get("mau_gap_pct", latest.get("mau_plan_variance_pct", 0)))
    opu_gap = safe_float(latest_diagnosis.get("opu_gap_pct", latest.get("opu_plan_variance_pct", 0)))
    arpu_gap = safe_float(latest_diagnosis.get("arpu_gap_pct", latest.get("arpu_plan_variance_pct", 0)))

    drivers = diagnosis.get("drivers", [])
    evidence = diagnosis.get("evidence", [])
    attribution = diagnosis.get("driver_attribution", [])
    recommendation = decision.get("recommendation", {})

    if attribution:
        driver_parts = []
        for item in attribution[:3]:
            driver_parts.append(
                f"{item.get('driver', 'Driver')} contributed "
                f"{fmt_money(item.get('revenue_impact', 0))} to the revenue gap "
                f"({safe_float(item.get('gap_pct', 0)):+.1f}% vs plan)"
            )
        driver_text = "; ".join(driver_parts) + "."
    elif drivers:
        driver_text = "The deterministic diagnosis identified: " + ", ".join(str(driver) for driver in drivers[:3]) + "."
    else:
        driver_text = "The deterministic diagnosis did not identify a sufficiently strong driver."

    root_cause_text = (
        "The strongest evidence-backed constraints are "
        + ", ".join(str(driver) for driver in drivers[:3])
        + "."
        if drivers
        else "No sufficiently strong root-cause driver was identified."
    )

    opportunity_text = "No quantified opportunity was generated."
    opportunities = decision.get("opportunities")
    if opportunities is not None and not opportunities.empty:
        total_revenue = safe_float(
            opportunities["incremental_revenue"].sum()
            if "incremental_revenue" in opportunities.columns else 0
        )
        total_contribution = safe_float(
            opportunities["incremental_contribution"].sum()
            if "incremental_contribution" in opportunities.columns else 0
        )
        opportunity_text = (
            f"{len(opportunities)} scenario case(s) quantify {fmt_money(total_revenue)} "
            f"of illustrative revenue upside and {fmt_money(total_contribution)} "
            "of contribution upside. These cases are not forecasts."
        )

    if recommendation.get("status") == "ready":
        action_text = (
            f"Prioritise {recommendation.get('initiative', 'the top-ranked initiative')} "
            f"for {recommendation.get('target_segment', 'the specified target segment')}. "
            f"It addresses {recommendation.get('target_problem', 'the identified problem')} "
            f"through the {recommendation.get('driver_family', 'identified')} driver family, "
            f"with decision score {safe_float(recommendation.get('decision_score', 0)):.2f} "
            f"and evidence alignment {safe_float(recommendation.get('evidence_alignment_score', 0)):.2f}."
        )
    else:
        action_text = recommendation.get(
            "reason",
            "No initiative can currently be prioritised from the supplied evidence.",
        )

    experiment_text = "No experiment is available."
    if top_experiment and top_experiment.get("status") != "insufficient evidence":
        experiment_text = (
            f"Test {top_experiment.get('initiative', 'the recommended initiative')} "
            f"with {top_experiment.get('primary_kpi', 'the primary KPI')} as the primary KPI. "
            f"Expected uplift: {fmt_pct(top_experiment.get('expected_uplift_pct', 0))}. "
            f"Target: {top_experiment.get('target_population', 'specified target population')}."
        )

    measurement_text = (
        f"Scale only when the supplied decision threshold is met and the "
        f"guardrails remain acceptable: {top_experiment.get('decision_threshold', 'not specified')}."
        if top_experiment and top_experiment.get("status") != "insufficient evidence"
        else "Measurement conditions are not available because there is insufficient evidence to define an experiment."
    )

    chain = [
        (
            "1",
            "Performance",
            f"Latest period {latest.get('week', 'N/A')}: revenue is {revenue_gap:+.1f}% vs plan; "
            f"MAU is {mau_gap:+.1f}%, OPU is {opu_gap:+.1f}%, and ARPU is {arpu_gap:+.1f}% vs plan."
        ),
        (
            "2",
            "Drivers",
            driver_text
        ),
        (
            "3",
            "Root Cause",
            root_cause_text
        ),
        (
            "4",
            "Opportunity",
            opportunity_text
        ),
        (
            "5",
            "Action",
            action_text
        ),
        (
            "6",
            "Experiment",
            experiment_text
        ),
        (
            "7",
            "Measurement",
            measurement_text
        ),
    ]

    for number, title, explanation in chain:
        with st.container(border=True):
            cols = st.columns([0.5, 1.7, 5.8])
            cols[0].markdown(f"### {number}")
            cols[1].markdown(f"**{title}**")
            cols[2].write(explanation)

    st.caption(
        "The chain above is generated from the deterministic decision package. "
        "The optional Gemini narrative can add executive context without changing the underlying numbers."
    )

    st.markdown("### Supporting Evidence")
    evidence = diagnosis.get(
        "evidence",
        [],
    )

    if evidence:

        with st.expander(
            "View supporting evidence",
            expanded=False,
        ):
            st.dataframe(
                pd.DataFrame(evidence),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# DEEP DIVE: DATA QUALITY
# ============================================================

with tab_quality:

    st.subheader("Data Quality")

    score = safe_float(
        validation["data_quality_score"]
    )

    status = validation["overall_status"]

    cols = st.columns(3)

    cols[0].metric(
        "Data Quality Score",
        f"{score:.0f}/100",
    )

    cols[1].metric(
        "Validation Status",
        status,
    )

    cols[2].metric(
        "Latest Period",
        str(latest["week"]),
    )

    validation_rows = _collect_validation_detail_rows(validation)

    if validation_rows:

        st.dataframe(
            pd.DataFrame(validation_rows),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander(
        "View complete validation output",
        expanded=False,
    ):
        st.json(validation)

    st.caption(
        "A WARNING can represent a non-critical rounding difference. "
        "Critical structural validation failures should stop "
        "downstream analysis."
    )
