from __future__ import annotations

import re
from typing import Dict, List, Mapping

import pandas as pd

STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_FAIL = "FAIL"
WEEK_PATTERN = re.compile(r"^W(?:0[1-9]|[1-9]\d+)$")
COHORT_RETAINED_PATTERN = re.compile(r"^week_(\d+)_retained_users$")

# The input contract contains raw business facts only.
# Derived KPIs are calculated by the deterministic engines.
WEEKLY_KPI_REQUIRED_COLUMNS = [
    "week", "mau", "orders", "revenue", "new_users",
    "acquisition_spend", "contribution_profit",
]

WEEKLY_PLAN_REQUIRED_COLUMNS = [
    "week", "mau_plan", "orders_plan", "revenue_plan", "cm_plan",
]

FUNNEL_REQUIRED_COLUMNS = [
    "week", "food_visitors", "restaurant_viewers", "menu_viewers",
    "cart_users", "checkout_users",
]

SEGMENTS_REQUIRED_COLUMNS = [
    "week", "segment", "users", "orders", "revenue",
    "retained_users", "promo_users", "contribution_profit",
]

# Cohorts are intentionally dynamic. The dataset requires at least one
# retention week and accepts week_1 ... week_N_retained_users.
COHORT_BASE_REQUIRED_COLUMNS = ["cohort", "users"]

INITIATIVES_REQUIRED_COLUMNS = [
    "initiative", "target_problem", "target_segment",
    "expected_order_uplift", "expected_conversion_uplift",
    "expected_revenue", "implementation_effort", "confidence",
    "time_to_impact", "cm_impact", "risk", "owner",
]

WEEKLY_KPI_NUMERIC_COLUMNS = WEEKLY_KPI_REQUIRED_COLUMNS[1:]
WEEKLY_PLAN_NUMERIC_COLUMNS = WEEKLY_PLAN_REQUIRED_COLUMNS[1:]
FUNNEL_NUMERIC_COLUMNS = FUNNEL_REQUIRED_COLUMNS[1:]
SEGMENTS_NUMERIC_COLUMNS = SEGMENTS_REQUIRED_COLUMNS[2:]
INITIATIVES_NUMERIC_COLUMNS = INITIATIVES_REQUIRED_COLUMNS[3:11]

DATASET_CONFIG = {
    "kpi": {
        "label": "Weekly KPIs",
        "required_columns": WEEKLY_KPI_REQUIRED_COLUMNS,
        "numeric_columns": WEEKLY_KPI_NUMERIC_COLUMNS,
        "week_column": "week",
        "unique_columns": ["week"],
        "non_negative_columns": WEEKLY_KPI_NUMERIC_COLUMNS,
    },
    "plan": {
        "label": "Weekly Plan",
        "required_columns": WEEKLY_PLAN_REQUIRED_COLUMNS,
        "numeric_columns": WEEKLY_PLAN_NUMERIC_COLUMNS,
        "week_column": "week",
        "unique_columns": ["week"],
        "non_negative_columns": WEEKLY_PLAN_NUMERIC_COLUMNS,
    },
    "funnel": {
        "label": "Funnel",
        "required_columns": FUNNEL_REQUIRED_COLUMNS,
        "numeric_columns": FUNNEL_NUMERIC_COLUMNS,
        "week_column": "week",
        "unique_columns": ["week"],
        "non_negative_columns": FUNNEL_NUMERIC_COLUMNS,
    },
    "segments": {
        "label": "Segments",
        "required_columns": SEGMENTS_REQUIRED_COLUMNS,
        "numeric_columns": SEGMENTS_NUMERIC_COLUMNS,
        "week_column": "week",
        "unique_columns": ["week", "segment"],
        "non_negative_columns": SEGMENTS_NUMERIC_COLUMNS,
    },
    "cohorts": {
        "label": "Cohorts",
        "required_columns": COHORT_BASE_REQUIRED_COLUMNS,
        "numeric_columns": [],
        "week_column": None,
        "unique_columns": ["cohort"],
        "non_negative_columns": [],
    },
    "initiatives": {
        "label": "Initiatives",
        "required_columns": INITIATIVES_REQUIRED_COLUMNS,
        "numeric_columns": INITIATIVES_NUMERIC_COLUMNS,
        "week_column": None,
        "unique_columns": ["initiative"],
        "non_negative_columns": [
            "expected_order_uplift", "expected_conversion_uplift",
            "expected_revenue", "implementation_effort", "confidence",
            "time_to_impact", "risk",
        ],
    },
}


def _result(status: str, message: str, **details) -> Dict:
    return {
        "status": status,
        "passed": status != STATUS_FAIL,
        "message": message,
        **details,
    }


def _cohort_week_columns(df: pd.DataFrame) -> List[str]:
    """Return all week_N_retained_users columns in numeric order."""
    matches = []
    for column in df.columns:
        match = COHORT_RETAINED_PATTERN.match(str(column))
        if match:
            matches.append((int(match.group(1)), column))
    return [column for _, column in sorted(matches, key=lambda item: item[0])]


def validate_required_columns(df: pd.DataFrame, required_columns: List[str]) -> Dict:
    missing = [c for c in required_columns if c not in df.columns]
    return _result(
        STATUS_FAIL if missing else STATUS_PASS,
        "Required columns are missing." if missing else "All required columns are present.",
        missing_columns=missing,
    )


def check_missing_values(df: pd.DataFrame) -> Dict:
    missing = {c: int(n) for c, n in df.isna().sum().items() if n > 0}
    return _result(
        STATUS_FAIL if missing else STATUS_PASS,
        "Missing values were found." if missing else "No missing values were found.",
        missing_values=missing,
    )


def check_numeric_types(df: pd.DataFrame, columns: List[str]) -> Dict:
    invalid = {}
    for c in columns:
        if c in df.columns:
            count = int(pd.to_numeric(df[c], errors="coerce").isna().sum())
            if count:
                invalid[c] = count
    return _result(
        STATUS_FAIL if invalid else STATUS_PASS,
        "Non-numeric values were found in numeric columns." if invalid else "All numeric columns are valid.",
        invalid_numeric_values=invalid,
    )


def check_negative_values(df: pd.DataFrame, columns: List[str]) -> Dict:
    invalid = {}
    for c in columns:
        if c in df.columns:
            numeric = pd.to_numeric(df[c], errors="coerce")
            count = int((numeric < 0).fillna(False).sum())
            if count:
                invalid[c] = count
    return _result(
        STATUS_FAIL if invalid else STATUS_PASS,
        "Negative values were found." if invalid else "No invalid negative values were found.",
        negative_values=invalid,
    )


def check_week_values(df: pd.DataFrame, week_column: str = "week", require_unique: bool = True) -> Dict:
    if week_column not in df.columns:
        return _result(STATUS_FAIL, f"The {week_column} column is missing.", invalid_weeks=[])
    invalid = [str(x) for x in df[week_column] if not WEEK_PATTERN.match(str(x))]
    duplicates = int(df[week_column].duplicated().sum()) if require_unique else 0
    failed = bool(invalid or duplicates)
    return _result(
        STATUS_FAIL if failed else STATUS_PASS,
        "Week identifiers are invalid or duplicated." if failed else "Week identifiers are valid and unique.",
        invalid_weeks=invalid,
        duplicate_weeks=duplicates,
    )


def check_key_uniqueness(df: pd.DataFrame, columns: List[str]) -> Dict:
    if any(c not in df.columns for c in columns):
        return _result(
            STATUS_FAIL,
            "The uniqueness key cannot be checked because one or more columns are missing.",
            duplicate_keys=0,
            key_columns=columns,
        )
    duplicates = int(df.duplicated(subset=columns).sum())
    return _result(
        STATUS_FAIL if duplicates else STATUS_PASS,
        "Duplicate business keys were found." if duplicates else "Business keys are unique.",
        duplicate_keys=duplicates,
        key_columns=columns,
    )


def check_cohort_schema(df: pd.DataFrame) -> Dict:
    """Validate that cohort retention columns are dynamic, numeric and contiguous."""
    retained_columns = _cohort_week_columns(df)

    if not retained_columns:
        return _result(
            STATUS_FAIL,
            "No cohort retention columns were found. Expected week_1_retained_users through week_N_retained_users.",
            retention_columns=[],
        )

    week_numbers = [
        int(COHORT_RETAINED_PATTERN.match(column).group(1))
        for column in retained_columns
    ]
    expected = list(range(1, max(week_numbers) + 1))
    missing_weeks = [week for week in expected if week not in week_numbers]

    status = STATUS_FAIL if missing_weeks else STATUS_PASS
    message = (
        "Cohort retention week columns contain gaps."
        if missing_weeks
        else "Cohort retention columns are present and sequential."
    )

    return _result(
        status,
        message,
        retention_columns=retained_columns,
        week_numbers=week_numbers,
        missing_weeks=missing_weeks,
        latest_week=max(week_numbers),
    )


def check_cohort_integrity(df: pd.DataFrame, retained_columns: List[str]) -> Dict:
    """Ensure retention counts cannot exceed users or increase across weeks."""
    if not retained_columns:
        return _result(STATUS_FAIL, "Cohort retention columns are missing.", invalid_rows=[])

    invalid_rows = []

    users_numeric = pd.to_numeric(df["users"], errors="coerce")
    retained_numeric = {
        column: pd.to_numeric(df[column], errors="coerce")
        for column in retained_columns
    }

    for index in df.index:
        users = users_numeric.loc[index]
        values = [retained_numeric[column].loc[index] for column in retained_columns]

        if pd.isna(users) or any(pd.isna(value) for value in values):
            continue

        if any(value > users for value in values):
            invalid_rows.append({
                "row": int(index),
                "cohort": str(df.loc[index, "cohort"]),
                "reason": "Retained users exceed original cohort users.",
            })
            continue

        for previous, current in zip(values, values[1:]):
            if current > previous:
                invalid_rows.append({
                    "row": int(index),
                    "cohort": str(df.loc[index, "cohort"]),
                    "reason": "Retention increases between cohort weeks.",
                })
                break

    return _result(
        STATUS_FAIL if invalid_rows else STATUS_PASS,
        "Cohort retention values are structurally invalid." if invalid_rows else "Cohort retention values are structurally consistent.",
        invalid_rows=invalid_rows,
    )


def check_funnel_stage_order(df: pd.DataFrame) -> Dict:
    # MAU is supplied by weekly_kpis, so this local check is applied after
    # the cross-dataset join in validate_cross_dataset_consistency.
    return _result(STATUS_PASS, "Funnel stage structure will be checked against weekly KPI MAU.")


def validate_dataset(name: str, df: pd.DataFrame) -> Dict:
    if name not in DATASET_CONFIG:
        return _result(STATUS_FAIL, f"Unknown dataset: {name}.")

    config = DATASET_CONFIG[name]
    results = {
        "required_columns": validate_required_columns(df, config["required_columns"])
    }
    if results["required_columns"]["status"] == STATUS_FAIL:
        return finalise_validation(results)

    if name == "cohorts":
        cohort_schema = check_cohort_schema(df)
        results["cohort_schema"] = cohort_schema
        if cohort_schema["status"] == STATUS_FAIL:
            return finalise_validation(results)

        retained_columns = cohort_schema["retention_columns"]
        results["missing_values"] = check_missing_values(df)
        results["numeric_types"] = check_numeric_types(
            df,
            ["users"] + retained_columns,
        )
        results["negative_values"] = check_negative_values(
            df,
            ["users"] + retained_columns,
        )
        results["key_uniqueness"] = check_key_uniqueness(df, config["unique_columns"])
        results["cohort_integrity"] = check_cohort_integrity(df, retained_columns)
        return finalise_validation(results)

    results["missing_values"] = check_missing_values(df)
    results["numeric_types"] = check_numeric_types(df, config["numeric_columns"])
    results["negative_values"] = check_negative_values(df, config.get("non_negative_columns", []))

    week_column = config.get("week_column")
    if week_column:
        results["week_values"] = check_week_values(
            df,
            week_column=week_column,
            require_unique=config.get("unique_columns") == [week_column],
        )

    if config.get("unique_columns"):
        results["key_uniqueness"] = check_key_uniqueness(df, config["unique_columns"])

    return finalise_validation(results)


def validate_cross_dataset_consistency(data: Mapping[str, pd.DataFrame]) -> Dict:
    """Run cross-dataset checks defensively without crashing on malformed input."""
    results = {}

    weekly_names = ["kpi", "plan", "funnel", "segments"]
    available = [
        name
        for name in weekly_names
        if name in data and isinstance(data[name], pd.DataFrame)
    ]

    # 1. Weekly period alignment
    if len(available) == len(weekly_names):
        missing_week_columns = {
            name: ["week"]
            for name in weekly_names
            if "week" not in data[name].columns
        }

        if missing_week_columns:
            results["weekly_period_alignment"] = _result(
                STATUS_FAIL,
                "Weekly period alignment cannot be checked because one or more weekly datasets are missing the week column.",
                missing_columns=missing_week_columns,
            )
        else:
            week_sets = {
                name: set(str(x) for x in data[name]["week"].dropna().tolist())
                for name in weekly_names
            }

            reference = week_sets["kpi"]
            mismatches = {
                name: sorted(reference.symmetric_difference(week_sets[name]))
                for name in weekly_names
                if week_sets[name] != reference
            }

            results["weekly_period_alignment"] = _result(
                STATUS_FAIL if mismatches else STATUS_PASS,
                (
                    "Weekly datasets do not cover the same periods."
                    if mismatches
                    else "Weekly datasets are aligned to the same periods."
                ),
                mismatched_periods=mismatches,
            )

    # 2. Funnel stage consistency
    if "kpi" in data and "funnel" in data:
        kpi = data["kpi"]
        funnel = data["funnel"]

        required_kpi_columns = {"week", "mau"}
        required_funnel_columns = {
            "week",
            "food_visitors",
            "restaurant_viewers",
            "menu_viewers",
            "cart_users",
            "checkout_users",
        }

        missing_kpi_columns = sorted(required_kpi_columns - set(kpi.columns))
        missing_funnel_columns = sorted(
            required_funnel_columns - set(funnel.columns)
        )

        if missing_kpi_columns or missing_funnel_columns:
            results["funnel_stage_consistency"] = _result(
                STATUS_FAIL,
                "Funnel stage consistency cannot be checked because required columns are missing.",
                missing_kpi_columns=missing_kpi_columns,
                missing_funnel_columns=missing_funnel_columns,
                inconsistent_weeks=[],
            )
        else:
            merged = kpi[["week", "mau"]].merge(
                funnel,
                on="week",
                how="inner",
                validate="one_to_one",
            )

            invalid_rows = merged[
                (merged["food_visitors"] > merged["mau"])
                | (merged["restaurant_viewers"] > merged["food_visitors"])
                | (merged["menu_viewers"] > merged["restaurant_viewers"])
                | (merged["cart_users"] > merged["menu_viewers"])
                | (merged["checkout_users"] > merged["cart_users"])
            ]

            results["funnel_stage_consistency"] = _result(
                STATUS_FAIL if not invalid_rows.empty else STATUS_PASS,
                (
                    "Funnel stages exceed their upstream populations."
                    if not invalid_rows.empty
                    else "Funnel stages are structurally consistent."
                ),
                inconsistent_weeks=invalid_rows["week"].astype(str).tolist(),
            )

    # 3. Segment aggregate consistency
    if "segments" in data and "kpi" in data:
        segments = data["segments"].copy()
        kpi = data["kpi"]

        required_kpi_columns = {"week", "mau", "orders", "revenue"}
        required_segment_columns = {"week", "users", "orders", "revenue"}

        missing_kpi_columns = sorted(
            required_kpi_columns - set(kpi.columns)
        )
        missing_segment_columns = sorted(
            required_segment_columns - set(segments.columns)
        )

        if missing_kpi_columns or missing_segment_columns:
            results["segment_aggregate_consistency"] = _result(
                STATUS_FAIL,
                "Segment aggregate consistency cannot be checked because required columns are missing.",
                missing_kpi_columns=missing_kpi_columns,
                missing_segment_columns=missing_segment_columns,
                inconsistent_weeks=[],
                warning_weeks=[],
                revenue_differences={},
            )
        else:
            grouped = segments.groupby(
                "week",
                as_index=False,
            )[["users", "orders", "revenue"]].sum()

            grouped = grouped.rename(
                columns={
                    "users": "segment_users",
                    "orders": "segment_orders",
                    "revenue": "segment_revenue",
                }
            )

            merged = kpi[["week", "mau", "orders", "revenue"]].merge(
                grouped,
                on="week",
                how="inner",
                validate="one_to_one",
            )

            revenue_difference = (
                merged["revenue"] - merged["segment_revenue"]
            ).abs()

            hard_mismatch = merged[
                (merged["mau"] != merged["segment_users"])
                | (merged["orders"] != merged["segment_orders"])
                | (revenue_difference > 1.0)
            ]

            small_revenue_difference = merged[
                (revenue_difference > 0)
                & (revenue_difference <= 1.0)
                & (merged["mau"] == merged["segment_users"])
                & (merged["orders"] == merged["segment_orders"])
            ]

            if not hard_mismatch.empty:
                status = STATUS_FAIL
                message = "Segment aggregates do not reconcile to weekly KPIs."
            elif not small_revenue_difference.empty:
                status = STATUS_WARNING
                message = (
                    "Segment aggregates reconcile to weekly KPIs within "
                    "a small revenue rounding difference."
                )
            else:
                status = STATUS_PASS
                message = "Segment aggregates reconcile to weekly KPIs."

            results["segment_aggregate_consistency"] = _result(
                status,
                message,
                inconsistent_weeks=hard_mismatch["week"].astype(str).tolist(),
                warning_weeks=small_revenue_difference["week"].astype(str).tolist(),
                revenue_differences={
                    str(row["week"]): float(
                        abs(row["revenue"] - row["segment_revenue"])
                    )
                    for _, row in small_revenue_difference.iterrows()
                },
            )

    # 4. Segment period coverage
    if "segments" in data and "kpi" in data:
        kpi = data["kpi"]
        segments = data["segments"]

        if "week" not in kpi.columns or "week" not in segments.columns:
            results["segment_period_coverage"] = _result(
                STATUS_FAIL,
                "Segment period coverage cannot be checked because the week column is missing.",
                missing_columns={
                    "kpi": [] if "week" in kpi.columns else ["week"],
                    "segments": [] if "week" in segments.columns else ["week"],
                },
                missing_periods=[],
            )
        else:
            kpi_weeks = set(str(x) for x in kpi["week"].dropna().tolist())
            segment_weeks = set(str(x) for x in segments["week"].dropna().tolist())
            missing_from_segments = sorted(kpi_weeks - segment_weeks)

            results["segment_period_coverage"] = _result(
                STATUS_FAIL if missing_from_segments else STATUS_PASS,
                (
                    "One or more KPI periods have no segment data."
                    if missing_from_segments
                    else "All KPI periods have segment data."
                ),
                missing_periods=missing_from_segments,
            )

    return results


def _statuses(results: Dict) -> List[str]:
    statuses = []
    for key, value in results.items():
        if key in {"overall_status", "data_quality_score"}:
            continue
        if isinstance(value, dict) and "status" in value:
            statuses.append(value["status"])
        elif isinstance(value, dict):
            statuses.extend(_statuses(value))
    return statuses


def calculate_data_quality_score(results: Dict) -> float:
    statuses = _statuses(results)
    if not statuses:
        return 0.0
    weights = {STATUS_PASS: 1.0, STATUS_WARNING: 1.0, STATUS_FAIL: 0.0}
    return round(sum(weights[s] for s in statuses) / len(statuses) * 100, 1)


def finalise_validation(results: Dict) -> Dict:
    statuses = _statuses(results)
    results["overall_status"] = (
        STATUS_FAIL if STATUS_FAIL in statuses
        else STATUS_WARNING if STATUS_WARNING in statuses
        else STATUS_PASS
    )
    results["data_quality_score"] = calculate_data_quality_score(results)
    return results


def validate_data_package(data: Mapping[str, pd.DataFrame]) -> Dict:
    """Validate the complete six-dataset raw-data input package."""
    results = {}
    missing_datasets = [name for name in DATASET_CONFIG if name not in data or data[name] is None]
    results["dataset_presence"] = _result(
        STATUS_FAIL if missing_datasets else STATUS_PASS,
        "Required datasets are missing." if missing_datasets else "All required datasets are present.",
        missing_datasets=missing_datasets,
    )

    for name in DATASET_CONFIG:
        if name in data and isinstance(data[name], pd.DataFrame):
            results[name] = validate_dataset(name, data[name])
        else:
            results[name] = _result(
                STATUS_FAIL,
                f"{DATASET_CONFIG[name]['label']} was not uploaded.",
            )

    if not missing_datasets:
        results["cross_dataset"] = validate_cross_dataset_consistency(data)

    return finalise_validation(results)
