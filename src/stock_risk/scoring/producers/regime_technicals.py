"""[G6] Regime + technical-structure producer: realised-vs-implied volatility
regime, cyclical/defensive sector tilt, trend state, and candlestick patterns.

**score=None, default_weight=0.0 — display-only, by the repo's own rule, not
by oversight.** `resolve_weights` refuses a nonzero weight on a producer with
`validation=None`, and none of these signals has been walk-forward backtested
against forward drawdown yet. Folding them into `risk_score` today would be
exactly the "launder unvalidated numbers into the headline" failure the
producer layer was built to prevent (see base.py). `scripts/validate_regime_
technicals.py` is the backtest that would earn them a weight; until it reports
a real edge, these numbers inform the reader and do not move the score.

There is a second, independent reason not to reach for `_METRIC_SPECS`
instead: `PercentileCompositeProducer.validation` records a quintile backtest
+ Kupiec test run against *that specific metric set*. Adding columns to
`risk_categories._METRIC_SPECS` silently invalidates that record, and
`score_timeseries` (which recomputes the composite per day without these
columns) would start diverging from the card's score — widening the known
[E1] gauge-vs-chart inconsistency rather than leaving it alone.

What each block reports:

  - **regime** — the stock's realised volatility against the VIX as quoted a
    month ago. Risk-on when realised came in under what was implied (plus a
    buffer); the persistence figure says how much of the last month agreed,
    because a single day's flag flips on noise near the threshold.
  - **sector_tilt** — rolling beta to a cyclical proxy vs a defensive one. A
    single market beta cannot separate "moves with the market because it is
    cyclical" from "moves with the market because it is large"; the difference
    between the two betas can.
  - **trend** — the walk-forward-selected moving-average window and the
    current side of it. The *selected window* is itself informative: it drifts
    short in choppy tape and long in trending tape.
  - **patterns** — candlestick reversal patterns printed in the recent window,
    plus net bullish-minus-bearish pattern pressure.
  - **momentum** — 1/3/12-month price momentum, position within the 52-week
    range, and the momentum-crash interaction (high run-up AND high
    volatility), which neither a momentum column nor a volatility column
    expresses on its own.

Every block degrades to None independently: a throttled VIX fetch empties
`regime` and leaves `patterns` (pure OHLC, no network) intact.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import ProducerOutput, RiskProducer, ScoringContext

# How far back to look for a printed reversal pattern. Two weeks of trading:
# far enough that a card is rarely empty, short enough that what it shows is
# still about the current setup rather than last quarter's.
_PATTERN_LOOKBACK = 10

_PATTERN_LABELS = {
    "cdl_hammer": "hammer",
    "cdl_shooting_star": "shooting_star",
    "cdl_bull_engulfing": "bullish_engulfing",
    "cdl_bear_engulfing": "bearish_engulfing",
    "cdl_doji": "doji",
}

_BULLISH = {"hammer", "bullish_engulfing"}
_BEARISH = {"shooting_star", "bearish_engulfing"}

# |beta_on - beta_off| below this reads as "no meaningful tilt" rather than a
# direction. Betas carry estimation error of roughly this size over a 63-day
# window, so calling a 0.05 gap "cyclical" would be reporting noise as a finding.
_TILT_DEADBAND = 0.15


def _num(value) -> Optional[float]:
    """Native float, or None for missing. Native because a numpy scalar in an
    API response raises inside json.dumps (CLAUDE.md rule 4)."""
    if value is None or pd.isna(value):
        return None
    return float(value)


class RegimeTechnicalsProducer(RiskProducer):
    """Display-only regime/technical structure block — see module docstring."""

    name = "regime_technicals"
    default_weight = 0.0
    validation = None

    def produce(self, df: pd.DataFrame, ctx: ScoringContext) -> ProducerOutput:
        latest = df.iloc[-1]
        return ProducerOutput(
            score=None,
            raw={
                "regime": self._regime(latest),
                "sector_tilt": self._sector_tilt(latest),
                "trend": self._trend(latest),
                "patterns": self._patterns(df),
                "momentum": self._momentum(latest),
            },
        )

    # ── Blocks ───────────────────────────────────────────────────────────────

    @staticmethod
    def _regime(latest: pd.Series) -> Optional[dict]:
        premium = _num(latest.get("vol_risk_premium"))
        if premium is None:
            return None
        return {
            "state": "risk_on" if premium > 0 else "risk_off",
            "realized_vol_pct": round(_num(latest.get("realized_vol_pct")) or 0.0, 2),
            "implied_vol_lagged_pct": round(_num(latest.get("vix_lagged_pct")) or 0.0, 2),
            "vol_risk_premium": round(premium, 2),
            "persistence_21d": (
                round(p, 3)
                if (p := _num(latest.get("risk_on_persistence_21d"))) is not None
                else None
            ),
        }

    @staticmethod
    def _sector_tilt(latest: pd.Series) -> Optional[dict]:
        tilt = _num(latest.get("risk_on_tilt"))
        if tilt is None:
            return None
        if tilt > _TILT_DEADBAND:
            reading = "cyclical"
        elif tilt < -_TILT_DEADBAND:
            reading = "defensive"
        else:
            reading = "balanced"
        beta_on = _num(latest.get("beta_risk_on_63d"))
        beta_off = _num(latest.get("beta_risk_off_63d"))
        return {
            "beta_risk_on": round(beta_on, 3) if beta_on is not None else None,
            "beta_risk_off": round(beta_off, 3) if beta_off is not None else None,
            "tilt": round(tilt, 3),
            "reading": reading,
        }

    @staticmethod
    def _trend(latest: pd.Series) -> Optional[dict]:
        distance = _num(latest.get("dist_sma_opt"))
        window = _num(latest.get("sma_opt_window"))
        if distance is None or window is None:
            return None
        return {
            "sma_window": int(window),
            "distance_pct": round(distance * 100, 2),
            "state": "above" if distance > 0 else "below",
        }

    @staticmethod
    def _momentum(latest: pd.Series) -> Optional[dict]:
        crash = _num(latest.get("momentum_crash_risk"))
        m3 = _num(latest.get("momentum_3m"))
        if crash is None and m3 is None:
            return None

        def pct(key: str) -> Optional[float]:
            v = _num(latest.get(key))
            return round(v * 100, 2) if v is not None else None

        return {
            "momentum_1m_pct": pct("momentum_1m"),
            "momentum_3m_pct": pct("momentum_3m"),
            "momentum_12m_pct": pct("momentum_12m"),
            "crash_risk": round(crash, 3) if crash is not None else None,
            # Reader-facing band for the interaction score. The cut points are
            # descriptive labels for a 0-1 percentile product, NOT calibrated
            # thresholds — nothing has been backtested against forward
            # drawdown yet (see module docstring), and naming them "elevated"
            # rather than "sell" is the whole point.
            "crash_risk_band": (
                None if crash is None
                else "elevated" if crash >= 0.64
                else "moderate" if crash >= 0.36
                else "low"
            ),
            "vs_52w_high_pct": pct("price_vs_52w_high"),
            "pct_of_52w_range": (
                round(v * 100, 1)
                if (v := _num(latest.get("pct_of_52w_range"))) is not None
                else None
            ),
        }

    @staticmethod
    def _patterns(df: pd.DataFrame) -> Optional[dict]:
        available = [c for c in _PATTERN_LABELS if c in df.columns]
        if not available:
            return None

        recent = df.tail(_PATTERN_LOOKBACK)
        hits = []
        for col in available:
            for date in recent.index[recent[col] == 1]:
                hits.append({
                    "name": _PATTERN_LABELS[col],
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                })
        # Newest first — the most recent print is the one a reader cares about.
        hits.sort(key=lambda h: h["date"], reverse=True)

        pressure = _num(df.iloc[-1].get("cdl_bull_minus_bear_20d"))
        return {
            "recent": hits,
            "bullish_count": sum(1 for h in hits if h["name"] in _BULLISH),
            "bearish_count": sum(1 for h in hits if h["name"] in _BEARISH),
            "net_pressure_20d": int(pressure) if pressure is not None else None,
            "lookback_days": _PATTERN_LOOKBACK,
        }
