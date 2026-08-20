from __future__ import annotations

from typing import Dict
import pandas as pd


def build_experiment_plan(initiative_row: pd.Series, diagnosis: Dict, latest_kpi: pd.Series) -> Dict:
    name = str(initiative_row["initiative"])
    segment = str(initiative_row["target_segment"])
    problem = str(initiative_row["target_problem"])
    owner = str(initiative_row["owner"])
    expected_uplift = float(initiative_row["expected_order_uplift"])

    primary = {
        "Retention": "repeat purchase rate",
        "Frequency": "orders per user",
        "Conversion": "checkout completion rate",
        "Monetisation": "ARPU",
        "Revenue": "revenue per active user",
    }.get(problem, "orders per user")

    return {
        "initiative": name,
        "hypothesis": f"If {segment} users receive the {name.lower()} intervention, then {primary} will improve because the observed {problem.lower()} constraint is addressed.",
        "target_population": segment,
        "control": "Business-as-usual experience / holdout group",
        "treatment": name,
        "primary_kpi": primary,
        "secondary_kpis": ["orders", "revenue", "contribution margin"],
        "expected_uplift_pct": expected_uplift,
        "guardrails": [
            "contribution margin per order",
            "fulfilment or service issue rate",
            "refund or return rate",
        ],
        "decision_threshold": f"Scale only if the primary KPI reaches at least the expected {expected_uplift:.1f}% uplift and guardrails do not materially deteriorate.",
        "owner": owner,
        "timeline": f"Time-to-impact score: {int(initiative_row['time_to_impact'])}/5",
        "evidence": diagnosis.get("evidence", []),
        "baseline_week": str(latest_kpi["week"]),
    }


def build_top_experiment(initiatives: pd.DataFrame, diagnosis: Dict, latest_kpi: pd.Series) -> Dict:
    if initiatives.empty:
        return {"status": "insufficient evidence", "reason": "No initiatives are available."}
    return build_experiment_plan(initiatives.iloc[0], diagnosis, latest_kpi)
