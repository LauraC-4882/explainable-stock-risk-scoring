"""End-to-end risk scoring pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from ..config import settings
from ..data.fetcher import MarketDataFetcher
from ..data.preprocessor import DataPreprocessor
from ..features.technical import TechnicalFeatures
from ..features.risk_metrics import RiskMetrics
from ..models.downside_risk import DownsideRiskModel
from ..models.volatility import VolatilityModel
from ..models.explain import explain_prediction
from ..llm.news_risk import extract_news_risk, summarize_news_risk
from . import risk_categories

BENCHMARK_TICKER = "SPY"

RISK_LABELS = {
    (0, 25): "LOW",
    (25, 50): "MODERATE",
    (50, 75): "HIGH",
    (75, 101): "EXTREME",
}

RISK_NOTE = (
    "Score reflects this stock's risk relative to its own historical distribution "
    "(and market sensitivity vs. SPY) — it is not a probability of loss, default "
    "probability, or investment recommendation."
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

    def _try_load_downside_model(self) -> Optional[DownsideRiskModel]:
        try:
            return DownsideRiskModel.load(self.model_dir)
        except Exception as exc:
            logger.debug(f"No pretrained DownsideRiskModel artefact found: {exc}")
            return None

    def score(self, ticker: str, period: str = "2y") -> dict:
        """Return a complete risk scorecard dict for *ticker*."""
        logger.info(f"Scoring {ticker}")

        raw = self.fetcher.fetch_history(ticker, period=period)
        df = self.preprocessor.process(raw)
        df = self.tech.compute(df)

        benchmark_log_return = None
        if ticker.upper() != BENCHMARK_TICKER:
            try:
                bench_raw = self.fetcher.fetch_history(BENCHMARK_TICKER, period=period)
                benchmark_log_return = self.preprocessor.process(bench_raw)["log_return"]
            except Exception as exc:
                logger.warning(f"Could not fetch benchmark {BENCHMARK_TICKER}: {exc}")

        df = self.risk.compute(df, benchmark_returns=benchmark_log_return)
        info = self.fetcher.fetch_info(ticker)
        iv = self.fetcher.fetch_options_iv(ticker)

        latest = df.iloc[-1]

        # Percentile-based composite score across volatility/tail/drawdown/
        # sensitivity/liquidity categories (see risk_categories.py) — the
        # explainable baseline. XGBoost is a secondary, ML-derived signal.
        scorecard = risk_categories.composite_score(df)
        composite_score = scorecard["composite_score"]

        ml_drawdown_probability = None
        ml_drawdown_explanation = None
        if self._dr_model is not None:
            try:
                ml_drawdown_probability = round(
                    float(self._dr_model.predict(df)["downside_risk_score"]), 1
                )
                ml_drawdown_explanation = explain_prediction(self._dr_model, df)
            except Exception as exc:
                logger.warning(f"DownsideRiskModel prediction/explanation failed for {ticker}: {exc}")

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

        return {
            "ticker": ticker.upper(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "risk_score": round(composite_score, 1),
            "risk_label": _label(composite_score),
            "risk_note": RISK_NOTE,
            "risk_breakdown": scorecard["categories"],
            "ml_drawdown_probability": ml_drawdown_probability,
            "ml_drawdown_explanation": ml_drawdown_explanation,
            "garch_volatility_forecast": garch_volatility_forecast,
            "news_risk": news_risk,
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
        raw = self.fetcher.fetch_history(ticker, period=period)
        df = self.preprocessor.process(raw)
        df = self.tech.compute(df)
        df = self.risk.compute(df)

        results = []
        for idx, row in df.iterrows():
            score = self._heuristic_score_row(row)
            if np.isnan(score):
                continue
            up_prob, down_prob = self._direction_probabilities(row)
            vol = row.get("vol_21d")
            clipped = float(np.clip(score, 0, 100))
            results.append({
                "date": idx.strftime("%Y-%m-%d"),
                "close": round(float(row["close"]), 2),
                "risk_score": round(clipped, 1),
                "risk_label": _label(clipped),
                "up_prob": round(float(up_prob), 3),
                "down_prob": round(float(down_prob), 3),
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

        c_vol = min(float(vol or 0.25) / 0.80 * 40, 40)

        rsi_v = float(rsi) if pd.notna(rsi) else 50.0
        c_rsi = 20 if rsi_v >= 70 else (5 if rsi_v <= 30 else 10)

        c_dd  = min(abs(float(dd or 0.0)) / 0.30 * 20, 20)
        c_var = min(abs(float(var or 0.02)) / 0.05 * 20, 20)

        return c_vol + c_rsi + c_dd + c_var  # max = 100

    def _direction_probabilities(self, row: pd.Series) -> tuple[float, float]:
        """Estimate up/down probability via sigmoid aggregation of technical signals."""
        signals: list[float] = []

        rsi = row.get("rsi_14")
        if pd.notna(rsi):
            signals.append((50.0 - float(rsi)) / 50.0)   # < 50 = bullish

        bb_pct = row.get("bb_pct")
        if pd.notna(bb_pct):
            signals.append(0.5 - float(bb_pct))           # near lower band = bullish

        dist = row.get("dist_ema_20")
        if pd.notna(dist):
            signals.append(-np.clip(float(dist) * 3, -1.0, 1.0))  # mean reversion

        sharpe = row.get("sharpe_63d")
        if pd.notna(sharpe):
            signals.append(np.clip(float(sharpe) / 3, -1.0, 1.0))  # trend quality

        if not signals:
            return 0.5, 0.5

        avg = float(np.mean(signals))
        up_prob = 1.0 / (1.0 + np.exp(-avg * 3))
        return up_prob, 1.0 - up_prob
