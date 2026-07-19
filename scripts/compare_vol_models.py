"""[G5] Volatility-model shootout: GARCH(1,1)-Normal (old default) vs
GJR-GARCH-skewt (new default) vs HAR-RV on Garman-Klass vol.

Loss functions: QLIKE (the standard vol-forecast loss — asymmetric, punishes
UNDER-estimating risk harder than over-estimating, which is the right
asymmetry for a downside-risk system) and RMSE on vol levels, at two
horizons (1 day and 20-day total). Expanding-window refits every 21 trading
days per ticker (a full daily refit x 3 models x 20+ tickers would be
thousands of MLE fits for no extra insight). Whoever wins becomes the
default; the table goes into the README/PR either way.

Reads the same disk cache as the other [G2]/[G3] experiment scripts.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402

from stock_risk.models.har_volatility import HarVolatilityModel, gk_daily_vol  # noqa: E402
from stock_risk.models.volatility import VolatilityModel  # noqa: E402

ROOT = Path(__file__).parent.parent
OHLCV_CACHE = ROOT / "data/experiments/ohlcv"

REFIT_EVERY = 21
TRAIN_FRAC = 0.6
H_LONG = 20


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    return df.dropna(subset=["log_return"])


def _garch_paths(model: VolatilityModel, horizon: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fc = model._fit_result.forecast(horizon=horizon, reindex=False)
    return np.asarray(fc.variance.values[-1]) / model.rescale**2  # daily variances


def _har_paths(model: HarVolatilityModel, horizon: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fc = model._fit_result.forecast(horizon=horizon, reindex=False)
    vols = np.clip(fc.mean.values[-1], 1e-8 * model.rescale, None) / model.rescale
    return vols**2


def qlike(realized_var: float, forecast_var: float) -> float:
    ratio = realized_var / forecast_var
    return float(ratio - np.log(ratio) - 1)


def evaluate_ticker(df: pd.DataFrame) -> list[dict]:
    df = _prep(df)
    daily_gk = gk_daily_vol(df)
    n = len(df)
    start = int(n * TRAIN_FRAC)
    rows = []
    for t in range(start, n - H_LONG, REFIT_EVERY):
        train = df.iloc[:t]
        # Realized targets from the forward window (never seen by the fits)
        real_var_1d = float(daily_gk.iloc[t] ** 2)
        real_var_20d = float((df["log_return"].iloc[t:t + H_LONG] ** 2).sum())
        if real_var_1d <= 0 or real_var_20d <= 0:
            continue

        fits = {}
        try:
            fits["garch_normal"] = VolatilityModel(o=0, dist="Normal").fit(train)
            fits["gjr_skewt"] = VolatilityModel().fit(train)
            fits["har_rv"] = HarVolatilityModel().fit(train)
        except Exception as exc:
            logger.warning(f"fit failed at t={t}: {exc}")
            continue

        for name, model in fits.items():
            paths = (
                _har_paths(model, H_LONG) if name == "har_rv" else _garch_paths(model, H_LONG)
            )
            f_var_1d = float(paths[0])
            f_var_20d = float(paths.sum())
            rows.append({
                "model": name,
                "qlike_1d": qlike(real_var_1d, f_var_1d),
                "qlike_20d": qlike(real_var_20d, f_var_20d),
                "rmse_1d_sq": (np.sqrt(real_var_1d) - np.sqrt(f_var_1d)) ** 2,
                "rmse_20d_sq": (np.sqrt(real_var_20d) - np.sqrt(f_var_20d)) ** 2,
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="[G5] volatility model comparison")
    parser.add_argument("--min-tickers", type=int, default=20)
    args = parser.parse_args()

    paths = sorted(OHLCV_CACHE.glob("*.parquet"))
    if len(paths) < args.min_tickers:
        print(
            f"Need >= {args.min_tickers} cached tickers under {OHLCV_CACHE}, "
            f"found {len(paths)} — run the harvester first",
            file=sys.stderr,
        )
        return 1

    all_rows = []
    for path in paths:
        ticker = path.stem.replace("_", ".")
        rows = evaluate_ticker(pd.read_parquet(path))
        for r in rows:
            r["ticker"] = ticker
        all_rows.extend(rows)
        logger.info(f"{ticker}: {len(rows) // 3} refit points")

    frame = pd.DataFrame(all_rows)
    summary = frame.groupby("model").agg(
        qlike_1d=("qlike_1d", "mean"),
        qlike_20d=("qlike_20d", "mean"),
        rmse_1d=("rmse_1d_sq", lambda s: float(np.sqrt(s.mean()))),
        rmse_20d=("rmse_20d_sq", lambda s: float(np.sqrt(s.mean()))),
        n=("qlike_1d", "size"),
    )
    print(f"\nuniverse: {frame['ticker'].nunique()} tickers, "
          f"{int(summary['n'].iloc[0])} forecast points per model")
    print("\n== QLIKE / RMSE (lower is better) ==")
    print(summary.round(5).to_string())
    winner_1d = summary["qlike_1d"].idxmin()
    winner_20d = summary["qlike_20d"].idxmin()
    print(f"\nQLIKE winner: 1d={winner_1d}, 20d={winner_20d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
