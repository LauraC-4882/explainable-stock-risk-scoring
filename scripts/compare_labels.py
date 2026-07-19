"""[G2] Label-definition shootout: fixed vs vol_scaled vs triple_barrier.

Same tickers, same feature set, same TimeSeriesSplit folds — the ONLY moving
part is the label definition, so any metric difference is attributable to it
(the [G3] feature-surface change is deliberately a separate experiment).

Data comes from the disk cache under data/experiments/ (populated by the
harvester / a previous run) so this script never depends on Yahoo being
un-throttled at run time. Usage:

    python scripts/compare_labels.py                # all three modes
    python scripts/compare_labels.py --sweep-only   # just the k sweep table
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402

from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.features.technical import TechnicalFeatures  # noqa: E402
from stock_risk.models.evaluation import walk_forward_evaluate  # noqa: E402
from stock_risk.models.feature_sets import build_labels  # noqa: E402

ROOT = Path(__file__).parent.parent
OHLCV_CACHE = ROOT / "data/experiments/ohlcv"
FEATURE_CACHE = ROOT / "data/experiments/features"

K_SWEEP = [1.0, 1.25, 1.5, 1.75, 2.0]
TARGET_RATE = (0.10, 0.15)  # aim the vol-scaled base rate into this band


def load_feature_frames(refresh: bool = False) -> dict[str, pd.DataFrame]:
    """OHLCV cache -> engineered feature frames, themselves disk-cached
    (RiskMetrics' python-level rolling applies are the slow part)."""
    FEATURE_CACHE.mkdir(parents=True, exist_ok=True)
    pre, tech, risk = DataPreprocessor(), TechnicalFeatures(), RiskMetrics()
    out: dict[str, pd.DataFrame] = {}
    for raw_path in sorted(OHLCV_CACHE.glob("*.parquet")):
        ticker = raw_path.stem.replace("_", ".")
        feat_path = FEATURE_CACHE / raw_path.name
        if feat_path.exists() and not refresh:
            out[ticker] = pd.read_parquet(feat_path)
            continue
        df = risk.compute(tech.compute(pre.process(pd.read_parquet(raw_path))))
        df.to_parquet(feat_path)
        out[ticker] = df
        logger.info(f"engineered {ticker}: {len(df)} rows")
    return out


def base_rate(dfs: dict[str, pd.DataFrame], mode: str, k: float) -> float:
    labels = pd.concat([build_labels(df, label_mode=mode, k=k) for df in dfs.values()])
    return float(labels.mean())


def k_sweep(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for k in K_SWEEP:
        rows.append({
            "k": k,
            "vol_scaled_rate": base_rate(dfs, "vol_scaled", k),
            "triple_barrier_rate": base_rate(dfs, "triple_barrier", k),
        })
    return pd.DataFrame(rows).set_index("k")


def pick_k(sweep: pd.DataFrame, col: str) -> float:
    lo, hi = TARGET_RATE
    in_band = sweep[(sweep[col] >= lo) & (sweep[col] <= hi)]
    if 1.5 in in_band.index:
        return 1.5
    if not in_band.empty:
        return float(in_band.index[0])
    # nothing in band — nearest to band midpoint, reported honestly
    mid = (lo + hi) / 2
    return float((sweep[col] - mid).abs().idxmin())


def fold_rates(result: pd.DataFrame) -> list[float]:
    return [round(p / n, 3) for p, n in zip(result["n_test_positive"], result["n_test"])]


def main() -> int:
    parser = argparse.ArgumentParser(description="[G2] label-definition comparison")
    parser.add_argument("--sweep-only", action="store_true")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--refresh-features", action="store_true")
    args = parser.parse_args()

    if not any(OHLCV_CACHE.glob("*.parquet")):
        print(f"No cached OHLCV under {OHLCV_CACHE} — run the harvester first", file=sys.stderr)
        return 1

    dfs = load_feature_frames(refresh=args.refresh_features)
    print(f"\nuniverse: {len(dfs)} tickers, {sum(len(d) for d in dfs.values())} rows")

    sweep = k_sweep(dfs)
    print("\n== k sweep (overall base rate) ==")
    print(sweep.round(4).to_string())
    k_vs = pick_k(sweep, "vol_scaled_rate")
    k_tb = pick_k(sweep, "triple_barrier_rate")
    print(f"chosen k: vol_scaled={k_vs}, triple_barrier={k_tb} (target band {TARGET_RATE})")
    if args.sweep_only:
        return 0

    summary_rows = []
    for mode, k in [("fixed", 1.5), ("vol_scaled", k_vs), ("triple_barrier", k_tb)]:
        k_note = f" (k={k})" if mode != "fixed" else ""
        print(f"\n== walk-forward: label_mode={mode}{k_note} ==")
        result = walk_forward_evaluate(dfs, n_splits=args.n_splits, label_mode=mode, k=k)
        rates = fold_rates(result)
        summary_rows.append({
            "label_mode": mode,
            "k": k if mode != "fixed" else None,
            "roc_auc": result["roc_auc"].mean(),
            "pr_auc": result["pr_auc"].mean(),
            "brier_raw": result["brier_raw"].mean(),
            "brier_cal": result["brier_calibrated"].mean()
            if "brier_calibrated" in result else float("nan"),
            "recall": result["recall"].mean(),
            "fold_base_rates": rates,
            "rate_spread": round(max(rates) - min(rates), 3),
        })

    summary = pd.DataFrame(summary_rows).set_index("label_mode")
    print("\n== COMPARISON (same features, same folds; only the label changed) ==")
    print(summary.round(4).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
