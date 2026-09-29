"""Every number in docs_internal/VAR_ORDERSTAT_CASE_STUDY.md, regenerated.

Two tables, one sample, no simulation:

1. **The tail suite, per ticker.** `scripts/validate_tail.py --json` records the
   pooled block only, so the per-ticker Kupiec / independence / Z2 results the
   case study quotes have no committed source. This reuses that script's
   manifest loader and `_prepare` unchanged - same sample, same one-day shift,
   same log-return convention - and reports each ticker alongside the pooled
   run, with a check that the per-ticker breach counts sum to the pooled one.

2. **Wash-out under own-history percentile ranking.** The 21-day scoring
   feature `var_95_21d` is the second order statistic of its window (pandas'
   default plotting position lands exactly on index 1 at n=21; asserted below,
   not assumed). The scorer never shows that value: it ranks it against the
   stock's own history. The question is whether that ranking absorbs the
   estimator's bias. Both the feature and a 21-day Weibull comparator are
   ranked with the scorer's exact rule - `scipy.stats.percentileofscore`,
   `kind="mean"`, direction -1, at least `_MIN_HISTORY` observations, the
   current value included in its own history - and the rank gap is reported
   by tercile of 21-day realised volatility.

   Tercile cutoffs are **per ticker** (each ticker's own days split into
   thirds), which is the definition the document carries. Pooled cutoffs (one
   split across all tickers' days) are printed alongside because the two
   disagree in the high tercile and the document says so.

Deterministic: the sample is the manifest, the only random draw is the Z2
bootstrap's fixed seed inside `validation/tail_tests.py`, and no wall clock is
read. Same snapshots => byte-identical output.

    python scripts/var_orderstat_case_study.py
    python scripts/var_orderstat_case_study.py --json out.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.scoring.risk_categories import _MIN_HISTORY  # noqa: E402
from stock_risk.validation import run_full_suite  # noqa: E402

SNAPSHOT_DIR = Path("snapshots")
ALPHA = 0.05
SIGNIFICANCE = 0.05
FEATURE_WINDOW = 21
TERCILES = ("low", "mid", "high")


def _validate_tail_module():
    """The suite's own loader and preparation step, not a re-derivation.

    Loaded from the file because `scripts/` is not a package. Re-implementing
    `_prepare` here would be a second expression of "the VaR the product grades"
    that could drift from the first - the exact failure 93b5871 removed from the
    backtest endpoint.
    """
    path = Path(__file__).parent / "validate_tail.py"
    spec = importlib.util.spec_from_file_location("_validate_tail", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- 1. the tail suite, per ticker --------------------------------------------


def _result_block(result) -> dict:
    return {
        "statistic": result.statistic,
        "p_value": result.p_value,
        "reject": result.reject,
        "detail": result.detail,
    }


def tail_suite(frames: dict[str, pd.DataFrame], vt) -> dict:
    per_ticker, pooled_parts = {}, ([], [], [])
    for ticker, raw in frames.items():
        prepared = vt._prepare(raw)
        vt._assert_conventions_agree(prepared, ticker)
        suite = run_full_suite(prepared["return"], prepared["var"], prepared["es"], alpha=ALPHA)
        per_ticker[ticker] = {
            "n": int(len(prepared)),
            "tests": {name: _result_block(r) for name, r in suite["tests"].items()},
            "clustering": suite["clustering"],
        }
        for part, column in zip(pooled_parts, ("return", "var", "es")):
            part.append(prepared[column])

    suite = run_full_suite(*(pd.concat(p) for p in pooled_parts), alpha=ALPHA)
    pooled = {
        "n": int(sum(len(p) for p in pooled_parts[0])),
        "tests": {name: _result_block(r) for name, r in suite["tests"].items()},
        "clustering": suite["clustering"],
    }

    breach_sum = sum(t["tests"]["kupiec_pof"]["detail"]["breaches"] for t in per_ticker.values())
    pooled_breaches = pooled["tests"]["kupiec_pof"]["detail"]["breaches"]
    if breach_sum != pooled_breaches:
        raise AssertionError(
            f"per-ticker breaches sum to {breach_sum}, pooled run counted {pooled_breaches}"
        )

    m = len(per_ticker)
    return {
        "per_ticker": per_ticker,
        "pooled": pooled,
        "multiplicity": {
            "tests_per_family": m,
            "nominal": SIGNIFICANCE,
            "bonferroni": SIGNIFICANCE / m,
            "p_at_least_one_false_rejection": 1 - (1 - SIGNIFICANCE) ** m,
        },
    }


# -- 2. wash-out under own-history percentile ranking -------------------------


def expanding_rank(series: pd.Series) -> pd.Series:
    """The scorer's percentile, replayed day by day.

    `risk_categories._historical_percentile` ranks the latest value within the
    whole loaded history (which includes that value), direction -1 for the tail
    metrics, and returns nothing under `_MIN_HISTORY` observations. Replaying
    that on an expanding window is what the scorer would have shown on each
    day, given the history it had.
    """
    values = series.to_numpy()
    out = np.full(len(values), np.nan)
    history: list[float] = []
    for i, value in enumerate(values):
        if np.isnan(value):
            continue
        history.append(value)
        if len(history) < _MIN_HISTORY:
            continue
        out[i] = stats.percentileofscore(-np.asarray(history), -value, kind="mean") / 100.0
    return pd.Series(out, index=series.index)


def _tercile_summary(frame: pd.DataFrame, column: str) -> dict:
    summary = {}
    for label, group in frame.groupby(column, observed=True):
        summary[str(label)] = {
            "days": int(len(group)),
            "mean_ratio": float(group["ratio"].mean()),
            "mean_abs_rank_gap": float(group["gap"].mean()),
            "spearman_of_ranks": float(
                stats.spearmanr(group["rank_feature"], group["rank_comparator"]).correlation
            ),
            "mean_volatility": float(group["volatility"].mean()),
        }
    return summary


def washout(frames: dict[str, pd.DataFrame]) -> dict:
    per_ticker, parts = {}, []
    for ticker, raw in frames.items():
        df = RiskMetrics().compute(DataPreprocessor().process(raw))
        r = df["log_return"]
        feature = df["var_95_21d"]

        # The premise, checked: the feature IS the second smallest of its window.
        second = r.rolling(FEATURE_WINDOW).apply(lambda x: np.sort(x)[1], raw=True)
        present = feature.notna()
        if not np.allclose(feature[present], second[present]):
            raise AssertionError(f"{ticker}: var_95_21d is not the 2nd order statistic")

        comparator = r.rolling(FEATURE_WINDOW).apply(
            lambda x: np.quantile(x, ALPHA, method="weibull"), raw=True
        )
        frame = pd.DataFrame(
            {
                "feature": feature,
                "comparator": comparator,
                "volatility": r.rolling(FEATURE_WINDOW).std(),
                "reported": df["var_95_100d"],
                "rank_feature": expanding_rank(feature),
                "rank_comparator": expanding_rank(comparator),
            }
        ).dropna()
        frame["ratio"] = frame["feature"] / frame["comparator"]
        frame["gap"] = (frame["rank_feature"] - frame["rank_comparator"]).abs()
        frame["tercile_own"] = pd.qcut(frame["volatility"], 3, labels=TERCILES)
        frame["ticker"] = ticker
        parts.append(frame)

        per_ticker[ticker] = {
            "days": int(len(frame)),
            "spearman_raw": float(
                stats.spearmanr(frame["feature"], frame["comparator"]).correlation
            ),
            "spearman_of_ranks": float(
                stats.spearmanr(frame["rank_feature"], frame["rank_comparator"]).correlation
            ),
            "spearman_feature_vs_reported": float(
                stats.spearmanr(frame["feature"], frame["reported"]).correlation
            ),
            "spearman_comparator_vs_reported": float(
                stats.spearmanr(frame["comparator"], frame["reported"]).correlation
            ),
            "mean_ratio": float(frame["ratio"].mean()),
            "mean_abs_rank_gap": float(frame["gap"].mean()),
        }

    pooled = pd.concat(parts)
    pooled["tercile_pooled"] = pd.qcut(pooled["volatility"], 3, labels=TERCILES)
    return {
        "definition": {
            "feature": "var_95_21d: rolling(21).quantile(0.05), pandas default position "
            "= 2nd order statistic of 21",
            "comparator": "np.quantile(window, 0.05, method='weibull') over the same 21 days",
            "ranking": "scorer's rule replayed on an expanding window: percentileofscore, "
            f"kind=mean, direction -1, >= {_MIN_HISTORY} observations, current value included",
            "tercile_variable": "rolling 21-day std of log_return (same window as the feature)",
            "tercile_cutoffs": "tercile_own = per ticker (the document's definition); "
            "tercile_pooled = one split across all tickers' days",
        },
        "per_ticker": per_ticker,
        "pooled_days": int(len(pooled)),
        "overall": {
            "mean_ratio": float(pooled["ratio"].mean()),
            "mean_abs_rank_gap": float(pooled["gap"].mean()),
            "spearman_of_ranks": float(
                stats.spearmanr(pooled["rank_feature"], pooled["rank_comparator"]).correlation
            ),
        },
        "tercile_own": _tercile_summary(pooled, "tercile_own"),
        "tercile_pooled": _tercile_summary(pooled, "tercile_pooled"),
    }


# -- the markdown the document carries ----------------------------------------


def _p(value: float) -> str:
    return f"{value:.4f}"


def render(report: dict) -> str:
    """The exact tables in the case study. The document is checked against this
    output byte for byte, so nothing here may depend on the machine."""
    lines = []
    tail = report["tail_suite"]
    lines.append(
        "| ticker | n | breaches | rate | Kupiec p | independence p | Z2 | severity ratio |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    rows = list(tail["per_ticker"].items()) + [("pooled", tail["pooled"])]
    for name, block in rows:
        tests = block["tests"]
        kupiec = tests["kupiec_pof"]
        z2 = tests["acerbi_szekely_z2"]
        severity = z2["detail"].get("severity_ratio")
        lines.append(
            f"| {name} | {block['n']} | {kupiec['detail']['breaches']} | "
            f"{kupiec['detail']['observed_rate'] * 100:.2f}% | {_p(kupiec['p_value'])} | "
            f"{_p(tests['christoffersen_independence']['p_value'])} | "
            f"{z2['statistic']:+.3f} | {severity:.3f} |"
        )
    mult = tail["multiplicity"]
    lines.append("")
    lines.append(
        f"Six tickers, so six tests per family: Bonferroni threshold "
        f"{mult['bonferroni']:.5f}; probability of at least one rejection at "
        f"{mult['nominal']:.2f} under six true nulls "
        f"{mult['p_at_least_one_false_rejection'] * 100:.1f}%."
    )

    wash = report["washout"]
    schemes = (("tercile_own", "per-ticker cutoffs"), ("tercile_pooled", "pooled cutoffs"))
    for key, heading in schemes:
        lines.append("")
        lines.append(
            f"| tercile of 21-day volatility ({heading}) | days | mean ratio | "
            "mean abs rank gap | Spearman of ranks |"
        )
        lines.append("|---|---|---|---|---|")
        for label in TERCILES:
            cell = wash[key][label]
            lines.append(
                f"| {label} | {cell['days']} | {cell['mean_ratio']:.3f} | "
                f"{cell['mean_abs_rank_gap']:.3f} | {cell['spearman_of_ranks']:.3f} |"
            )
    lines.append("")
    lines.append(
        "| ticker | days | Spearman, raw series | Spearman, ranks | "
        "feature vs reported VaR | comparator vs reported VaR |"
    )
    lines.append("|---|---|---|---|---|---|")
    for name, cell in wash["per_ticker"].items():
        lines.append(
            f"| {name} | {cell['days']} | {cell['spearman_raw']:.3f} | "
            f"{cell['spearman_of_ranks']:.3f} | {cell['spearman_feature_vs_reported']:.3f} | "
            f"{cell['spearman_comparator_vs_reported']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def build_report(snapshot_dir: Path) -> dict:
    vt = _validate_tail_module()
    frames = vt._load_snapshots(snapshot_dir)
    return {
        "sample": list(frames),
        "tail_suite": tail_suite(frames, vt),
        "washout": washout(frames),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    report = build_report(args.snapshot_dir)
    sys.stdout.write(render(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
