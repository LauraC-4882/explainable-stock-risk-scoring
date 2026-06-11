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
from ..models.volatility import VolatilityModel
from ..models.downside_risk import DownsideRiskModel


RISK_LABELS = {
    (0, 25): "LOW",
    (25, 50): "MODERATE",
    (50, 75): "HIGH",
    (75, 101): "EXTREME",
}


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
        self._vol_model: Optional[VolatilityModel] = None
        self._dr_model: Optional[DownsideRiskModel] = None

    def _load_models(self):
        try:
            self._vol_model = VolatilityModel()
            self._dr_model = DownsideRiskModel()
        except Exception as exc:
            logger.warning(f"Could not load pre-trained models: {exc}. Using heuristic scoring.")

    def score(self, ticker: str, period: str = "2y") -> dict:
        """Return a complete risk scorecard dict for *ticker*."""
        logger.info(f"Scoring {ticker}")

        raw = self.fetcher.fetch_history(ticker, period=period)
        df = self.preprocessor.process(raw)
        df = self.tech.compute(df)
        df = self.risk.compute(df)
        info = self.fetcher.fetch_info(ticker)
        iv = self.fetcher.fetch_options_iv(ticker)

        latest = df.iloc[-1]

        # Heuristic composite score (used when model artefacts are absent)
        score_components = self._heuristic_score(df, latest, info, iv)
        composite_score = np.clip(score_components["composite"], 0, 100)

        return {
            "ticker": ticker.upper(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "risk_score": round(composite_score, 1),
            "risk_label": _label(composite_score),
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

    def _heuristic_score(
        self, df: pd.DataFrame, latest: pd.Series, info: dict, iv: Optional[float]
    ) -> dict:
        """Weighted heuristic when no trained model is available."""
        components = {}

        # Volatility component (higher vol → higher risk)
        vol = latest.get("vol_21d", 0.25)
        components["vol"] = min(vol / 0.80 * 40, 40)  # cap at 40 points

        # Momentum / RSI component
        rsi = latest.get("rsi_14", 50)
        if rsi >= 70:
            components["rsi"] = 20
        elif rsi <= 30:
            components["rsi"] = 5
        else:
            components["rsi"] = 10

        # Drawdown component
        dd = abs(latest.get("max_drawdown_63d", 0))
        components["drawdown"] = min(dd / 0.30 * 20, 20)

        # VaR component
        var = abs(latest.get("var_95_21d", 0.02))
        components["var"] = min(var / 0.05 * 20, 20)

        components["composite"] = sum(components.values())
        return components

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
