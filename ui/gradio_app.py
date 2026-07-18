"""Gradio Space entry point — see README.md's Deployment section ([F3]).

Runs the FULL scoring pipeline (ENABLE_ML left at its default, unlike
[F2]'s Render deploy which sets ENABLE_ML=0) so ml_drawdown_probability and
the SHAP top_features breakdown are actually populated — the whole point of
this deploy vs. Render's cut-down one. Originally planned as an HF Docker
SDK Space reusing the FastAPI+React app directly (see the root Dockerfile,
still in the repo for whenever Docker SDK is free again or PRO is in use);
switched to Gradio after discovering HF now gates Docker SDK behind a PRO
subscription on the free tier — an unannounced platform change, not
something in this repo's control. A Gradio Space only runs a Python
app.py-style entry point, not an arbitrary Dockerfile, so this is a real
(if smaller-scope) UI, not a wrapper around the existing React frontend.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from stock_risk.scoring.scorer import RiskScorer

scorer = RiskScorer()

CATEGORY_ORDER = ["volatility", "tail", "drawdown", "sensitivity", "liquidity"]
LABEL_COLORS = {"LOW": "#3fb950", "MODERATE": "#d29922", "HIGH": "#f0883e", "EXTREME": "#f85149"}


def _breakdown_df(risk_breakdown: dict) -> pd.DataFrame:
    rows = []
    for cat in CATEGORY_ORDER:
        entry = risk_breakdown.get(cat) or {}
        rows.append({
            "category": cat,
            "score": entry.get("score"),
            "weight": entry.get("weight"),
        })
    return pd.DataFrame(rows)


def _stress_test_df(stress_test: dict | None) -> pd.DataFrame:
    if not stress_test:
        return pd.DataFrame(columns=["scenario", "baseline_score", "stressed_score", "delta"])
    rows = [
        {
            "scenario": s["label"],
            "baseline_score": s["baseline_score"],
            "stressed_score": s["stressed_score"],
            "delta": s["delta"],
        }
        for s in stress_test.get("scenarios", {}).values()
    ]
    return pd.DataFrame(rows)


def _shap_df(explanation: dict | None) -> pd.DataFrame:
    if not explanation:
        return pd.DataFrame(columns=["feature", "raw_value", "shap_contribution"])
    return pd.DataFrame(explanation.get("top_features", []))


def _gauge(score: float, label: str) -> go.Figure:
    color = LABEL_COLORS.get(label, "#8b949e")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"font": {"size": 44}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 25], "color": "#1a3a1a"},
                {"range": [25, 50], "color": "#3a3319"},
                {"range": [50, 75], "color": "#3a2a19"},
                {"range": [75, 100], "color": "#3a1a1a"},
            ],
        },
    ))
    fig.update_layout(
        height=260, margin=dict(l=20, r=20, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)"
    )
    return fig


def score_ticker(ticker: str, period: str):
    ticker = (ticker or "").upper().strip()
    if not ticker:
        raise gr.Error("Enter a ticker symbol, e.g. TSLA")

    try:
        result = scorer.score(ticker, period=period)
    except ValueError as exc:
        raise gr.Error(str(exc))
    except Exception as exc:
        raise gr.Error(f"Scoring failed: {exc}")

    label = result["risk_label"]
    summary = f"## {ticker} — {result['risk_score']} / 100 ({label})\n\n{result['risk_note']}"

    ml_prob = result.get("ml_drawdown_probability")
    explanation = result.get("ml_drawdown_explanation")
    if ml_prob is not None and explanation is not None:
        ml_summary = (
            f"**Estimated 20-day drawdown probability: {ml_prob}%**\n\n"
            f"(calibrated: {explanation.get('calibrated_probability', 'n/a')})"
        )
    else:
        ml_summary = "_No ML model artefact loaded — ml_drawdown_probability is null._"

    return (
        _gauge(result["risk_score"], label),
        summary,
        _breakdown_df(result["risk_breakdown"]),
        _stress_test_df(result.get("stress_test")),
        ml_summary,
        _shap_df(explanation),
    )


with gr.Blocks(title="Explainable Stock Risk Scoring") as demo:
    gr.Markdown(
        "# 📉 Explainable Stock Risk Scoring — full ML + SHAP\n"
        "Percentile-based composite risk score, historical stress tests, and "
        "SHAP-explained XGBoost downside-risk probability, all from live yfinance data. "
        "See the [GitHub repo](https://github.com/LauraC-4882/explainable-stock-risk-scoring) "
        "for the FastAPI+React version (Render deploy, ML leg disabled for memory)."
    )
    with gr.Row():
        ticker_in = gr.Textbox(label="Ticker", value="TSLA", scale=2)
        period_in = gr.Dropdown(
            label="History window", choices=["6mo", "1y", "2y", "5y"], value="2y", scale=1
        )
        score_btn = gr.Button("Score", variant="primary", scale=1)

    with gr.Row():
        with gr.Column(scale=1):
            gauge_out = gr.Plot(label="Risk Score")
        with gr.Column(scale=2):
            summary_out = gr.Markdown()
            breakdown_out = gr.Dataframe(
                headers=["category", "score", "weight"], label="Category Breakdown"
            )

    gr.Markdown("## Historical Stress Test")
    stress_out = gr.Dataframe(
        headers=["scenario", "baseline_score", "stressed_score", "delta"],
        label="If a historical crisis recurred",
    )

    gr.Markdown("## ML Downside-Risk Signal (SHAP-explained)")
    ml_summary_out = gr.Markdown()
    shap_out = gr.Dataframe(
        headers=["feature", "raw_value", "shap_contribution"], label="Top Contributing Factors"
    )

    score_btn.click(
        score_ticker,
        inputs=[ticker_in, period_in],
        outputs=[gauge_out, summary_out, breakdown_out, stress_out, ml_summary_out, shap_out],
    )
    demo.load(
        score_ticker,
        inputs=[ticker_in, period_in],
        outputs=[gauge_out, summary_out, breakdown_out, stress_out, ml_summary_out, shap_out],
    )

if __name__ == "__main__":
    demo.launch()
