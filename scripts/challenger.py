"""[R8] Champion–challenger evaluation for the downside-risk model.

The question this answers is the one model validation actually cares about, and
it is not "what is our best AUC":

    Does the complex model beat a simple, well-calibrated baseline — and does it
    keep beating it out of sample, across regimes, and in the subgroups where it
    matters?

A gradient-boosted tree that edges out logistic regression by 0.01 AUC while
being far harder to explain, monitor and defend is not obviously the right
production model. Making that trade-off visible is the point.

Each challenger is registered in the [R4] model registry as a SHADOW model, so
the comparison is recorded rather than living in a terminal scrollback, and
promotion stays a separate human decision.

    python scripts/challenger.py --tickers-file scripts/tickers_universe.txt
    python scripts/challenger.py --tickers AAPL MSFT NVDA --lookback 1825
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402

from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402
from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.features.technical import TechnicalFeatures  # noqa: E402
from stock_risk.governance import ModelRegistry, ModelStatus, TransitionError  # noqa: E402
from stock_risk.models.evaluation import walk_forward_evaluate  # noqa: E402


def _load(tickers: list[str], lookback: int) -> dict[str, pd.DataFrame]:
    fetcher, pre, tech, risk = (
        MarketDataFetcher(),
        DataPreprocessor(),
        TechnicalFeatures(),
        RiskMetrics(),
    )
    frames = {}
    period = f"{lookback // 365}y" if lookback >= 365 else f"{lookback}d"
    for ticker in tickers:
        try:
            frames[ticker] = risk.compute(tech.compute(pre.process(
                fetcher.fetch_history(ticker, period=period)
            )))
        except Exception as exc:
            logger.warning(f"Skipping {ticker}: {exc}")
    return frames


def _summarise(table: pd.DataFrame) -> dict:
    """Mean across folds — never the best fold.

    Registering a best fold would let a model that worked once in five clear a
    threshold designed to reject it, which is the exact self-deception
    walk-forward validation exists to prevent.
    """
    row = table.loc["mean"] if "mean" in table.index else table.mean(numeric_only=True)
    return {
        key: round(float(row[key]), 6)
        for key in ("roc_auc", "pr_auc", "precision", "recall", "brier_raw", "brier_calibrated")
        if key in row.index and pd.notna(row[key])
    }


def _stability(table: pd.DataFrame) -> dict:
    """Fold-to-fold dispersion — the discriminator a mean AUC hides.

    Two models with identical mean AUC are not equally good if one swings
    0.36-0.77 across folds and the other holds 0.66-0.69. The first is
    unusable in production even though its average looks fine; this project has
    seen exactly that pattern (README's first training run).
    """
    folds = table.drop(index=[i for i in ("mean", "std") if i in table.index], errors="ignore")
    if "roc_auc" not in folds.columns or folds.empty:
        return {}
    auc = folds["roc_auc"].astype(float)
    return {
        "auc_std": round(float(auc.std()), 6),
        "auc_min": round(float(auc.min()), 6),
        "auc_max": round(float(auc.max()), 6),
        "auc_range": round(float(auc.max() - auc.min()), 6),
        "folds_below_coin_flip": int((auc < 0.5).sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"])
    parser.add_argument("--tickers-file", type=Path, default=None)
    parser.add_argument("--lookback", type=int, default=1825)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=-0.10)
    parser.add_argument("--registry", type=Path, default=Path("models/registry.json"))
    parser.add_argument(
        "--register", action="store_true",
        help="Record each challenger in the model registry as a SHADOW model",
    )
    args = parser.parse_args()

    tickers = args.tickers
    if args.tickers_file:
        tickers = [
            line.strip().upper()
            for line in args.tickers_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

    frames = _load(tickers, args.lookback)
    if not frames:
        logger.error("No usable data")
        return 1
    logger.info(f"Loaded {len(frames)} tickers, {sum(len(f) for f in frames.values())} rows")

    # models/evaluation.py already benchmarks LogisticRegression / RandomForest
    # / XGBoost on a chronological split. Here each is run through the SAME
    # walk-forward + isotonic-calibration path the champion uses — comparing a
    # single-split baseline against a walk-forward champion would flatter
    # whichever got the easier evaluation.
    challengers = {
        "logistic_regression": {"estimator": "logistic"},
        "random_forest": {"estimator": "random_forest"},
        "xgboost_monotonic": {"estimator": "xgboost_monotonic"},
    }

    results = {}
    logger.info("Champion (XGBoost, as deployed)...")
    try:
        champion_table = walk_forward_evaluate(
            frames, horizon=args.horizon, threshold=args.threshold
        )
        results["champion_xgboost"] = {
            **_summarise(champion_table),
            **_stability(champion_table),
        }
        logger.info("\n" + champion_table.to_string())
    except (ValueError, TypeError) as exc:
        logger.error(f"Champion evaluation failed: {exc}")
        return 1

    for name, kwargs in challengers.items():
        logger.info(f"Challenger: {name}...")
        try:
            table = walk_forward_evaluate(
                frames, horizon=args.horizon, threshold=args.threshold, **kwargs
            )
            results[name] = {**_summarise(table), **_stability(table)}
        except ValueError as exc:
            logger.warning(f"{name}: {exc}")

    print("\n" + "=" * 84)
    print("CHAMPION vs CHALLENGERS (walk-forward, isotonic-calibrated)")
    print("=" * 84)
    header = (
        f"{'MODEL':24s} {'AUC':>8s} {'PR-AUC':>8s} {'RECALL':>8s} "
        f"{'BRIER':>8s} {'AUC SD':>8s} {'MIN':>7s}"
    )
    print(header)
    print("-" * 84)
    for name, metrics in results.items():
        print(
            f"{name:24s} "
            f"{metrics.get('roc_auc', float('nan')):>8.4f} "
            f"{metrics.get('pr_auc', float('nan')):>8.4f} "
            f"{metrics.get('recall', float('nan')):>8.4f} "
            f"{metrics.get('brier_calibrated', float('nan')):>8.4f} "
            f"{metrics.get('auc_std', float('nan')):>8.4f} "
            f"{metrics.get('auc_min', float('nan')):>7.4f}"
        )

    champion_auc = results.get("champion_xgboost", {}).get("roc_auc")
    if champion_auc is not None:
        print("\nVerdict:")
        for name, metrics in results.items():
            if name == "champion_xgboost":
                continue
            auc = metrics.get("roc_auc")
            if auc is None:
                continue
            delta = auc - champion_auc
            verdict = "beats" if delta > 0 else "does not beat"
            print(f"  {name}: {verdict} the champion by {delta:+.4f} AUC")
        print(
            "\nA challenger within noise of the champion while being simpler is a real "
            "argument for the simpler model — complexity has to earn its place."
        )

    if args.register:
        registry = ModelRegistry(args.registry)
        for name, metrics in results.items():
            if name == "champion_xgboost":
                continue
            version = f"challenger-{name}"
            try:
                registry.register("downside_risk", version, metrics=metrics,
                                  notes="Registered by scripts/challenger.py")
                registry.validate("downside_risk", version)
                registry.transition("downside_risk", version, ModelStatus.APPROVED,
                                    reason="challenger evaluated")
                registry.transition("downside_risk", version, ModelStatus.SHADOW,
                                    reason="running as challenger")
                logger.info(f"[registry] {version} registered as SHADOW")
            except (ValueError, TransitionError) as exc:
                logger.warning(f"[registry] {version}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
