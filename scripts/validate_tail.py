"""[R6] Run the tail-risk backtest suite against real price history.

Extends scripts/validate_score.py's Kupiec POF check with the three tests it
can't perform: breach independence, joint conditional coverage, and an Expected
Shortfall backtest.

Reads the committed parquet snapshots by default, so it runs offline and gives
the same answer on every machine — the numbers quoted in the README have to be
reproducible, and a live fetch would silently drift as prices are restated.

    python scripts/validate_tail.py                    # snapshots
    python scripts/validate_tail.py --live AAPL MSFT   # live fetch instead
    python scripts/validate_tail.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402

from stock_risk.data.preprocessor import DataPreprocessor  # noqa: E402
from stock_risk.features.risk_metrics import RiskMetrics  # noqa: E402
from stock_risk.validation import run_full_suite  # noqa: E402

SNAPSHOT_DIR = Path("snapshots")
MANIFEST_NAME = "validation_manifest.txt"


def _read_manifest(snapshot_dir: Path) -> list[str]:
    """The declared sample set, in manifest order.

    Deliberately not a directory listing. The sample used to come from
    `snapshot_dir.glob("*.parquet")`, so it was whatever the machine happened to
    have: 6 files in a fresh checkout, 101 on a box that had run the
    cross-sectional builder. The published tail figures were therefore not
    reproducible across machines, and nothing in the output said which
    population had been measured.

    A missing manifest is an error rather than a fallback to globbing. A silent
    fallback would restore exactly the behaviour this replaces, and would do it
    at the moment someone is least likely to notice.
    """
    manifest = snapshot_dir / MANIFEST_NAME
    if not manifest.exists():
        raise FileNotFoundError(
            f"No sample manifest at {manifest}. It declares which snapshots the "
            "tail validation runs against; without it the sample would be "
            "whatever happens to be on this disk, which is what this file "
            "exists to prevent. Restore it from version control."
        )
    names = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            names.append(entry)
    return names


def _load_snapshots(snapshot_dir: Path) -> dict[str, pd.DataFrame]:
    """Load exactly the manifest's files — no more, no fewer.

    Two asymmetric rules, and the asymmetry is the point:

    * a manifest entry with no file on disk is fatal. A shrinking sample must
      never present itself as a passing run, which is what skipping would do.
    * a parquet on disk that the manifest does not list is skipped, and said
      out loud on stderr. Failing there would make the script unusable on any
      machine that has ever cached extra snapshots, but folding them in
      silently is the original bug.
    """
    declared = _read_manifest(snapshot_dir)

    missing = [name for name in declared if not (snapshot_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} file(s) in {MANIFEST_NAME} are not on disk: "
            f"{', '.join(missing)}. The declared sample set is incomplete, so "
            "any result would describe a different population than the manifest "
            "claims. Restore the snapshots or update the manifest deliberately."
        )

    on_disk = {p.name for p in snapshot_dir.glob("*.parquet")}
    ignored = sorted(on_disk - set(declared))
    if ignored:
        print(
            f"IGNORED (not in manifest): {len(ignored)} files — {', '.join(ignored)}",
            file=sys.stderr,
        )

    print(f"sample set: {len(declared)} files from manifest")

    frames = {}
    for name in declared:
        path = snapshot_dir / name
        ticker = path.stem.replace("_2y_1d", "")
        try:
            frames[ticker] = pd.read_parquet(path)
        except Exception as exc:
            # An unreadable file in the DECLARED set is not a skip either: the
            # sample would silently shrink. Re-raised with the filename so the
            # cause is obvious.
            raise RuntimeError(f"Declared sample file {name} could not be read: {exc}") from exc
    return frames


def _load_live(tickers: list[str]) -> dict[str, pd.DataFrame]:
    from stock_risk.data.fetcher import MarketDataFetcher

    fetcher = MarketDataFetcher()
    frames = {}
    for ticker in tickers:
        try:
            frames[ticker] = fetcher.fetch_history(ticker, period="2y")
        except Exception as exc:
            logger.warning(f"Skipping {ticker}: {exc}")
    return frames


def _prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Compute the risk metrics whose tail calibration is under test.

    Grades `var_95_100d`/`cvar_95_100d` — the pair the scorecard reports — NOT
    the 21-day `var_95_21d` features this used to read. The 21-day series is a
    second-order-statistic estimator that breaches 2/22 = 9.09% by construction
    at any tail thickness (see the comment block in features/risk_metrics.py);
    testing it against a 5% target measured the estimator's window, not the
    market's tails, and every ticker failed for the same arithmetic reason.

    Note the one-day shift below: the VaR on day t is computed from returns up
    to and including day t, so comparing it against day t's OWN return would be
    scoring a forecast against data it already saw. The test has to ask whether
    *yesterday's* VaR contained *today's* loss.
    """
    df = RiskMetrics().compute(DataPreprocessor().process(raw))
    out = pd.DataFrame(index=df.index)
    out["return"] = df["pct_return"]
    out["var"] = df["var_95_100d"].shift(1)
    out["es"] = df["cvar_95_100d"].shift(1)
    return out.dropna()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--live", nargs="*", default=None, help="Fetch these tickers instead")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", type=Path, default=None, help="Write full results here")
    args = parser.parse_args()

    frames = _load_live(args.live) if args.live else _load_snapshots(args.snapshot_dir)
    if not frames:
        logger.error("No data loaded — nothing to validate")
        return 1

    logger.info(f"Loaded {len(frames)} tickers")

    pooled_returns, pooled_var, pooled_es = [], [], []
    per_ticker = {}

    for ticker, raw in frames.items():
        try:
            prepared = _prepare(raw)
        except Exception as exc:
            logger.warning(f"Skipping {ticker}: {exc}")
            continue
        if len(prepared) < 100:
            logger.warning(f"Skipping {ticker}: only {len(prepared)} usable rows")
            continue

        result = run_full_suite(
            prepared["return"], prepared["var"], prepared["es"], alpha=args.alpha
        )
        per_ticker[ticker] = result
        pooled_returns.append(prepared["return"])
        pooled_var.append(prepared["var"])
        pooled_es.append(prepared["es"])

    if not pooled_returns:
        logger.error("No ticker had enough usable history")
        return 1

    # Pooled across tickers: per-ticker samples (~500 rows, ~25 breaches) are
    # too small for the independence test to have much power. Pooling is
    # legitimate here because each test statistic is a count over an aligned
    # breach indicator, not a time-series model fit across the boundary.
    pooled = run_full_suite(
        pd.concat(pooled_returns),
        pd.concat(pooled_var),
        pd.concat(pooled_es),
        alpha=args.alpha,
    )

    print("\n" + "=" * 78)
    print(f"POOLED TAIL BACKTEST  ({len(per_ticker)} tickers, alpha={args.alpha:.0%})")
    print("=" * 78)
    for result in pooled["tests"].values():
        print("  " + result.summary())
        for key, value in result.detail.items():
            print(f"      {key}: {value}")
        print()

    print("  Breach clustering:")
    for key, value in pooled["clustering"].items():
        print(f"      {key}: {value}")

    print("\n" + "-" * 78)
    print(f"{'TICKER':12s} {'BREACH%':>8s} {'KUPIEC':>10s} {'INDEP':>10s} {'ES Z2':>10s}")
    print("-" * 78)
    for ticker, result in sorted(per_ticker.items()):
        tests = result["tests"]
        rate = tests["kupiec_pof"].detail.get("observed_rate")
        print(
            f"{ticker:12s} {rate * 100 if rate else 0:>7.2f}% "
            f"{'REJECT' if tests['kupiec_pof'].reject else 'pass':>10s} "
            f"{'REJECT' if tests['christoffersen_independence'].reject else 'pass':>10s} "
            f"{tests['acerbi_szekely_z2'].statistic:>10.3f}"
        )

    if args.json:
        serialisable = {
            "pooled": {
                "tests": {
                    name: {
                        "statistic": r.statistic,
                        "p_value": r.p_value,
                        "reject": r.reject,
                        "detail": r.detail,
                    }
                    for name, r in pooled["tests"].items()
                },
                "clustering": pooled["clustering"],
            }
        }
        args.json.write_text(json.dumps(serialisable, indent=2, default=str), encoding="utf-8")
        logger.info(f"Wrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
