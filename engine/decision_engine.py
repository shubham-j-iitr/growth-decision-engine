from __future__ import annotations

import re
from typing import Dict, List

import pandas as pd


COHORT_RETAINED_PATTERN = re.compile(r"^week_(\d+)_retained_users$")
COHORT_RETENTION_PATTERN = re.compile(r"^week_(\d+)_retention$")


def _safe(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _cohort_week_columns(
    cohorts: pd.DataFrame,
    suffix: str = "retained_users",
) -> List[str]:
    """Return cohort week columns in numeric week order.

    Supports week_1 ... week_N rather than hard-coding a maximum week.
    """
    pattern = (
        COHORT_RETAINED_PATTERN
        if suffix == "retained_users"
        else COHORT_RETENTION_PATTERN
    )

    matches = []
    for column in cohorts.columns:
        match = pattern.match(str(column))
        if match:
            matches.append((int(match.group(1)), column))

    return [column for _, column in sorted(matches, key=lambda item: item[0])]


def _derive_segment_metrics(segments: pd.DataFrame) -> pd.DataFrame:
    out = segments.copy()
    out["orders_per_user"] = out["orders"] / out["users"].replace(0, pd.NA)
    out["aov"] = out["revenue"] / out["orders"].replace(0, pd.NA)
    out["retention"] = out["retained_users"] / out["users"].replace(0, pd.NA)
    out["promo_usage"] = out["promo_users"] / out["users"].replace(0, pd.NA)
    out["contribution_margin"] = out["contribution_profit"] / out["revenue"].replace(0, pd.NA)
    return out


def _derive_cohort_metrics(cohorts: pd.DataFrame) -> pd.DataFrame:
    """Derive retention percentages for every supplied cohort week."""
    out = cohorts.copy()
    retained_columns = _cohort_week_columns(out, "retained_users")

    for retained_col in retained_columns:
        match = COHORT_RETAINED_PATTERN.match(retained_col)
        week_number = int(match.group(1))
        retention_col = f"week_{week_number}_retention"
        out[retention_col] = (
            pd.to_numeric(out[retained_col], errors="coerce")
            / pd.to_numeric(out["users"], errors="coerce").replace(0, pd.NA)
        )

    return out


def _driver_attribution(
    latest: pd.Series,
) -> List[Dict]:
    """Attribute the latest revenue gap across MAU, OPU and AOV.

    Revenue is treated as the multiplicative relationship:
        Revenue = MAU * OPU * AOV

    Shapley-style marginal attribution is used so the result does not
    depend on an arbitrary order of changing the three drivers.
    """

    actual = {
        "Acquisition / MAU": _safe(latest.get("mau")),
        "Frequency / OPU": _safe(latest.get("opu")),
        "Monetisation / AOV": _safe(latest.get("aov")),
    }
    plan = {
        "Acquisition / MAU": _safe(latest.get("mau_plan")),
        "Frequency / OPU": _safe(latest.get("opu_plan")),
        "Monetisation / AOV": _safe(latest.get("aov_plan")),
    }

    names = list(actual.keys())
    actual_values = [actual[name] for name in names]
    plan_values = [plan[name] for name in names]

    # If plan/actual values are unavailable, do not invent attribution.
    if any(value <= 0 for value in actual_values + plan_values):
        return []

    import itertools

    def revenue_for(values):
        return values[0] * values[1] * values[2]

    shapley = {name: 0.0 for name in names}

    # Average each driver's marginal contribution across all permutations.
    for permutation in itertools.permutations(range(3)):
        current = plan_values.copy()
        current_revenue = revenue_for(current)

        for index in permutation:
            before = current_revenue
            current[index] = actual_values[index]
            after = revenue_for(current)
            shapley[names[index]] += after - before
            current_revenue = after

    for name in names:
        shapley[name] /= 6.0

    # Shapley attribution already satisfies the efficiency property:
    # the driver contributions sum to Actual Revenue - Plan Revenue.
    # Do not rescale the individual contributions by the signed revenue gap.
    # Rescaling by a negative total gap would incorrectly flip a positive
    # above-plan driver (e.g. MAU) into a negative revenue impact.

    result = []
    for name in names:
        metric = name.split(" / ")[-1]
        actual_value = actual[name]
        plan_value = plan[name]
        gap_pct = (
            (actual_value / plan_value - 1.0) * 100
            if plan_value
            else 0.0
        )
        impact = shapley[name]

        result.append(
            {
                "driver": name,
                "metric": metric,
                "actual": actual_value,
                "plan": plan_value,
                "gap_pct": gap_pct,
                "revenue_impact": impact,
                "direction": (
                    "negative"
                    if impact < -1e-9
                    else "positive"
                    if impact > 1e-9
                    else "neutral"
                ),
            }
        )

    # Negative revenue impacts are the business constraints. Rank those first.
    # If all impacts are non-negative, rank by absolute impact.
    result.sort(
        key=lambda item: (
            0 if item["revenue_impact"] < 0 else 1,
            -abs(item["revenue_impact"]),
        )
    )
    return result


def diagnose_root_causes(
    kpi_analysis: Dict[str, pd.DataFrame],
    funnel_analysis: Dict[str, pd.DataFrame],
    segments: pd.DataFrame,
    cohorts: pd.DataFrame,
) -> Dict:
    """Derive diagnosis from calculated evidence. No business conclusion is hard-coded."""

    weekly = kpi_analysis["weekly"]
    latest = weekly.iloc[-1]
    prior = weekly.iloc[-2] if len(weekly) > 1 else latest
    funnel_latest = funnel_analysis["weekly"].iloc[-1]

    evidence = []
    drivers = []

    mau_gap_pct = _safe(latest["mau_plan_variance_pct"])
    opu_gap_pct = _safe(latest["opu_plan_variance_pct"])
    arpu_gap_pct = _safe(latest["arpu_plan_variance_pct"])
    revenue_gap_pct = _safe(latest["revenue_plan_variance_pct"])
    cm_gap_pp = _safe(latest["cm_gap_pp"])
    cac_wow = _safe(latest["cac_wow_pct"])
    opu_wow = _safe(latest["opu_wow_pct"])
    arpu_wow = _safe(latest["arpu_wow_pct"])

    # Revenue-driver attribution is the source of truth for the primary
    # business driver. Do not use an arbitrary +/-5% MAU threshold.
    driver_attribution = _driver_attribution(latest)

    negative_drivers = [
        item
        for item in driver_attribution
        if item["revenue_impact"] < -1e-9
    ]

    if negative_drivers:
        for item in negative_drivers:
            drivers.append(item["driver"])
            evidence.append(
                {
                    "metric": f'{item["metric"]} revenue attribution',
                    "value": item["revenue_impact"],
                    "unit": "AED",
                    "signal": "negative contribution to revenue gap",
                }
            )
    else:
        # If revenue is below plan but no single multiplicative driver is
        # negative, keep the diagnosis honest instead of inventing a driver.
        drivers.append("No negative MAU / OPU / AOV driver identified")
        evidence.append(
            {
                "metric": "Revenue driver attribution",
                "value": _safe(latest.get("revenue")) - _safe(latest.get("revenue_plan")),
                "unit": "AED",
                "signal": "no negative multiplicative driver",
            }
        )

    # Preserve the existing supporting evidence rules.
    if mau_gap_pct < -0.5:
        evidence.append(
            {
                "metric": "MAU plan variance",
                "value": mau_gap_pct,
                "unit": "%",
                "signal": "below plan",
            }
        )
    elif mau_gap_pct > 0.5:
        evidence.append(
            {
                "metric": "MAU plan variance",
                "value": mau_gap_pct,
                "unit": "%",
                "signal": "above plan",
            }
        )

    if opu_gap_pct < -0.5:
        evidence.append(
            {
                "metric": "OPU plan variance",
                "value": opu_gap_pct,
                "unit": "%",
                "signal": "below plan",
            }
        )
    elif opu_gap_pct > 0.5:
        evidence.append(
            {
                "metric": "OPU plan variance",
                "value": opu_gap_pct,
                "unit": "%",
                "signal": "above plan",
            }
        )

    if arpu_gap_pct < -0.5:
        evidence.append(
            {
                "metric": "ARPU plan variance",
                "value": arpu_gap_pct,
                "unit": "%",
                "signal": "below plan",
            }
        )
    elif arpu_gap_pct > 0.5:
        evidence.append(
            {
                "metric": "ARPU plan variance",
                "value": arpu_gap_pct,
                "unit": "%",
                "signal": "above plan",
            }
        )

    if cm_gap_pp < -2:
        evidence.append(
            {
                "metric": "Contribution margin gap",
                "value": cm_gap_pp,
                "unit": "pp",
                "signal": "below plan",
            }
        )

    if cac_wow > 5:
        evidence.append(
            {
                "metric": "CAC WoW change",
                "value": cac_wow,
                "unit": "%",
                "signal": "increasing",
            }
        )

    if opu_wow < -1:
        evidence.append(
            {
                "metric": "OPU WoW change",
                "value": opu_wow,
                "unit": "%",
                "signal": "declining",
            }
        )

    if arpu_wow < -1:
        evidence.append(
            {
                "metric": "ARPU WoW change",
                "value": arpu_wow,
                "unit": "%",
                "signal": "declining",
            }
        )

    # Funnel evidence is used only when it shows deterioration between the latest two periods.
    if len(funnel_analysis["stages"]) > 0:
        weak_stage = funnel_analysis["stages"].sort_values("change_pp").iloc[0]
        if _safe(weak_stage.get("change_pp")) < -0.5:
            evidence.append(
                {
                    "metric": weak_stage["stage"],
                    "value": _safe(weak_stage["change_pp"]),
                    "unit": "pp WoW",
                    "signal": "largest funnel deterioration",
                }
            )

    # Segment evidence: derive segment KPIs from raw counts before comparison.
    seg = _derive_segment_metrics(segments)
    if not seg.empty:
        first_week = seg["week"].min()
        last_week = seg["week"].max()
        first = seg[seg["week"] == first_week].set_index("segment")
        last = seg[seg["week"] == last_week].set_index("segment")
        common = first.index.intersection(last.index)
        if len(common):
            changes = []
            for segment in common:
                changes.append(
                    {
                        "segment": segment,
                        "opu_change": _safe(last.loc[segment, "orders_per_user"])
                        - _safe(first.loc[segment, "orders_per_user"]),
                        "retention_change": _safe(last.loc[segment, "retention"])
                        - _safe(first.loc[segment, "retention"]),
                        "cm_change_pp": (
                            _safe(last.loc[segment, "contribution_margin"])
                            - _safe(first.loc[segment, "contribution_margin"])
                        )
                        * 100,
                    }
                )
            segment_changes = pd.DataFrame(changes).sort_values("opu_change")
        else:
            segment_changes = pd.DataFrame()
    else:
        segment_changes = pd.DataFrame()

    return {
        "drivers": drivers,
        "driver_attribution": driver_attribution,
        "evidence": evidence,
        "latest": {
            "week": latest["week"],
            "revenue_gap_pct": revenue_gap_pct,
            "mau_gap_pct": mau_gap_pct,
            "opu_gap_pct": opu_gap_pct,
            "arpu_gap_pct": arpu_gap_pct,
            "cm_gap_pp": cm_gap_pp,
        },
        "segment_changes": segment_changes,
        "retention_summary": _retention_summary(_derive_cohort_metrics(cohorts)),
    }

def _retention_summary(cohorts: pd.DataFrame) -> Dict:
    """Return average retention for every available cohort week."""
    if cohorts.empty:
        return {}

    retention_columns = _cohort_week_columns(cohorts, "retention")
    return {
        column: float(cohorts[column].mean())
        for column in retention_columns
        if column in cohorts.columns
    }


def calculate_opportunities(
    kpi_analysis: Dict[str, pd.DataFrame],
    segments: pd.DataFrame,
    cohorts: pd.DataFrame,
) -> pd.DataFrame:
    latest = kpi_analysis["weekly"].iloc[-1]
    mau = _safe(latest["mau"])
    opu = _safe(latest["opu"])
    arpu = _safe(latest["arpu"])
    aov = _safe(latest["aov"])
    cm = _safe(latest["contribution_margin"]) / 100

    rows: List[Dict] = []
    target_opu = _safe(latest["opu_plan"])
    target_arpu = _safe(latest["arpu_plan"])
    incremental_orders = max(0.0, mau * (target_opu - opu))
    incremental_revenue = incremental_orders * aov
    rows.append({
        "opportunity": "Close OPU gap to plan",
        "driver": "Frequency",
        "target_metric": "OPU",
        "current_value": opu,
        "target_value": target_opu,
        "incremental_orders": incremental_orders,
        "incremental_revenue": incremental_revenue,
        "incremental_contribution": incremental_revenue * cm,
        "assumption": "Incremental orders use current MAU and current AOV; no additional MAU growth assumed.",
    })

    incremental_revenue_arpu = max(0.0, mau * (target_arpu - arpu))
    rows.append({
        "opportunity": "Close ARPU gap to plan",
        "driver": "Monetisation",
        "target_metric": "ARPU",
        "current_value": arpu,
        "target_value": target_arpu,
        "incremental_orders": 0.0,
        "incremental_revenue": incremental_revenue_arpu,
        "incremental_contribution": incremental_revenue_arpu * cm,
        "assumption": "ARPU improvement is applied across current MAU; no incremental MAU assumed.",
    })

    derived_cohorts = _derive_cohort_metrics(cohorts)
    retention_cols = _cohort_week_columns(derived_cohorts, "retention")

    if not derived_cohorts.empty and retention_cols:
        latest_retention_col = retention_cols[-1]
        latest_match = COHORT_RETENTION_PATTERN.match(latest_retention_col)
        latest_week_number = int(latest_match.group(1))
        latest_retention = _safe(derived_cohorts[latest_retention_col].mean())
        target_retention = latest_retention + 0.05
        eligible = float(pd.to_numeric(derived_cohorts["users"], errors="coerce").sum())
        retained = eligible * 0.05
        retained_orders = retained * opu
        retained_revenue = retained_orders * aov

        rows.append({
            "opportunity": f"Improve Week {latest_week_number} retention by 5pp",
            "driver": "Retention",
            "target_metric": latest_retention_col,
            "current_value": latest_retention,
            "target_value": target_retention,
            "incremental_orders": retained_orders,
            "incremental_revenue": retained_revenue,
            "incremental_contribution": retained_revenue * cm,
            "assumption": (
                f"Illustrative 5pp Week {latest_week_number} retention improvement across "
                "the supplied cohort population; retained users transact at current OPU and AOV."
            ),
        })

    return pd.DataFrame(rows)


def _initiative_driver_family(target_problem: str) -> str:
    """Map planning language to the deterministic growth-driver framework."""
    mapping = {
        "Retention": "Retention",
        "Frequency": "Frequency",
        "AOV": "Monetisation",
        "Monetisation": "Monetisation",
        # Conversion improves completed transactions and therefore supports
        # the frequency / OPU driver in the current revenue decomposition.
        "Conversion": "Frequency",
        "Acquisition": "Acquisition",
    }
    return mapping.get(str(target_problem), str(target_problem))


def _driver_evidence_strength(
    diagnosis: Dict,
    funnel_analysis: Dict[str, pd.DataFrame],
) -> Dict[str, float]:
    """Convert available diagnostic signals into comparable 0-1 evidence strengths."""
    latest = diagnosis.get("latest", {})
    strength = {
        "Acquisition": min(1.0, max(0.0, -_safe(latest.get("mau_gap_pct")) / 5.0)),
        "Frequency": min(1.0, max(0.0, -_safe(latest.get("opu_gap_pct")) / 10.0)),
        "Monetisation": min(1.0, max(0.0, -_safe(latest.get("arpu_gap_pct")) / 20.0)),
        "Retention": 0.0,
        "Conversion": 0.0,
    }

    segment_changes = diagnosis.get("segment_changes")
    if isinstance(segment_changes, pd.DataFrame) and not segment_changes.empty:
        worst_retention = _safe(segment_changes["retention_change"].min())
        strength["Retention"] = min(1.0, max(0.0, -worst_retention / 0.10))

    stages = funnel_analysis.get("stages")
    if isinstance(stages, pd.DataFrame) and not stages.empty and "change_pp" in stages.columns:
        worst_funnel_change = _safe(pd.to_numeric(stages["change_pp"], errors="coerce").min())
        strength["Conversion"] = min(1.0, max(0.0, -worst_funnel_change / 2.0))

    return strength


def _segment_alignment_score(
    target_segment: str,
    segment_changes: pd.DataFrame | None,
) -> float:
    """Score whether the initiative's target population matches observed deterioration."""
    target = str(target_segment)
    if target.lower() == "all":
        return 0.5

    if not isinstance(segment_changes, pd.DataFrame) or segment_changes.empty:
        return 0.0

    if target not in set(segment_changes["segment"].astype(str)):
        return 0.0

    row = segment_changes[segment_changes["segment"].astype(str) == target].iloc[0]
    opu_pressure = min(1.0, max(0.0, -_safe(row.get("opu_change")) / 0.30))
    retention_pressure = min(1.0, max(0.0, -_safe(row.get("retention_change")) / 0.10))
    return (opu_pressure + retention_pressure) / 2.0


def prioritise_initiatives(
    initiatives: pd.DataFrame,
    opportunities: pd.DataFrame,
    diagnosis: Dict | None = None,
    funnel_analysis: Dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Rank initiatives using economics plus evidence alignment.

    The previous ranking considered expected revenue, confidence, speed,
    economics and effort but did not connect the result to the diagnosis.
    This phase keeps that commercial score and adds a bounded evidence
    multiplier so a high-impact initiative that does not address the observed
    constraint cannot outrank a similarly credible, evidence-aligned action.
    """
    df = initiatives.copy()

    if df.empty:
        return df

    # Normalise 1-5 effort, confidence and speed. Higher confidence/speed is
    # better; lower effort is better.
    df["impact_score"] = (
        df["expected_revenue"].clip(lower=0)
        / max(df["expected_revenue"].max(), 1)
        * 5
    ).clip(0, 5)
    df["confidence_score"] = df["confidence"].clip(1, 5) / 5
    df["speed_score"] = (6 - df["time_to_impact"].clip(1, 5)) / 5
    df["economics_score"] = ((5 + df["cm_impact"]) / 6).clip(0, 1)
    df["effort_score"] = df["implementation_effort"].clip(1, 5)
    df["priority_score"] = (
        df["impact_score"]
        * df["confidence_score"]
        * df["speed_score"]
        * df["economics_score"]
        / df["effort_score"]
    )

    diagnosis = diagnosis or {}
    funnel_analysis = funnel_analysis or {}
    driver_strength = _driver_evidence_strength(diagnosis, funnel_analysis)
    segment_changes = diagnosis.get("segment_changes")

    opportunity_drivers = set()
    if isinstance(opportunities, pd.DataFrame) and not opportunities.empty and "driver" in opportunities.columns:
        opportunity_drivers = set(str(value) for value in opportunities["driver"].dropna())

    evidence_scores = []
    for _, row in df.iterrows():
        family = _initiative_driver_family(row.get("target_problem", ""))
        driver_score = driver_strength.get(family, 0.0)

        # An initiative is better grounded when the deterministic opportunity
        # package contains the same driver family.
        opportunity_score = 1.0 if family in opportunity_drivers else 0.0
        driver_alignment = (driver_score + opportunity_score) / 2.0

        segment_alignment = _segment_alignment_score(
            row.get("target_segment", ""),
            segment_changes,
        )

        # Driver evidence carries more weight than population specificity.
        evidence_alignment = 0.70 * driver_alignment + 0.30 * segment_alignment

        evidence_scores.append(
            {
                "driver_family": family,
                "driver_evidence_score": driver_score,
                "opportunity_alignment_score": opportunity_score,
                "segment_alignment_score": segment_alignment,
                "evidence_alignment_score": evidence_alignment,
            }
        )

    evidence_df = pd.DataFrame(evidence_scores, index=df.index)
    for column in evidence_df.columns:
        df[column] = evidence_df[column]

    # Evidence is intentionally the dominant component of the decision score.
    # Commercial priority remains important, but a high-revenue/low-effort
    # initiative should not outrank an evidence-backed action simply because
    # its planning assumptions are attractive.
    max_priority = max(float(df["priority_score"].max()), 1e-9)
    df["commercial_priority_score"] = (
        df["priority_score"] / max_priority
    ).clip(0, 1)
    df["decision_score"] = (
        0.30 * df["commercial_priority_score"]
        + 0.70 * df["evidence_alignment_score"]
    )

    return df.sort_values(
        ["decision_score", "priority_score"],
        ascending=[False, False],
    ).reset_index(drop=True)


def build_recommendation(
    ranked_initiatives: pd.DataFrame,
    diagnosis: Dict,
) -> Dict:
    """Return the single deterministic recommendation and its evidence trail."""
    if ranked_initiatives.empty:
        return {
            "status": "insufficient evidence",
            "reason": "No initiatives are available for prioritisation.",
        }

    top = ranked_initiatives.iloc[0]
    drivers = diagnosis.get("driver_attribution", [])
    negative_drivers = [
        item for item in drivers if _safe(item.get("revenue_impact")) < 0
    ]

    evidence = []
    if negative_drivers:
        for item in negative_drivers[:3]:
            evidence.append(
                {
                    "type": "driver attribution",
                    "driver": item.get("driver"),
                    "revenue_impact": item.get("revenue_impact"),
                    "gap_pct": item.get("gap_pct"),
                }
            )

    return {
        "status": "ready",
        "initiative": str(top.get("initiative", "")),
        "target_segment": str(top.get("target_segment", "")),
        "target_problem": str(top.get("target_problem", "")),
        "driver_family": str(top.get("driver_family", "")),
        "priority_score": _safe(top.get("priority_score")),
        "decision_score": _safe(top.get("decision_score")),
        "expected_revenue": _safe(top.get("expected_revenue")),
        "evidence_alignment_score": _safe(top.get("evidence_alignment_score")),
        "driver_evidence_score": _safe(top.get("driver_evidence_score")),
        "segment_alignment_score": _safe(top.get("segment_alignment_score")),
        "evidence": evidence,
    }


def build_decision_package(kpi_analysis, funnel_analysis, segments, cohorts, initiatives) -> Dict:
    diagnosis = diagnose_root_causes(kpi_analysis, funnel_analysis, segments, cohorts)
    opportunities = calculate_opportunities(kpi_analysis, segments, cohorts)
    ranked = prioritise_initiatives(
        initiatives,
        opportunities,
        diagnosis=diagnosis,
        funnel_analysis=funnel_analysis,
    )
    recommendation = build_recommendation(ranked, diagnosis)
    return {
        "diagnosis": diagnosis,
        "opportunities": opportunities,
        "initiatives": ranked,
        "recommendation": recommendation,
    }
