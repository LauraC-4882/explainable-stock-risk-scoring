"""End-to-end risk scoring pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
import pandas as pd
from loguru import logger

from ..config import settings
from ..data.fetcher import MarketDataFetcher
from ..data.preprocessor import DataPreprocessor
from ..features.risk_metrics import RiskMetrics
from ..features.technical import TechnicalFeatures
from ..llm.news_risk import extract_news_risk, summarize_news_risk
from ..models.volatility import VolatilityModel
from . import risk_categories
from .stress_test import run_stress_test

if TYPE_CHECKING:
    # Not imported at runtime — see [F1]: DownsideRiskModel/explain_prediction
    # pull in xgboost/shap at *their* module level, so importing them eagerly
    # here means merely `import stock_risk.scoring.scorer` (e.g. from
    # ui/dashboard.py, which never touches the ML leg until a user actually
    # scores a ticker) drags both multi-hundred-MB libraries into every
    # process that imports this module — including ones, like a 1GB free-tier
    # Streamlit dashboard, that can't afford to carry them just sitting idle.
    from ..models.downside_risk import DownsideRiskModel

# "cn" uses the CSI 300 ETF (510300.SS) rather than the raw index (000300.SS):
# the raw index ticker was found to have multi-day gaps via yfinance (verified
# live — 3 missing trading days in a 1mo pull) while the ETF tracking it had
# continuous daily bars, so it's the more reliable proxy despite being one
# step removed from the index itself.
MARKET_BENCHMARKS = {"us": "SPY", "hk": "^HSI", "cn": "510300.SS"}


def market_for_ticker(ticker: str) -> str:
    """Infer the market from a ticker's exchange suffix."""
    upper = ticker.upper()
    if upper.endswith(".HK"):
        return "hk"
    if upper.endswith(".SS") or upper.endswith(".SZ"):
        return "cn"
    return "us"


RISK_LABELS = {
    (0, 25): "LOW",
    (25, 50): "MODERATE",
    (50, 75): "HIGH",
    (75, 101): "EXTREME",
}

# Trading-day counts for each selectable timeframe, and how much *extra*
# history score_timeseries must fetch before that window so 21d/63d rolling
# metrics (vol_21d, max_drawdown_63d, ...) already have valid values on the
# first displayed day instead of returning NaN for the whole requested period.
_PERIOD_TRADING_DAYS = {"5d": 5, "1mo": 21, "3mo": 63, "6mo": 126, "1y": 252, "2y": 504}
_ROLLING_WARMUP_DAYS = 70  # covers the largest rolling window (63d) plus a buffer


def _fetch_period_for_display(period: str) -> str:
    """Map a display period to a yfinance fetch period with enough warm-up history."""
    needed = _PERIOD_TRADING_DAYS.get(period, 126) + _ROLLING_WARMUP_DAYS
    for fetch_period, days in [("6mo", 126), ("1y", 252), ("2y", 504), ("5y", 1260)]:
        if needed <= days:
            return fetch_period
    return "10y"


def _trim_to_display_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Drop the warm-up rows fetched by _fetch_period_for_display, keeping the
    last N trading days actually requested for display."""
    days = _PERIOD_TRADING_DAYS.get(period)
    return df.tail(days) if days else df


def _risk_note(benchmark_ticker: str) -> str:
    return (
        "Score reflects this stock's risk relative to its own historical distribution "
        f"(and market sensitivity vs. {benchmark_ticker}) — it is not a probability of loss, "
        "default probability, or investment recommendation."
    )


def _label(score: float) -> str:
    for (lo, hi), label in RISK_LABELS.items():
        if lo <= score < hi:
            return label
    return "EXTREME"


class RiskScorer:
    """Orchestrates data fetch → feature engineering → model scoring."""

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or settings.model_dir
        self.fetcher = MarketDataFetcher()
        self.preprocessor = DataPreprocessor()
        self.tech = TechnicalFeatures()
        self.risk = RiskMetrics()
        self._dr_model = self._try_load_downside_model()

    def _try_load_downside_model(self) -> "Optional[DownsideRiskModel]":
        try:
            from ..models.downside_risk import DownsideRiskModel  # deferred — see [F1]

            return DownsideRiskModel.load(self.model_dir)
        except Exception as exc:
            logger.debug(f"No pretrained DownsideRiskModel artefact found: {exc}")
            return None

    def score(self, ticker: str, period: str = "2y") -> dict:
        """Return a complete risk scorecard dict for *ticker*."""
        logger.info(f"Scoring {ticker}")

        market = market_for_ticker(ticker)
        benchmark_ticker = MARKET_BENCHMARKS.get(market, "SPY")

        raw = self.fetcher.fetch_history(ticker, period=period)
        df = self.preprocessor.process(raw)
        df = self.tech.compute(df)

        benchmark_log_return = None
        if ticker.upper() != benchmark_ticker:
            try:
                bench_raw = self.fetcher.fetch_history(benchmark_ticker, period=period)
                benchmark_log_return = self.preprocessor.process(bench_raw)["log_return"]
            except Exception as exc:
                logger.warning(f"Could not fetch benchmark {benchmark_ticker}: {exc}")

        df = self.risk.compute(df, benchmark_returns=benchmark_log_return)
        info = self.fetcher.fetch_info(ticker)
        iv = self.fetcher.fetch_options_iv(ticker)

        latest = df.iloc[-1]

        # VIX-threshold regime weighting: panic/elevated markets lean the
        # composite toward tail risk over day-to-day volatility (see
        # risk_categories.REGIME_WEIGHTS). The VIX is a US-market fear gauge —
        # there's no verified free equivalent wired in for HK/CN yet, so
        # non-US tickers fall back to the base (non-regime-adjusted) weights
        # rather than reusing VIX as a proxy it wasn't designed to represent.
        if market == "us":
            vix = self.fetcher.fetch_vix()
            regime = risk_categories.regime_for_vix(vix)
            weights = risk_categories.regime_adjusted_weights(vix)
        else:
            vix = None
            regime = "not_available"
            weights = risk_categories.CATEGORY_WEIGHTS

        # Percentile-based composite score across volatility/tail/drawdown/
        # sensitivity/liquidity categories (see risk_categories.py) — the
        # explainable baseline. XGBoost is a secondary, ML-derived signal.
        scorecard = risk_categories.composite_score(df, weights=weights)
        composite_score = scorecard["composite_score"]

        ml_drawdown_probability = None
        ml_drawdown_explanation = None
        if self._dr_model is not None:
            try:
                from ..models.explain import explain_prediction  # deferred — see [F1]

                ml_drawdown_probability = round(
                    float(self._dr_model.predict(df)["downside_risk_score"]), 1
                )
                ml_drawdown_explanation = explain_prediction(self._dr_model, df)
            except Exception as exc:
                logger.warning(
                    f"DownsideRiskModel prediction/explanation failed for {ticker}: {exc}"
                )

        # GARCH is fit live on this ticker's own return series — unlike the
        # pretrained XGBoost classifier, volatility clustering parameters are
        # instrument-specific and can't be learned once and reused cross-sectionally.
        garch_volatility_forecast = None
        try:
            garch = VolatilityModel().fit(df)
            forecast = garch.predict(df)
            garch_volatility_forecast = {
                "vol_1d": round(float(forecast["garch_vol_1d"]), 4),
                "vol_30d": round(float(forecast["garch_vol_30d"]), 4),
            }
        except Exception as exc:
            logger.warning(f"GARCH volatility forecast failed for {ticker}: {exc}")

        # News/event risk layer: real headlines via yfinance, but extraction is
        # currently a labeled mock (no live LLM call wired in — see llm/news_risk.py)
        news_articles = self.fetcher.fetch_news(ticker)
        news_extractions = [extract_news_risk(a) for a in news_articles]
        news_risk = summarize_news_risk(news_extractions)
        news_risk["llm_configured"] = False

        # Free alt-data via yfinance: analyst rating changes + insider transactions.
        # Informational for now — not folded into risk_score (see risk_categories.py's
        # calibrated weights); surfaced so the report can point to a concrete signal.
        alt_data = {
            "analyst_activity": self.fetcher.fetch_analyst_activity(ticker),
            "insider_activity": self.fetcher.fetch_insider_activity(ticker),
        }

        # Historical-scenario stress test on the explainable percentile score
        # only (not the XGBoost leg) — see stress_test.py's module docstring
        # for why, and for the shock-propagation rationale per metric.
        stress_test = None
        try:
            stress_test = run_stress_test(df, beta=info.get("beta"))
        except Exception as exc:
            logger.warning(f"Stress test failed for {ticker}: {exc}")

        return {
            "ticker": ticker.upper(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "risk_score": round(composite_score, 1),
            "risk_label": _label(composite_score),
            "risk_note": _risk_note(benchmark_ticker),
            "risk_breakdown": scorecard["categories"],
            "market_regime": {
                "vix": vix,
                "regime": regime,
                "market": market,
                "benchmark": benchmark_ticker,
            },
            "ml_drawdown_probability": ml_drawdown_probability,
            "ml_drawdown_explanation": ml_drawdown_explanation,
            "garch_volatility_forecast": garch_volatility_forecast,
            "news_risk": news_risk,
            "alt_data": alt_data,
            "stress_test": stress_test,
            "volatility_30d": round(float(latest.get("vol_63d", np.nan)), 4),
            "var_95": round(float(latest.get("var_95_21d", np.nan)), 4),
            "cvar_95": round(float(latest.get("cvar_95_21d", np.nan)), 4),
            "max_drawdown_90d": round(float(latest.get("max_drawdown_63d", np.nan)), 4),
            "beta": info.get("beta"),
            "implied_volatility": round(iv, 4) if iv else None,
            "name": info.get("shortName") or ticker.upper(),
            "indicators": {
                "rsi_14": round(float(latest.get("rsi_14", np.nan)), 2),
                "bb_pct": round(float(latest.get("bb_pct", np.nan)), 4),
                "atr_14": round(float(latest.get("atr_14", np.nan)), 4),
            },
            "fundamentals": {
                "sector": info.get("sector"),
                "market_cap": info.get("marketCap"),
                "trailing_pe": info.get("trailingPE"),
            },
        }

    # ── Timeseries scoring ────────────────────────────────────────────────────

    def score_timeseries(self, ticker: str, period: str = "6mo") -> list[dict]:
        """Return a daily risk scorecard list for the requested *period*."""
        logger.info(f"Timeseries for {ticker} | period={period}")
        raw = self.fetcher.fetch_history(ticker, period=_fetch_period_for_display(period))
        df = self.preprocessor.process(raw)
        df = self.tech.compute(df)
        df = self.risk.compute(df)
        df = _trim_to_display_period(df, period)

        results = []
        for idx, row in df.iterrows():
            score = self._heuristic_score_row(row)
            if np.isnan(score):
                continue
            vol = row.get("vol_21d")
            clipped = float(np.clip(score, 0, 100))
            results.append({
                "date": idx.strftime("%Y-%m-%d"),
                "close": round(float(row["close"]), 2),
                "risk_score": round(clipped, 1),
                "risk_label": _label(clipped),
                "volatility": round(float(vol), 4) if pd.notna(vol) else None,
            })
        return results

    def _heuristic_score_row(self, row: pd.Series) -> float:
        """Compute a 0–100 heuristic risk score for a single feature row."""
        vol = row.get("vol_21d")
        rsi = row.get("rsi_14")
        dd  = row.get("max_drawdown_63d")
        var = row.get("var_95_21d")

        if pd.isna(vol) and pd.isna(rsi):
            return np.nan

        # `x or default` silently breaks here: NaN is truthy in Python, so
        # `float("nan") or 0.25` evaluates to NaN, not the default — and NaN
        # propagates through the sum below, making the whole score NaN even
        # though vol/rsi were present. Use explicit pd.notna() checks instead.
        vol_v = float(vol) if pd.notna(vol) else 0.25
        c_vol = min(vol_v / 0.80 * 40, 40)

        rsi_v = float(rsi) if pd.notna(rsi) else 50.0
        c_rsi = 20 if rsi_v >= 70 else (5 if rsi_v <= 30 else 10)

        dd_v = float(dd) if pd.notna(dd) else 0.0
        c_dd  = min(abs(dd_v) / 0.30 * 20, 20)

        var_v = float(var) if pd.notna(var) else 0.02
        c_var = min(abs(var_v) / 0.05 * 20, 20)

        return c_vol + c_rsi + c_dd + c_var  # max = 100

    # _direction_probabilities (a sigmoid blend of RSI/Bollinger%B/EMA-distance/
    # Sharpe, rendered as "Upside 53% / Downside 47%") was removed after a
    # real backtest: 14 tickers x 2 years, 6,453 observations. Days it flagged
    # "up" (up_prob > 0.55) actually closed up 48.6% of the time — *below*
    # the 49.9% unconditional baseline — and days it flagged "down"
    # (up_prob < 0.45) closed up 50.9% of the time, i.e. inverted. Not just
    # noisy: measurably worse than a coin flip, on the exact claim ("likely
    # to increase/decrease") it displayed most prominently in the UI. See
    # README "Direction Signal" for the full writeup.
