from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def kpi_trend(df: pd.DataFrame, metric: str, title: str, plan_metric: str | None = None):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["week"], y=df[metric], mode="lines+markers", name="Actual"))
    if plan_metric and plan_metric in df.columns:
        fig.add_trace(go.Scatter(x=df["week"], y=df[plan_metric], mode="lines", name="Plan", line={"dash": "dash"}))
    fig.update_layout(title=title, xaxis_title="Week", yaxis_title=metric.upper(), hovermode="x unified")
    return fig


def revenue_driver_chart(df: pd.DataFrame):
    latest = df.iloc[-1]
    values = [latest["mau"], latest["opu"], latest["arpu"]]
    labels = ["MAU", "OPU", "ARPU"]
    fig = go.Figure(go.Bar(x=labels, y=values, text=[f"{v:,.2f}" for v in values], textposition="auto"))
    fig.update_layout(title="Revenue Driver Snapshot", yaxis_title="Current value")
    return fig


def segment_share_chart(segments: pd.DataFrame, metric: str = "revenue"):
    latest_week = segments["week"].max()
    df = segments[segments["week"] == latest_week].copy()
    fig = px.bar(df, x="segment", y=metric, title=f"{metric.title()} by Segment | {latest_week}", text_auto=".2s")
    return fig


def initiative_priority_chart(initiatives: pd.DataFrame):
    df = initiatives.head(8).copy()
    fig = px.bar(df, x="priority_score", y="initiative", orientation="h", title="Initiative Priority")
    fig.update_yaxes(categoryorder="total ascending")
    return fig
