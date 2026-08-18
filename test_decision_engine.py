from pathlib import Path

import pandas as pd

from engine.decision_engine import (
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
