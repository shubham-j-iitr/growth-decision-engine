from __future__ import annotations

from typing import Dict

import pandas as pd


def build_funnel_analysis(
    funnel: pd.DataFrame,
    kpi: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    """
    Calculate funnel rates using raw funnel stages plus MAU from weekly KPIs.

    Orders are intentionally not used as a funnel conversion denominator
    because orders represent transactions, not unique converting users.
    """

    df = funnel.merge(
        kpi[["week", "mau", "orders"]],
        on="week",
        how="left",
        validate="one_to_one",
    )

    df["food_engagement_rate"] = (
        df["food_visitors"]
        / df["mau"].replace(0, pd.NA)
        * 100
    )

    df["restaurant_view_rate"] = (
        df["restaurant_viewers"]
        / df["food_visitors"].replace(0, pd.NA)
        * 100
    )

    df["menu_view_rate"] = (
        df["menu_viewers"]
        / df["restaurant_viewers"].replace(0, pd.NA)
        * 100
    )

    df["cart_rate"] = (
        df["cart_users"]
        / df["menu_viewers"].replace(0, pd.NA)
        * 100
    )

    df["checkout_rate"] = (
        df["checkout_users"]
        / df["cart_users"].replace(0, pd.NA)
        * 100
    )

    stages = [
        ("Food engagement", "food_engagement_rate"),
        ("Restaurant view", "restaurant_view_rate"),
        ("Menu view", "menu_view_rate"),
        ("Cart", "cart_rate"),
        ("Checkout", "checkout_rate"),
    ]

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else None

    rows = []

    for name, metric in stages:
        row = {
            "stage": name,
            "metric": metric,
            "current_rate": float(latest[metric]),
        }

        if previous is not None:
            row["previous_rate"] = float(previous[metric])
            row["change_pp"] = float(
                latest[metric] - previous[metric]
            )
        else:
            row["previous_rate"] = None
            row["change_pp"] = None

        rows.append(row)

    return {
        "weekly": df,
        "stages": pd.DataFrame(rows),
    }