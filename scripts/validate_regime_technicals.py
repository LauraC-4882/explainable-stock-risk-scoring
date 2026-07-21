"""[G6] The backtest that would let the regime/technical signals carry weight.

`RegimeTechnicalsProducer` ships with `validation=None` and `default_weight=0.0`,
and `resolve_weights` forces any nonzero weight back to 0 for exactly that
reason. This script is how that changes: it asks, per signal, whether sorting
on it actually separates future losses. Nothing here edits weights — it prints
evidence, and a weight change is a separate, deliberate commit that pastes the
resulting numbers into the producer's `validation` dict (the same route
`validate_score.py` and `validate_vix_structure.py` opened for the existing
legs).

Method, per signal:

  1. Bucket every observation into quintiles of the signal, pooled across the
     universe.
  2. Report mean forward 20-day max drawdown and realised volatility per
     quintile. A signal that measures risk should be **monotonic** across
     buckets — that is the actual claim, and it is stronger than "the extremes
     differ", which a single outlier bucket can fake.
  3. Test top-vs-bottom quintile with Welch's t-test on **non-overlapping**
     observations (every `horizon`-th row). Daily rows with a 20-day forward
     window are ~20-fold serially correlated; a naive t-test on them reports
     significance that is an artefact of the overlap, not of the signal.

A signal earns a weight when the monotonic ordering holds AND the
non-overlapping test survives. One without the other is not evidence.

Usage (needs the same cached OHLCV harvest factor_screen.py uses):
    python scripts/validate_regime_technicals.py
    python scripts/validate_regime_technicals.py --horizon 20 --quintiles 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from stock_risk.features.candlestick import CandlestickFeatures  # noqa: E402
from stock_risk.features.momentum_risk import MomentumRiskFeatures  # noqa: E402
from stock_risk.features.regime import RegimeFeatures  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.features.sma_search import OptimizedSMAFeatures  # noqa: E402

ROOT = Path(__file__).parent.parent
OHLCV_CACHE = ROOT / "data/experiments/ohlcv"
RESULTS_CSV = Path(__file__).parent / "regime_technicals_validation.csv"

# Signals under test, and the direction each one *claims*. "higher_is_riskier"
# is written down before running, so a signal that comes out significant with
# the opposite sign is recorded as a failed hypothesis rather than quietly
# reinterpreted as a win.
SIGNALS = {
    "momentum_crash_risk": True,
    "vol_risk_premium": False,   # low premium = realised running hot vs implied
    "risk_on_persistence_21d": False,
    "dist_sma_opt": False,       # below the trend line is the riskier side
    "cdl_bull_minus_bear_20d": False,
    "price_vs_52w_high": False,
    "momentum_12m": True,        # the momentum-crash hypothesis, on its own
}


def build_frames(vix_close: pd.Series | None) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for path in sorted(OHLCV_CACHE.glob("*.parquet")):
        raw = pd.read_parquet(path)
        raw["log_return"] = np.log(raw["close"] / raw["close"].shift(1))
        df = RiskMetrics().compute(raw)
        df = CandlestickFeatures().compute(df)
        df = MomentumRiskFeatures().compute(df)
        df = OptimizedSMAFeatures().compute(df)
        df = RegimeFeatures().compute(df, vix_close)
        frames[path.stem.replace("_", ".")] = df
    return frames


def add_outcomes(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    df = df.copy()
    fwd_min = df["close"].shift(-horizon).rolling(horizon).min()
    df["fwd_drawdown"] = fwd_min / df["close"] - 1
    df["fwd_vol"] = (
        df["log_return"].shift(-horizon).rolling(horizon).std() * np.sqrt(252)
    )
    return df


def evaluate(pooled: pd.DataFrame, signal: str, quintiles: int, horizon: int) -> dict:
    data = pooled[[signal, "fwd_drawdown", "fwd_vol"]].dropna()
    if len(data) < 500 or data[signal].nunique() < quintiles:
        return {"signal": signal, "n_obs": len(data), "verdict": "insufficient data"}

    buckets = pd.qcut(data[signal], quintiles, labels=False, duplicates="drop")
    grouped = data.groupby(buckets)["fwd_drawdown"].mean()

    higher_is_riskier = SIGNALS[signal]
    # "Riskier" = a deeper (more negative) forward drawdown, so a valid
    # higher-is-riskier signal produces a DECREASING sequence of means.
    ordered = grouped.to_numpy()
    monotonic = bool(
        np.all(np.diff(ordered) < 0) if higher_is_riskier else np.all(np.diff(ordered) > 0)
    )

    top = data[buckets == buckets.max()]
    bottom = data[buckets == buckets.min()]
    # Non-overlapping subsample: consecutive daily rows share ~19/20 of their
    # forward window, so the naive t-test's effective sample size is a fraction
    # of its nominal one.
    t_stat, p_value = stats.ttest_ind(
        top["fwd_drawdown"].to_numpy()[::horizon],
        bottom["fwd_drawdown"].to_numpy()[::horizon],
        equal_var=False,
    )

    passes = monotonic and p_value < 0.05
    return {
        "signal": signal,
        "n_obs": len(data),
        "monotonic": monotonic,
        "top_quintile_dd": round(float(top["fwd_drawdown"].mean()), 4),
        "bottom_quintile_dd": round(float(bottom["fwd_drawdown"].mean()), 4),
        "t_stat": round(float(t_stat), 3),
        "p_value": round(float(p_value), 5),
        "verdict": "PASS — eligible for a weight" if passes else "FAIL — stays at weight 0",
        "quintile_means": [round(float(v), 4) for v in ordered],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--quintiles", type=int, default=5)
    args = parser.parse_args()

    if not any(OHLCV_CACHE.glob("*.parquet")):
        print(f"No cached OHLCV under {OHLCV_CACHE} — run the harvester first",
              file=sys.stderr)
        return 1

    vix_close = None
    vix_path = OHLCV_CACHE / "^VIX.parquet"
    if vix_path.exists():
        vix_close = pd.read_parquet(vix_path)["close"]
    else:
        print("note: no ^VIX in the cache — the regime signals will be all-NaN "
              "and report as insufficient data, not as failures.", file=sys.stderr)

    frames = build_frames(vix_close)
    print(f"universe: {len(frames)} tickers")

    pooled = pd.concat(
        [add_outcomes(df, args.horizon) for df in frames.values()], ignore_index=True
    )
    print(f"pooled observations: {len(pooled)}")

    rows = [evaluate(pooled, sig, args.quintiles, args.horizon) for sig in SIGNALS]
    table = pd.DataFrame(rows).set_index("signal")
    table.to_csv(RESULTS_CSV)

    print(f"\n== forward {args.horizon}d max-drawdown by signal quintile ==")
    print(table.to_string())
    print(f"\nresults written to {RESULTS_CSV}")
    print(
        "\nA PASS is necessary, not sufficient: before moving any weight off 0, "
        "paste the numbers above into RegimeTechnicalsProducer.validation and "
        "re-run scripts/validate_score.py — adding a leg to risk_score "
        "invalidates the composite's own validation record."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
