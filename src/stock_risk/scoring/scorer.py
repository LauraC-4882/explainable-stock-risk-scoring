"""End-to-end risk scoring pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
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
from . import risk_categories
from .producers import (
    ScoringContext,
    build_producers,
    fuse_with_composition,
    resolve_weights,
    run_producer,
)
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


def _risk_note(benchmark_ticker: str, ml_share: float = 0.0) -> str:
    """The per-response disclaimer, reflecting what THIS response's score is
    actually made of (a request where the ML leg was unavailable renormalises
    to pure percentile, and its note must say the pre-fusion thing)."""
    if ml_share > 0:
        pct = round((1 - ml_share) * 100)
        ml = round(ml_share * 100)
        return (
            f"Score blends this stock's risk percentile relative to its own history ({pct}%) "
            f"with a walk-forward-validated ML estimate of its 20-day severe-drawdown "
            f"probability ({ml}%), plus market sensitivity vs. {benchmark_ticker} — it is "
            "not a probability of loss, default probability, or investment recommendation."
        )
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


def _resolve_beta(fundamental_beta, computed_beta) -> Optional[float]:
    """The beta shown in the metric tile: yfinance's fundamental beta when
    available, else the 63-day rolling beta computed against the market
    benchmark (SPY / CSI 300 / HSI — all now sourced from Twelve Data or
    akshare, see data/fetcher.py). fetch_info is yfinance-only and degrades
    to {} whenever Yahoo throttles the egress IP, so without this fallback
    every stock's beta tile reads "—" on a throttled deploy even though a
    perfectly good benchmark-relative beta was already computed for the
    sensitivity risk category."""
    if fundamental_beta is not None:
        return fundamental_beta
    if computed_beta is not None and pd.notna(computed_beta):
        return round(float(computed_beta), 2)
    return None


class RiskScorer:
    """Orchestrates data fetch → feature engineering → model scoring."""

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or settings.model_dir
        self.fetcher = MarketDataFetcher()
        self.preprocessor = DataPreprocessor()
        self.tech = TechnicalFeatures()
        self.risk = RiskMetrics()
        self._dr_model = self._try_load_downside_model()
        # [G1] producer layer: the five risk signals as uniform RiskProducer
        # instances. resolve_weights applies the validation guard at startup
        # (unvalidated producer with nonzero weight -> warned + zeroed).
        self.producers = build_producers(self._dr_model)
        self.producer_weights = resolve_weights(self.producers)

    def _try_load_downside_model(self) -> "Optional[DownsideRiskModel]":
        if not settings.enable_ml:
            # [F2]: skip the import entirely, not just the load — the goal is
            # keeping xgboost (and, transitively via explain_prediction,
            # shap) out of sys.modules on memory-constrained deploys, and an
            # attempted-then-discarded import would already have paid that
            # memory cost.
            logger.info("ENABLE_ML=0 — skipping DownsideRiskModel load")
            return None
        try:
            from ..models.downside_risk import DownsideRiskModel  # deferred — see [F1]

            return DownsideRiskModel.load(self.model_dir)
        except Exception as exc:
            logger.debug(f"No pretrained DownsideRiskModel artefact found: {exc}")
            return None

    # Periods long enough to serve as a percentile-ranking baseline on their
    # own; anything shorter is floored to "2y" in score() below.
    _BASELINE_PERIODS = frozenset({"2y", "5y", "10y", "max"})

    def score(self, ticker: str, period: str = "2y") -> dict:
        """Return a complete risk scorecard dict for *ticker*.

        *period* is the percentile-ranking baseline, not a display window, and
        is floored at "2y" — see the comment on the fetch below.
        """
        logger.info(f"Scoring {ticker}")

        market = market_for_ticker(ticker)
        benchmark_ticker = MARKET_BENCHMARKS.get(market, "SPY")

        # The composite ranks today's metrics within this stock's OWN history,
        # so the fetch length is the ranking baseline itself. The UI's
        # timeframe selector goes down to "5d"; ranking one observation
        # against five falls below risk_categories._MIN_HISTORY, which drops
        # every metric and silently returns the neutral 50 fallback for every
        # stock — a plausible-looking number with no information in it. The
        # baseline is therefore floored at 2y independently of any display
        # period the caller passes, matching the identical floor
        # score_timeseries applies and keeping the two paths comparable.
        period = period if period in self._BASELINE_PERIODS else "2y"

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
        # fetch_info is still yfinance-only (unlike fetch_history — see
        # data/fetcher.py's migration) and every downstream use is
        # info.get(...)-safe, so a failure here degrades to an empty dict
        # (matching the benchmark-fetch pattern above) instead of taking
        # down a request whose actual price history fetch already succeeded.
        try:
            info = self.fetcher.fetch_info(ticker)
        except Exception as exc:
            logger.warning(f"Could not fetch info for {ticker}: {exc}")
            info = {}
        # [G4] one chain snapshot feeds both the compat implied_volatility
        # field and the options_implied block (put skew etc.).
        options_signals = self.fetcher.fetch_options_signals(ticker)
        iv = options_signals["atm_iv"]

        latest = df.iloc[-1]

        # VIX-threshold regime weighting: panic/elevated markets lean the
        # composite toward tail risk over day-to-day volatility (see
        # risk_categories.REGIME_WEIGHTS). The VIX is a US-market fear gauge —
        # there's no verified free equivalent wired in for HK/CN yet, so
        # non-US tickers fall back to the base (non-regime-adjusted) weights
        # rather than reusing VIX as a proxy it wasn't designed to represent.
        if market == "us":
            vix = self.fetcher.fetch_vix()
            vix3m = self.fetcher.fetch_vix3m()  # [G4] term-structure leg
            regime = risk_categories.regime_for_vix(vix)
            weights = risk_categories.regime_adjusted_weights(vix)
        else:
            vix = None
            vix3m = None
            regime = "not_available"
            weights = risk_categories.CATEGORY_WEIGHTS

        # [G1] Shared inputs are fetched exactly once here and handed to every
        # producer via the context — a producer can never add a hidden network
        # call. The per-signal computation (and its degradation policy) lives
        # in scoring/producers/, not in this method anymore.
        ctx = ScoringContext(
            ticker=ticker.upper(),
            market=market,
            benchmark_ticker=benchmark_ticker,
            category_weights=weights,
            vix=vix,
            vix3m=vix3m,
            regime=regime,
            info=info,
            iv=iv,
            options_signals=options_signals,
            news_articles=self.fetcher.fetch_news(ticker),
            analyst_activity=self.fetcher.fetch_analyst_activity(ticker),
            insider_activity=self.fetcher.fetch_insider_activity(ticker),
        )

        outputs = {p.name: run_producer(p, df, ctx) for p in self.producers}

        # Fusion gate open (see build_producers): {percentile: 0.85,
        # ml_drawdown: 0.15} by default. When the ML leg is unavailable the
        # weights renormalise to the percentile alone — identical to the
        # pre-fusion score — and risk_score_composition reports what actually
        # contributed. The 50.0 fallback is unreachable today (composite_score
        # always returns a number and percentile is a required producer) but
        # keeps the None-contract honest.
        fused, composition = fuse_with_composition(outputs, self.producer_weights)
        composite_score = fused if fused is not None else 50.0
        ml_share = next(
            (c["weight"] for c in composition if c["producer"] == "ml_drawdown"), 0.0
        )

        pct = outputs["percentile_composite"]  # required producer — never None
        ml = outputs["ml_drawdown"]
        garch = outputs["garch_vol"]
        har = outputs["har_vol"]
        opts = outputs["options_implied"]
        news = outputs["news_risk"]
        alt = outputs["alt_data"]

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
            # timezone-aware now() (the naive-UTC variant is deprecated);
            # .replace keeps the ISO string's trailing "Z" format instead of
            # "+00:00" so API consumers see no change.
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "risk_score": round(composite_score, 1),
            "risk_label": _label(composite_score),
            "risk_note": _risk_note(benchmark_ticker, ml_share),
            "risk_score_composition": composition,
            "risk_breakdown": pct.detail["categories"],
            "market_regime": {
                "vix": vix,
                "regime": regime,
                "market": market,
                "benchmark": benchmark_ticker,
            },
            "ml_drawdown_probability": ml.raw["probability"] if ml else None,
            "ml_drawdown_explanation": ml.detail["explanation"] if ml else None,
            "garch_volatility_forecast": garch.raw if garch else None,
            "har_volatility_forecast": har.raw if har else None,
            "options_implied": opts.raw if opts else {
                "atm_iv": None, "put_skew": None, "iv_hv_ratio": None,
                "vix_term_structure": None, "expiry": None,
            },
            # news/alt producers are pure computation over already-fetched
            # context and shouldn't fail, but keep the response shape stable
            # if one ever does (pre-refactor these fields were never null).
            "news_risk": news.raw if news else {
                "max_severity": 0, "negative_count": 0, "articles": [], "llm_configured": False,
            },
            "alt_data": alt.raw if alt else {
                "analyst_activity": ctx.analyst_activity,
                "insider_activity": ctx.insider_activity,
            },
            "stress_test": stress_test,
            "volatility_30d": round(float(latest.get("vol_63d", np.nan)), 4),
            "var_95": round(float(latest.get("var_95_21d", np.nan)), 4),
            "cvar_95": round(float(latest.get("cvar_95_21d", np.nan)), 4),
            "max_drawdown_90d": round(float(latest.get("max_drawdown_63d", np.nan)), 4),
            "beta": _resolve_beta(info.get("beta"), latest.get("beta_63d")),
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

    # _fetch_period_for_display's own floor only covers rolling-window warmup
    # (21d/63d indicators). score()'s card path always fetches "2y" of history
    # for percentile ranking; a short display period (e.g. "6mo" -> "1y" fetch)
    # would rank the same current value against a materially shorter history
    # than the card does, producing a different score for the same day even
    # with identical weights — so the *fetch* period is floored at "2y" here,
    # independent of the (smaller) display period, purely to keep the
    # percentile-ranking history in sync with score()'s.
    _SHORT_FETCH_PERIODS = {"6mo", "1y"}

    def score_timeseries(self, ticker: str, period: str = "6mo") -> list[dict]:
        """Return a daily risk scorecard list for the requested *period*,
        computed via the same percentile composite score as score() — not a
        separate heuristic. Each day's score uses only data up to and
        including that day (composite_score(df.iloc[:i+1])), so this is
        genuinely no-lookahead, not just a display-window slice of a
        whole-history calculation (see tests/test_risk_categories.py::
        test_composite_score_has_no_lookahead for the version of this
        guarantee that's actually verified against a truncated raw series).
        """
        logger.info(f"Timeseries for {ticker} | period={period}")
        market = market_for_ticker(ticker)
        benchmark_ticker = MARKET_BENCHMARKS.get(market, "SPY")

        fetch_period = _fetch_period_for_display(period)
        if fetch_period in self._SHORT_FETCH_PERIODS:
            fetch_period = "2y"

        raw = self.fetcher.fetch_history(ticker, period=fetch_period)
        df = self.preprocessor.process(raw)
        df = self.tech.compute(df)

        # Same benchmark passthrough as score() — without it, beta_63d is
        # never computed, the sensitivity category has no metrics, and
        # composite_score drops it and renormalises the remaining four
        # categories' weights, which systematically diverges from the card's
        # score (which always has all five) rather than just adding noise.
        benchmark_log_return = None
        if ticker.upper() != benchmark_ticker:
            try:
                bench_raw = self.fetcher.fetch_history(benchmark_ticker, period=fetch_period)
                benchmark_log_return = self.preprocessor.process(bench_raw)["log_return"]
            except Exception as exc:
                logger.warning(f"Could not fetch benchmark {benchmark_ticker}: {exc}")

        df = self.risk.compute(df, benchmark_returns=benchmark_log_return)

        # The card (score()) applies VIX-regime-adjusted weights for US
        # tickers. Historical VIX isn't fetched here (fetch_vix() only
        # returns the current level), so only the LAST day — the one that
        # gets compared directly against the card's score — uses the current
        # regime weights; earlier days use the base weights, which is a
        # documented approximation, not a claim that every historical day's
        # regime is known.
        if market == "us":
            vix = self.fetcher.fetch_vix()
            last_day_weights = risk_categories.regime_adjusted_weights(vix)
        else:
            last_day_weights = risk_categories.CATEGORY_WEIGHTS

        display = _trim_to_display_period(df, period)
        start_pos = len(df) - len(display)
        last_pos = len(df) - 1

        results = []
        for i in range(start_pos, len(df)):
            row = df.iloc[i]
            weights = last_day_weights if i == last_pos else risk_categories.CATEGORY_WEIGHTS
            scorecard = risk_categories.composite_score(df.iloc[: i + 1], weights=weights)
            score = scorecard["composite_score"]
            vol = row.get("vol_21d")
            results.append({
                "date": df.index[i].strftime("%Y-%m-%d"),
                "close": round(float(row["close"]), 2),
                "risk_score": score,
                "risk_label": _label(score),
                "volatility": round(float(vol), 4) if pd.notna(vol) else None,
            })
        return results

    # _direction_probabilities (a sigmoid blend of RSI/Bollinger%B/EMA-distance/
    # Sharpe, rendered as "Upside 53% / Downside 47%") was removed after a
    # real backtest: 14 tickers x 2 years, 6,453 observations. Days it flagged
    # "up" (up_prob > 0.55) actually closed up 48.6% of the time — *below*
    # the 49.9% unconditional baseline — and days it flagged "down"
    # (up_prob < 0.45) closed up 50.9% of the time, i.e. inverted. Not just
    # noisy: measurably worse than a coin flip, on the exact claim ("likely
    # to increase/decrease") it displayed most prominently in the UI. See
    # README "Direction Signal" for the full writeup.
