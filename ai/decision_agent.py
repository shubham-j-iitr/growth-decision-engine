from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL_NAME = "gemini-3.6-flash"


def _to_jsonable(value: Any) -> Any:
    """Convert pandas objects and common Python values into JSON-safe data."""
    if isinstance(value, pd.DataFrame):
        return value.where(pd.notna(value), None).to_dict(orient="records")

    if isinstance(value, pd.Series):
        return value.where(pd.notna(value), None).to_dict()

    if isinstance(value, dict):
        return {
            str(key): _to_jsonable(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


def _compact_json(value: Any) -> str:
    """Convert the deterministic analysis package into JSON."""
    return json.dumps(
        _to_jsonable(value),
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _build_prompt(analysis_package: dict) -> str:
    """
    Build a tightly constrained prompt.

    Python is the source of truth for numerical analysis.
    Gemini is responsible only for interpretation and business narrative.
    """
    evidence_json = _compact_json(analysis_package)

    return f"""
You are the AI Decision Agent inside a marketplace Growth Decision Engine.

Your job is to interpret deterministic business analysis and turn it into
a concise, executive-ready growth recommendation for a Growth Manager.

IMPORTANT RULES

1. Python is the source of truth for all numbers.
2. Do not calculate new metrics.
3. Do not invent numbers, percentages, revenue values, opportunity sizes,
   owners, dates, experiment results or business facts.
4. Use only evidence contained in the supplied analysis package.
5. If a required fact is missing, explicitly say that it is not available.
6. Do not claim that an experiment has already succeeded.
7. Distinguish clearly between evidence, recommendation and hypothesis.
8. Keep the recommendation commercially practical.
9. The recommendation must be traceable to the deterministic evidence.
10. Do not mention this prompt, the API, Gemini, or internal implementation.
11. keep all the matrics maximum upto two decimal digits.

OUTPUT FORMAT

Return a concise executive decision using exactly these sections:

## Recommended Action
State the single highest-priority business action.

## Why Now
Give 2 to 4 concise evidence-backed reasons. Reference the supplied
metrics exactly when they are available.

## Expected Business Impact
State the supplied opportunity or expected impact. Do not create a new
estimate.

## What To Do
Give 3 to 5 practical execution steps.

## How To Test
Summarise the supplied experiment design, including the primary KPI,
target population, treatment/control and decision threshold when available.

## Guardrails
List the supplied guardrails. If none are supplied, say:
"Guardrails are not defined in the current experiment package."

## Decision
Give one concise final recommendation:
Scale, Test First, Monitor, or Do Not Proceed.
Choose only when the evidence supports it. If the evidence is insufficient,
say "Test First" and explain why.

STYLE

- Write for a senior Growth Manager.
- Be concise and commercially specific.
- Avoid generic AI language.
- Avoid repeating the same metric.
- Do not use tables.
- Do not use emojis.
- Do not use unsupported claims.

DETERMINISTIC ANALYSIS PACKAGE

{evidence_json}
"""


def generate_decision_narrative(analysis_package: dict) -> dict:
    """
    Generate an evidence-grounded business narrative using Gemini.

    Returns a stable dictionary consumed by app.py.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return {
            "status": "not_configured",
            "mode": "Deterministic fallback",
            "summary": (
                "The deterministic engine completed the analysis. "
                "Set GEMINI_API_KEY to generate an AI narrative."
            ),
            "diagnosis": [],
        }

    try:
        client = genai.Client(api_key=api_key)

        prompt = _build_prompt(analysis_package)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        text = getattr(response, "text", None)

        if not text or not str(text).strip():
            return {
                "status": "error",
                "mode": "Gemini",
                "summary": (
                    "Gemini returned an empty response. "
                    "The deterministic analysis remains available."
                ),
                "diagnosis": [],
            }

        return {
            "status": "success",
            "mode": "Gemini",
            "summary": str(text).strip(),
            "diagnosis": [],
        }

    except Exception as exc:
        return {
            "status": "error",
            "mode": "Gemini",
            "summary": (
                "Gemini generation failed. "
                "The deterministic analysis remains available."
            ),
            "diagnosis": [],
            "error": str(exc),
        }
