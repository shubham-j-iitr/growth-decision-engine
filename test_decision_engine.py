from pathlib import Path

import pandas as pd
import pytest

from engine.decision_engine import (
    _driver_attribution,
    build_decision_package,
    prioritise_initiatives,
)
from engine.funnel_engine import build_funnel_analysis
from engine.kpi_engine import build_kpi_analysis


BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

FILES = {
    "kpi": "weekly_kpis.csv",
    "plan": "weekly_plan.csv",
    "funnel": "funnel.csv",
    "segments": "segments.csv",
    "cohorts": "cohorts.csv",
    "initiatives": "initiatives.csv",
}


def load_data():
    return {
        key: pd.read_csv(DATA / filename)
        for key, filename in FILES.items()
    }


def build_package():
    data = load_data()
    kpi_analysis = build_kpi_analysis(data["kpi"], data["plan"])
    funnel_analysis = build_funnel_analysis(data["funnel"], data["kpi"])
    return data, kpi_analysis, funnel_analysis


def test_recommendation_is_evidence_aligned():
    data, kpi_analysis, funnel_analysis = build_package()

    decision = build_decision_package(
        kpi_analysis,
        funnel_analysis,
        data["segments"],
        data["cohorts"],
        data["initiatives"],
    )

    recommendation = decision["recommendation"]

    assert recommendation["status"] == "ready"
    assert recommendation["initiative"] == "Occasional User Re-engagement"
    assert recommendation["target_segment"] == "Occasional"
    assert recommendation["decision_score"] > 0
    assert recommendation["evidence_alignment_score"] > 0


def test_ranked_initiatives_expose_evidence_layer():
    data, kpi_analysis, funnel_analysis = build_package()

    decision = build_decision_package(
        kpi_analysis,
        funnel_analysis,
        data["segments"],
        data["cohorts"],
        data["initiatives"],
    )

    ranked = decision["initiatives"]

    required_columns = {
        "priority_score",
        "driver_family",
        "driver_evidence_score",
        "opportunity_alignment_score",
        "segment_alignment_score",
        "evidence_alignment_score",
        "decision_score",
    }

    assert required_columns.issubset(ranked.columns)
    assert ranked["decision_score"].is_monotonic_decreasing


def test_high_revenue_but_weakly_aligned_initiative_does_not_automatically_win():
    data, kpi_analysis, funnel_analysis = build_package()

    initiatives = data["initiatives"].copy()
    initiatives.loc[len(initiatives)] = [
        "Large Acquisition Bet",
        "Acquisition",
        "All",
        20.0,
        5.0,
        50_000_000,
        1,
        5,
        1,
        2.0,
        1,
        "Growth",
    ]

    full_decision = build_decision_package(
        kpi_analysis,
        funnel_analysis,
        data["segments"],
        data["cohorts"],
        initiatives,
    )

    ranked = full_decision["initiatives"]

    assert ranked.iloc[0]["initiative"] == "Occasional User Re-engagement"
    assert "Large Acquisition Bet" in set(ranked["initiative"])
    assert ranked.loc[
        ranked["initiative"] == "Large Acquisition Bet", "evidence_alignment_score"
    ].iloc[0] < ranked.iloc[0]["evidence_alignment_score"]


def test_above_plan_acquisition_has_positive_revenue_attribution():
    data, kpi_analysis, _ = build_package()

    attribution = _driver_attribution(kpi_analysis["weekly"].iloc[-1])
    acquisition = next(
        item for item in attribution if item["driver"] == "Acquisition / MAU"
    )

    # Demo W12 MAU is above plan, so acquisition cannot be a negative
    # revenue driver. The attribution must also preserve the revenue-gap
    # reconciliation across all three multiplicative drivers.
    assert acquisition["gap_pct"] > 0
    assert acquisition["revenue_impact"] > 0

    total_impact = sum(item["revenue_impact"] for item in attribution)
    latest = kpi_analysis["weekly"].iloc[-1]
    revenue_gap = latest["revenue"] - latest["revenue_plan"]
    assert abs(total_impact - revenue_gap) < 1e-6


@pytest.mark.parametrize(
    "positive_driver_index,driver_name",
    [
        (0, "Acquisition / MAU"),
        (1, "Frequency / OPU"),
        (2, "Monetisation / AOV"),
    ],
)
def test_any_above_plan_driver_keeps_positive_attribution_even_when_total_revenue_is_below_plan(
    positive_driver_index,
    driver_name,
):
    """A positive driver must never be flipped negative by a negative total gap.

    This deliberately creates a mixed scenario where one driver is above plan
    but the other two are far below plan, so total revenue is still below plan.
    This is the exact failure mode that previously affected MAU and must work
    identically for MAU, OPU and AOV.
    """
    latest = pd.Series(
        {
            "mau": 100.0,
            "mau_plan": 100.0,
            "opu": 100.0,
            "opu_plan": 100.0,
            "aov": 100.0,
            "aov_plan": 100.0,
        }
    )

    actual_values = [80.0, 80.0, 80.0]
    actual_values[positive_driver_index] = 101.0

    latest["mau"] = actual_values[0]
    latest["opu"] = actual_values[1]
    latest["aov"] = actual_values[2]
    latest["revenue"] = actual_values[0] * actual_values[1] * actual_values[2]
    latest["revenue_plan"] = 100.0 * 100.0 * 100.0

    attribution = _driver_attribution(latest)
    target = next(item for item in attribution if item["driver"] == driver_name)

    # The selected driver is above plan and must therefore contribute positively
    # even though total revenue is below plan because the other two drivers are weak.
    assert target["gap_pct"] > 0
    assert target["revenue_impact"] > 0

    # All three driver contributions must reconcile exactly to the total gap.
    total_impact = sum(item["revenue_impact"] for item in attribution)
    revenue_gap = latest["revenue"] - latest["revenue_plan"]
    assert revenue_gap < 0
    assert abs(total_impact - revenue_gap) < 1e-6
