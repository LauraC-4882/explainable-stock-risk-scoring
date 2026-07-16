"""Historical-scenario stress testing for the percentile-based composite score.

Scope: only risk_categories.py's five percentile categories (volatility,
tail, drawdown, sensitivity, liquidity) are stress-tested here — NOT the
XGBoost ml_drawdown_probability. Momentum/technical-indicator features (RSI,
Bollinger %B, distance-from-moving-average, volume ratio) that feed XGBoost
don't have a defensible "shock" interpretation the way volatility/VaR/
drawdown do — there's no established mapping from "VIX spikes to 80" to
"RSI moves to X" — and inventing one would undermine the credibility a
stress test is supposed to add rather than build it. If XGBoost-based stress
testing is wanted later, it needs its own separately-justified feature-shock
design, not a reuse of this one.

Shock methodology: each named scenario carries real, approximate historical
magnitudes (S&P 500 peak-to-trough drawdown, a realized/implied-volatility
multiplier) sourced from public market history, not a licensed vendor
dataset — directional and illustrative, not tick-precise. Per-metric
propagation, each with an actual rationale rather than an arbitrary number:

  - Volatility & tail metrics (vol_21d, vol_63d, downside_dev_63d,
    var_95_21d, cvar_95_21d, kurt_63d) scale *multiplicatively* by the
    scenario's vol_multiplier — Value-at-Risk and realized vol move roughly
    linearly with the vol regime under standard return-distribution
    assumptions.
  - skew_63d shifts by a fixed *additive* delta instead — left tails fatten
    during selloffs, but multiplying a near-zero (or positive) skew value
    wouldn't meaningfully shock it the way an additive shift does.
  - Drawdown metrics (drawdown, max_drawdown_63d) apply a CAPM-style
    beta-scaled shock: stock_shock = beta * scenario.market_drawdown. A
    stock's own historical beta determines how hard *it* falls in a given
    market-wide scenario — a fixed multiplier would ignore that a low-beta
    utility and a high-beta growth stock don't fall the same amount.
  - Liquidity metrics (amihud_illiq_21d, volume_vol_21d) scale
    multiplicatively by the scenario's liquidity_multiplier (liquidity dries
    up in a crisis).
  - beta_63d is left UNCHANGED — beta measures sensitivity itself; a
    scenario doesn't shock the quantity that determines its own propagation.
  - drawdown_duration and dollar_volume_21d are left UNCHANGED — duration is
    path-dependent and can't be inferred from a single point-in-time shock
    without simulating a full future path, and panic-driven volume can spike
    or vanish depending on the stock with no single defensible direction.
    Leaving both unchanged is a deliberate, documented simplification (it
    mildly understates the stressed drawdown/liquidity category scores)
    rather than a guessed number standing in for missing rigor.

Shocked values are ranked against the stock's own real historical
distribution via risk_categories.category_score/composite_score's existing
percentile machinery (passed a modified `latest` row) — not a separately
fit model — so results stay tied to the explainable baseline's own,
already-validated methodology.

Known limitation — percentile saturation: once a shocked value already falls
outside the stock's entire historical range, its percentile rank is ~100
regardless of how much further it's pushed. Within a single scenario,
stressed_score >= baseline_score is guaranteed (see run_stress_test's
docstring); but *across* scenarios, a more severe one (e.g. 2008) is not
guaranteed to produce a strictly higher stressed_score than a milder one
(e.g. 2022) for the same stock — both can saturate near 100 if the stock's
own history is calm relative to either shock, and they also use different
regime-implied weight profiles. The underlying shocked metric *values*
remain correctly ordered by severity (see apply_shock); only the final
percentile-ranked, reweighted score can tie or invert near the ceiling.
This is an inherent property of percentile-based scoring, not a bug — it's
the same reason a 99th-percentile event and a 1-in-a-million event both
round to "worse than everything in history."
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from . import risk_categories

SCENARIOS: dict[str, dict] = {
    "2008_financial_crisis": {
        "label": "2008 Global Financial Crisis",
        "market_drawdown": -0.50,
        "vol_multiplier": 3.5,
        "liquidity_multiplier": 2.5,
        "skew_shift": -1.2,
    },
    "2020_covid_crash": {
        "label": "2020 COVID-19 Crash",
        "market_drawdown": -0.34,
        "vol_multiplier": 4.0,
        "liquidity_multiplier": 2.0,
        "skew_shift": -1.0,
    },
    "2022_rate_hike_selloff": {
        "label": "2022 Rate Hike Bear Market",
        "market_drawdown": -0.25,
        "vol_multiplier": 1.8,
        "liquidity_multiplier": 1.3,
        "skew_shift": -0.5,
    },
}

_VOL_TAIL_SCALED_COLS = [
    "vol_21d", "vol_63d", "downside_dev_63d", "var_95_21d", "cvar_95_21d", "kurt_63d",
]
_LIQUIDITY_SCALED_COLS = ["amihud_illiq_21d", "volume_vol_21d"]
_DRAWDOWN_COLS = ["drawdown", "max_drawdown_63d"]


def apply_shock(latest: pd.Series, scenario: dict, beta: Optional[float]) -> pd.Series:
    """Return a shocked copy of *latest* (the stock's current feature row)
    under *scenario*. See the module docstring for the propagation rationale.
    """
    shocked = latest.copy()
    beta_v = float(beta) if beta is not None and pd.notna(beta) else 1.0
    stock_shock = beta_v * scenario["market_drawdown"]

    for col in _VOL_TAIL_SCALED_COLS:
        if col in shocked.index and pd.notna(shocked[col]):
            shocked[col] = float(shocked[col]) * scenario["vol_multiplier"]

    if "skew_63d" in shocked.index and pd.notna(shocked["skew_63d"]):
        shocked["skew_63d"] = float(shocked["skew_63d"]) + scenario["skew_shift"]

    for col in _LIQUIDITY_SCALED_COLS:
        if col in shocked.index and pd.notna(shocked[col]):
            shocked[col] = float(shocked[col]) * scenario["liquidity_multiplier"]

    for col in _DRAWDOWN_COLS:
        if col in shocked.index:
            current = float(shocked[col]) if pd.notna(shocked[col]) else 0.0
            shocked[col] = min(current, stock_shock)  # more negative = worse

    return shocked


def _implied_regime_vix(scenario: dict) -> float:
    """Rough VIX proxy from the scenario's vol_multiplier, used only to pick
    a sensible category-weight profile via risk_categories.regime_adjusted_weights
    — not a claim about the scenario's literal historical VIX level."""
    baseline_vix = 15.0
    return baseline_vix * scenario["vol_multiplier"]


def run_stress_test(
    df: pd.DataFrame, beta: Optional[float] = None, scenarios: Optional[dict] = None
) -> dict:
    """Run each named scenario against the stock's latest feature row and
    report how the percentile composite score would move.

    Each scenario's baseline and stressed score are computed with the *same*
    category-weight profile (that scenario's regime-implied weights) so the
    reported delta reflects only the shock's effect — comparing the stressed
    score against a baseline computed with different (live/default) weights
    would silently mix in a regime-reweighting effect alongside the shock,
    making the delta not mean what it claims to. This also makes
    stressed_score >= baseline_score a guarantee, not just an empirical
    tendency: apply_shock never moves a metric in the risk-reducing
    direction, so every category's percentile score can only stay the same
    or rise, and a same-weights weighted sum of non-decreasing terms cannot
    decrease. `live_score` (top-level, using the model's actual default/VIX
    weights) is included separately for context — it generally won't exactly
    equal any individual scenario's same-weights baseline_score.
    """
    scenarios = scenarios or SCENARIOS
    latest = df.iloc[-1]
    live_score = risk_categories.composite_score(df)["composite_score"]

    results = {}
    for name, scenario in scenarios.items():
        shocked_row = apply_shock(latest, scenario, beta)
        weights = risk_categories.regime_adjusted_weights(_implied_regime_vix(scenario))
        baseline = risk_categories.composite_score(df, weights=weights)
        stressed = risk_categories.composite_score(df, weights=weights, latest=shocked_row)
        delta = round(stressed["composite_score"] - baseline["composite_score"], 1)
        results[name] = {
            "label": scenario["label"],
            "baseline_score": baseline["composite_score"],
            "stressed_score": stressed["composite_score"],
            "delta": delta,
            "narrative": (
                f"If {scenario['label']} conditions recurred, this stock's risk score "
                f"would move from {baseline['composite_score']} to {stressed['composite_score']} "
                f"({'+' if delta >= 0 else ''}{delta})."
            ),
            "stressed_categories": stressed["categories"],
        }
    return {"live_score": live_score, "scenarios": results}
