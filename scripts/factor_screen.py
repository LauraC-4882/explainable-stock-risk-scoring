"""[G3] Single-factor IC screen with Benjamini-Hochberg FDR control.

For every alpha_grid factor: per-date cross-sectional Spearman IC against the
continuous forward outcome (20-day forward max close drawdown), then a
multiple-testing-corrected keep/drop decision. Without this screen the
operator-by-window grid is an overfitting amplifier — ~90 columns tested
against one outcome will produce lucky correlations by construction, and BH
FDR (alpha=0.05) is the standard discipline (ML4T ch. 7) for throwing those
out before they reach the model.

Statistical honesty note: daily ICs computed against a 20-day forward
outcome are ~20-fold serially correlated (overlapping windows), which
inflates a naive t-statistic. The keep/drop test therefore runs on ICs
subsampled every `horizon` days (non-overlapping outcomes, ~independent
observations); the daily-IC mean is still reported for reference.

Outputs scripts/factor_screen_results.csv plus a printed summary and the
python list of survivors (pasted into the [G3] experiment / feature set).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402
from scipy import stats  # noqa: E402

from stock_risk.features.alpha_grid import ALPHA_GRID_COLS, AlphaGridFeatures  # noqa: E402

ROOT = Path(__file__).parent.parent
OHLCV_CACHE = ROOT / "data/experiments/ohlcv"
ALPHA_CACHE = ROOT / "data/experiments/alpha"
RESULTS_CSV = Path(__file__).parent / "factor_screen_results.csv"

HORIZON = 20
MIN_NAMES_PER_DATE = 10
FDR_ALPHA = 0.05


def load_alpha_frames() -> dict[str, pd.DataFrame]:
    ALPHA_CACHE.mkdir(parents=True, exist_ok=True)
    grid = AlphaGridFeatures()
    out: dict[str, pd.DataFrame] = {}
    for raw_path in sorted(OHLCV_CACHE.glob("*.parquet")):
        ticker = raw_path.stem.replace("_", ".")
        cache_path = ALPHA_CACHE / raw_path.name
        if cache_path.exists():
            out[ticker] = pd.read_parquet(cache_path)
            continue
        raw = pd.read_parquet(raw_path)
        df = grid.compute(raw)
        # Continuous forward outcome: forward 20d max close drawdown (negative).
        fwd_min = df["close"].shift(-HORIZON).rolling(HORIZON).min()
        df["fwd_drawdown"] = fwd_min / df["close"] - 1
        df.to_parquet(cache_path)
        out[ticker] = df
        logger.info(f"alpha features {ticker}: {len(df)} rows")
    return out


def daily_cross_sectional_ic(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """dates x factors matrix of cross-sectional Spearman ICs."""
    long = pd.concat(
        {t: df[ALPHA_GRID_COLS + ["fwd_drawdown"]] for t, df in frames.items()},
        names=["ticker", "date"],
    ).swaplevel().sort_index()

    ics: dict[pd.Timestamp, pd.Series] = {}
    for date, group in long.groupby(level=0):
        g = group.dropna(subset=["fwd_drawdown"])
        if len(g) < MIN_NAMES_PER_DATE:
            continue
        ranks = g.rank()  # Spearman = Pearson on ranks
        ics[date] = ranks[ALPHA_GRID_COLS].corrwith(ranks["fwd_drawdown"])
    return pd.DataFrame(ics).T.sort_index()


def bh_fdr(pvals: pd.Series, alpha: float = FDR_ALPHA) -> pd.Series:
    """Benjamini-Hochberg: keep everything up to the largest rank i with
    p_(i) <= (i/m) * alpha."""
    p = pvals.dropna().sort_values()
    m = len(p)
    thresholds = alpha * np.arange(1, m + 1) / m
    passed = p.to_numpy() <= thresholds
    cutoff_rank = int(np.max(np.nonzero(passed)[0]) + 1) if passed.any() else 0
    keep = pd.Series(False, index=pvals.index)
    keep.loc[p.index[:cutoff_rank]] = True
    return keep


def main() -> int:
    if not any(OHLCV_CACHE.glob("*.parquet")):
        print(f"No cached OHLCV under {OHLCV_CACHE} — run the harvester first", file=sys.stderr)
        return 1

    frames = load_alpha_frames()
    print(f"universe: {len(frames)} tickers")
    ic = daily_cross_sectional_ic(frames)
    print(f"IC matrix: {ic.shape[0]} dates x {ic.shape[1]} factors")

    # Non-overlapping subsample for the significance test (see module docstring)
    ic_nonoverlap = ic.iloc[::HORIZON]

    rows = []
    for factor in ALPHA_GRID_COLS:
        series = ic_nonoverlap[factor].dropna()
        if len(series) < 10:
            rows.append({"factor": factor, "n_obs": len(series), "p_value": np.nan})
            continue
        t_stat, p_value = stats.ttest_1samp(series, 0.0)
        rows.append({
            "factor": factor,
            "mean_ic_daily": ic[factor].mean(),
            "mean_ic_nonoverlap": series.mean(),
            "t_stat": t_stat,
            "p_value": p_value,
            "n_obs": len(series),
        })

    table = pd.DataFrame(rows).set_index("factor")
    table["keep"] = bh_fdr(table["p_value"])
    table = table.sort_values("p_value")
    table.to_csv(RESULTS_CSV)

    kept = table[table["keep"]].index.tolist()
    print(f"\n== screen result: kept {len(kept)} / {len(ALPHA_GRID_COLS)} "
          f"(BH FDR alpha={FDR_ALPHA}, non-overlapping t-test) ==")
    print(table.round(4).to_string())
    print(f"\nresults written to {RESULTS_CSV}")
    print("\nkept factors (python list):")
    print("SCREENED_ALPHA_COLS = [")
    for f in kept:
        print(f'    "{f}",')
    print("]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
