from pathlib import Path

import pandas as pd

from engine.validation import (
    DATASET_CONFIG,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_WARNING,
    calculate_data_quality_score,
    check_week_values,
    validate_data_package,
    validate_dataset,
)

BASE = Path(__file__).resolve().parent
DATA_PATH = BASE / "data"

DATASET_FILES = {
    "kpi": "weekly_kpis.csv",
    "plan": "weekly_plan.csv",
    "funnel": "funnel.csv",
    "segments": "segments.csv",
    "cohorts": "cohorts.csv",
    "initiatives": "initiatives.csv",
}


def load_data_package():
    return {
        key: pd.read_csv(DATA_PATH / filename)
        for key, filename in DATASET_FILES.items()
    }


def test_demo_dataset_has_all_required_datasets():
    data = load_data_package()
    assert set(data) == set(DATASET_CONFIG)


def test_demo_dataset_passes_validation():
    data = load_data_package()
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_PASS
    assert results["data_quality_score"] == 100


def test_demo_dataset_all_individual_datasets_pass():
    data = load_data_package()
    results = validate_data_package(data)
    for key in DATASET_FILES:
        assert results[key]["overall_status"] == STATUS_PASS


def test_demo_dataset_cross_dataset_checks_pass():
    data = load_data_package()
    results = validate_data_package(data)
    for result in results["cross_dataset"].values():
        assert result["status"] == STATUS_PASS


def test_missing_required_column_fails():
    data = load_data_package()
    data["kpi"] = data["kpi"].drop(columns=["revenue"])
    result = validate_dataset("kpi", data["kpi"])
    assert result["overall_status"] == STATUS_FAIL
    assert "revenue" in result["required_columns"]["missing_columns"]


def test_invalid_numeric_value_fails():
    data = load_data_package()
    data["kpi"]["revenue"] = data["kpi"]["revenue"].astype(object)
    data["kpi"].loc[0, "revenue"] = "not-a-number"
    result = validate_dataset("kpi", data["kpi"])
    assert result["overall_status"] == STATUS_FAIL
    assert result["numeric_types"]["invalid_numeric_values"]["revenue"] == 1


def test_negative_value_fails():
    data = load_data_package()
    data["kpi"].loc[0, "revenue"] = -100
    result = validate_dataset("kpi", data["kpi"])
    assert result["overall_status"] == STATUS_FAIL
    assert result["negative_values"]["negative_values"]["revenue"] == 1


def test_duplicate_week_fails():
    data = load_data_package()
    data["kpi"].loc[1, "week"] = data["kpi"].loc[0, "week"]
    result = validate_dataset("kpi", data["kpi"])
    assert result["overall_status"] == STATUS_FAIL
    assert result["week_values"]["duplicate_weeks"] > 0


def test_invalid_week_format_fails():
    data = load_data_package()
    data["kpi"].loc[0, "week"] = "INVALID"
    result = validate_dataset("kpi", data["kpi"])
    assert result["overall_status"] == STATUS_FAIL
    assert "INVALID" in result["week_values"]["invalid_weeks"]

def test_week_identifiers_support_more_than_99_weeks():
    data = pd.DataFrame(
        {
            "week": [
                "W01",
                "W09",
                "W10",
                "W99",
                "W100",
                "W101",
                "W219",
            ]
        }
    )

    result = check_week_values(data)

    assert result["status"] == STATUS_PASS
    assert result["invalid_weeks"] == []
    assert result["duplicate_weeks"] == 0

def test_funnel_stage_order_failure():
    data = load_data_package()
    data["funnel"].loc[0, "menu_viewers"] = (
        data["funnel"].loc[0, "restaurant_viewers"] + 1
    )
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_FAIL
    assert results["cross_dataset"]["funnel_stage_consistency"]["status"] == STATUS_FAIL


def test_segment_aggregate_mismatch_fails():
    data = load_data_package()
    data["segments"].loc[0, "revenue"] += 10000
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_FAIL
    assert results["cross_dataset"]["segment_aggregate_consistency"]["status"] == STATUS_FAIL


def test_segment_period_coverage_failure():
    data = load_data_package()
    data["segments"] = data["segments"][data["segments"]["week"] != "W12"]
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_FAIL
    assert results["cross_dataset"]["segment_period_coverage"]["status"] == STATUS_FAIL


def test_missing_dataset_fails():
    data = load_data_package()
    del data["cohorts"]
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_FAIL
    assert "cohorts" in results["dataset_presence"]["missing_datasets"]


def test_malformed_cohort_data_fails():
    data = load_data_package()
    data["cohorts"].loc[0, "week_2_retained_users"] = (
        data["cohorts"].loc[0, "users"] + 1
    )
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_FAIL


def test_missing_required_column_does_not_crash_cross_dataset_validation():
    data = load_data_package()
    data["kpi"] = data["kpi"].drop(columns=["revenue"])
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_FAIL
    assert results["kpi"]["overall_status"] == STATUS_FAIL
    assert "revenue" in results["kpi"]["required_columns"]["missing_columns"]
    assert results["cross_dataset"]["segment_aggregate_consistency"]["status"] == STATUS_FAIL


def test_warning_is_non_blocking():
    data = load_data_package()
    data["segments"]["revenue"] = data["segments"]["revenue"].astype(float)
    data["segments"].loc[0, "revenue"] += 0.5
    results = validate_data_package(data)
    assert results["overall_status"] == STATUS_WARNING
    assert results["cross_dataset"]["segment_aggregate_consistency"]["status"] == STATUS_WARNING


def test_warning_does_not_block_analysis():
    data = load_data_package()
    data["segments"]["revenue"] = data["segments"]["revenue"].astype(float)
    data["segments"].loc[0, "revenue"] += 0.5
    results = validate_data_package(data)
    assert results["overall_status"] != STATUS_FAIL


def test_large_reconciliation_difference_is_not_warning():
    data = load_data_package()
    data["segments"].loc[0, "revenue"] += 10000
    results = validate_data_package(data)
    assert results["cross_dataset"]["segment_aggregate_consistency"]["status"] == STATUS_FAIL


if __name__ == "__main__":
    data = load_data_package()
    results = validate_data_package(data)
    score = calculate_data_quality_score(results)

    print("\n==============================")
    print("GROWTH DATA VALIDATION")
    print("==============================")
    print(f"Datasets checked: {len(data)}/{len(DATASET_CONFIG)}")

    for key in DATASET_FILES:
        dataset_result = results[key]
        print(
            f"{DATASET_CONFIG[key]['label']}: "
            f"{dataset_result['overall_status']} "
            f"({dataset_result['data_quality_score']}/100)"
        )

    print("\nCross-dataset checks:")
    for name, result in results.get("cross_dataset", {}).items():
        print(f"{name}: {result['status']}")

    print("\n------------------------------")
    print(f"OVERALL STATUS: {results['overall_status']}")
    print(f"DATA QUALITY SCORE: {score}/100")
    print("------------------------------")

    if results["overall_status"] in {STATUS_PASS, STATUS_WARNING}:
        print("\nVALIDATION TEST: PASS")
    else:
        print("\nVALIDATION TEST: FAIL")
