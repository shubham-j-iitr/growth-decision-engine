from __future__ import annotations

from typing import Dict

import pandas as pd


def build_funnel_analysis(
    funnel: pd.DataFrame,
    kpi: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    """Calculate generic marketplace funnel rates from user populations.

    The funnel is deliberately platform-neutral and can represent food delivery,
    quick commerce, ecommerce or another transaction marketplace. Orders are
    retained as a transaction KPI but are not used as a user-conversion
    denominator because one user can place multiple orders.
    """

    df = funnel.merge(
        kpi[["week", "mau", "orders"]],
        on="week",
        how="left",
        validate="one_to_one",
    )

    df["engagement_rate"] = (
        df["visitors"]
        / df["mau"].replace(0, pd.NA)
        * 100
    )

    df["browse_rate"] = (
        df["browse_users"]
        / df["visitors"].replace(0, pd.NA)
        * 100
    )

    df["product_view_rate"] = (
        df["product_viewers"]
        / df["browse_users"].replace(0, pd.NA)
        * 100
    )

    df["cart_rate"] = (
        df["cart_users"]
        / df["product_viewers"].replace(0, pd.NA)
        * 100
    )

    df["checkout_rate"] = (
        df["checkout_users"]
        / df["cart_users"].replace(0, pd.NA)
        * 100
    )

    stages = [
        ("Marketplace engagement", "engagement_rate"),
        ("Browse", "browse_rate"),
        ("Product view", "product_view_rate"),
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
            row["change_pp"] = float(latest[metric] - previous[metric])
        else:
            row["previous_rate"] = None
            row["change_pp"] = None

        rows.append(row)

    return {
        "weekly": df,
        "stages": pd.DataFrame(rows),
    }
