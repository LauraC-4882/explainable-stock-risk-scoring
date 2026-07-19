"""[G3] Feature-surface shootout: the hand-picked 19 columns vs 19 + the
IC/FDR-screened alpha-grid factors — same label definition, same folds, so
the only moving part is the feature surface ([G2] owns the label variable).

Reads the screen verdict from scripts/factor_screen_results.csv (run
scripts/factor_screen.py first) and the cached engineered frames from the
[G2] experiment cache.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402

from stock_risk.features.alpha_grid import AlphaGridFeatures  # noqa: E402
from stock_risk.models.evaluation import walk_forward_evaluate  # noqa: E402

ROOT = Path(__file__).parent.parent
FEATURE_CACHE = ROOT / "data/experiments/features"
RESULTS_CSV = Path(__file__).parent / "factor_screen_results.csv"


def load_frames_with_alpha() -> dict[str, pd.DataFrame]:
    grid = AlphaGridFeatures()
    out: dict[str, pd.DataFrame] = {}
    for path in sorted(FEATURE_CACHE.glob("*.parquet")):
        df = pd.read_parquet(path)
        out[path.stem.replace("_", ".")] = grid.compute(df)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="[G3] feature-surface comparison")
    parser.add_argument("--label-mode", default="vol_scaled",
                        choices=["fixed", "vol_scaled", "triple_barrier"])
    parser.add_argument("--k", type=float, default=1.5)
    parser.add_argument("--n-splits", type=int, default=5)
    args = parser.parse_args()

    if not RESULTS_CSV.exists():
        print("Run scripts/factor_screen.py first (no screen results found)", file=sys.stderr)
        return 1
    screen = pd.read_csv(RESULTS_CSV, index_col="factor")
    kept = screen[screen["keep"]].index.tolist()
    print(f"screened factors: {len(kept)} kept of {len(screen)}")

    frames = load_frames_with_alpha()
    print(f"universe: {len(frames)} tickers | label={args.label_mode} k={args.k}")

    rows = []
    for name, extra in [("baseline_19", None), (f"19_plus_{len(kept)}_alpha", kept)]:
        print(f"\n== walk-forward: features={name} ==")
        result = walk_forward_evaluate(
            frames, n_splits=args.n_splits,
            label_mode=args.label_mode, k=args.k,
            extra_feature_cols=extra,
        )
        rows.append({
            "features": name,
            "roc_auc": result["roc_auc"].mean(),
            "pr_auc": result["pr_auc"].mean(),
            "recall": result["recall"].mean(),
            "precision": result["precision"].mean(),
            "brier_cal": result["brier_calibrated"].mean()
            if "brier_calibrated" in result else float("nan"),
        })

    summary = pd.DataFrame(rows).set_index("features")
    print("\n== COMPARISON (same label, same folds; only the feature surface changed) ==")
    print(summary.round(4).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
