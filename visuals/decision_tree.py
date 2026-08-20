from __future__ import annotations

import textwrap

import plotly.graph_objects as go


def _wrap_label(value: str, width: int = 28) -> str:
    """Wrap long node labels so they remain readable in the chart."""
    return "<br>".join(textwrap.wrap(str(value), width=width))


def root_cause_tree(diagnosis: dict):
    """Render a dynamic revenue-driver tree.

    The tree is compatible with the existing dashboard contract:
    it accepts the diagnosis dictionary and returns a Plotly Figure.

    Layout:
        Revenue gap
        /    |    \\
      MAU   OPU   AOV

    Negative revenue-attribution drivers are shown first and highlighted
    through their labels. No fixed W12/W99/W219 assumptions are used.
    """

    attribution = diagnosis.get("driver_attribution", [])

    if attribution:
        driver_items = attribution
    else:
        # Backward-compatible fallback for older diagnosis packages.
        driver_items = [
            {
                "driver": driver,
                "gap_pct": None,
                "revenue_impact": None,
                "direction": "neutral",
            }
            for driver in diagnosis.get("drivers", [])
        ]

    if not driver_items:
        driver_items = [
            {
                "driver": "Evidence insufficient",
                "gap_pct": None,
                "revenue_impact": None,
                "direction": "neutral",
            }
        ]

    root_label = f"Revenue gap<br>{diagnosis.get('latest', {}).get('revenue_gap_pct', 0.0):+.1f}%"

    # Root at the left; drivers branch vertically from the centre.
    root_x = 0.12
    driver_x = 0.72

    if len(driver_items) == 1:
        y_positions = [0.50]
    else:
        top = 0.80
        bottom = 0.20
        step = (top - bottom) / (len(driver_items) - 1)
        y_positions = [top - i * step for i in range(len(driver_items))]

    labels = [root_label]
    x = [root_x]
    y = [0.50]

    for item in driver_items:
        driver = str(item.get("driver", "Unknown driver"))
        gap_pct = item.get("gap_pct")
        impact = item.get("revenue_impact")

        lines = [_wrap_label(driver, 24)]

        if gap_pct is not None:
            lines.append(f"{float(gap_pct):+.1f}% vs plan")

        if impact is not None:
            impact_value = float(impact)
            lines.append(f"{impact_value:+,.2f} revenue impact")

        labels.append("<br>".join(lines))
        x.append(driver_x)
        y.append(y_positions[len(labels) - 2])

    fig = go.Figure()

    # Root node.
    fig.add_trace(
        go.Scatter(
            x=[x[0]],
            y=[y[0]],
            mode="markers+text",
            text=[labels[0]],
            textposition="middle left",
            marker={"size": 30},
            hoverinfo="text",
        )
    )

    # Driver nodes.
    fig.add_trace(
        go.Scatter(
            x=x[1:],
            y=y[1:],
            mode="markers+text",
            text=labels[1:],
            textposition="middle right",
            marker={"size": 28},
            hoverinfo="text",
        )
    )

    # Branches from the revenue gap to every driver.
    for driver_y in y[1:]:
        fig.add_annotation(
            x=driver_x - 0.055,
            y=driver_y,
            ax=root_x + 0.055,
            ay=0.50,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=2,
        )

    fig.update_layout(
        title="Root Cause Evidence Chain",
        xaxis={
            "visible": False,
            "range": [0.0, 1.0],
        },
        yaxis={
            "visible": False,
            "range": [0.0, 1.0],
        },
        height=max(340, 170 + 120 * len(driver_items)),
        margin={"l": 40, "r": 220, "t": 55, "b": 30},
        showlegend=False,
    )

    return fig
