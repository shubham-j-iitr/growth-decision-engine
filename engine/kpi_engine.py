from __future__ import annotations

from typing import Dict
import pandas as pd


def _pct_change(current: pd.Series, previous: pd.Series) -> pd.Series:
    return ((current - previous) / previous.replace(0, pd.NA) * 100).fillna(0)


def _derive_metrics(df: pd.DataFrame, plan: bool = False) -> pd.DataFrame:
    out = df.copy()
    if plan:
        out["opu_plan"] = out["orders_plan"] / out["mau_plan"].replace(0, pd.NA)
        out["arpu_plan"] = out["revenue_plan"] / out["mau_plan"].replace(0, pd.NA)
        out["aov_plan"] = out["revenue_plan"] / out["orders_plan"].replace(0, pd.NA)
    else:
        out["opu"] = out["orders"] / out["mau"].replace(0, pd.NA)
        out["arpu"] = out["revenue"] / out["mau"].replace(0, pd.NA)
        out["aov"] = out["revenue"] / out["orders"].replace(0, pd.NA)
        out["cac"] = out["acquisition_spend"] / out["new_users"].replace(0, pd.NA)
        out["contribution_margin"] = out["contribution_profit"] / out["revenue"].replace(0, pd.NA) * 100
    return out


def build_kpi_analysis(kpi: pd.DataFrame, plan: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Derive marketplace KPIs from raw facts and calculate plan/WoW performance."""
    actual = _derive_metrics(kpi, plan=False)
    target = _derive_metrics(plan, plan=True)
    merged = actual.merge(target, on="week", how="left", validate="one_to_one")

    merged["mau_gap"] = merged["mau"] - merged["mau_plan"]
    merged["orders_gap"] = merged["orders"] - merged["orders_plan"]
    merged["opu_gap"] = merged["opu"] - merged["opu_plan"]
    merged["arpu_gap"] = merged["arpu"] - merged["arpu_plan"]
    merged["revenue_gap"] = merged["revenue"] - merged["revenue_plan"]
    merged["aov_gap"] = merged["aov"] - merged["aov_plan"]
    merged["cm_gap_pp"] = merged["contribution_margin"] - merged["cm_plan"]

    for metric in ["mau", "orders", "revenue", "opu", "arpu", "aov"]:
        merged[f"{metric}_plan_variance_pct"] = _pct_change(
            merged[metric], merged[f"{metric}_plan"]
        )

    merged["mau_wow_pct"] = _pct_change(merged["mau"], merged["mau"].shift(1))
    merged["orders_wow_pct"] = _pct_change(merged["orders"], merged["orders"].shift(1))
    merged["opu_wow_pct"] = _pct_change(merged["opu"], merged["opu"].shift(1))
    merged["arpu_wow_pct"] = _pct_change(merged["arpu"], merged["arpu"].shift(1))
    merged["revenue_wow_pct"] = _pct_change(merged["revenue"], merged["revenue"].shift(1))
    merged["cac_wow_pct"] = _pct_change(merged["cac"], merged["cac"].shift(1))
    merged["cm_wow_pp"] = merged["contribution_margin"] - merged["contribution_margin"].shift(1)

    latest = merged.iloc[-1].to_dict()
    latest["revenue_gap_pct"] = latest["revenue_plan_variance_pct"]
    latest["mau_gap_pct"] = latest["mau_plan_variance_pct"]
    latest["opu_gap_pct"] = latest["opu_plan_variance_pct"]
    latest["arpu_gap_pct"] = latest["arpu_plan_variance_pct"]

    return {"weekly": merged, "latest": pd.DataFrame([latest])}
