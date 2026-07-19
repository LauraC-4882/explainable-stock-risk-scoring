"""[G4] Walk-forward validation of the VIX/VIX3M term-structure signal — the
ONE options-implied signal that is backtestable today (both legs have full
daily history on yfinance; stock-level IV has no history until the snapshot
collector accumulates it).

Question: conditional on the term structure being in backwardation
(VIX > VIX3M, fear concentrated in the immediate future) vs contango, are
the NEXT 20 days actually worse — higher realized vol, more drawdown
events — for SPY and a cross-sector stock universe? The answer decides
whether this signal ever qualifies for fusion weight. A null result is a
valid result and gets reported as such.

Indices are fetched (and disk-cached) at >=10y; the stock panel reuses the
[G2]/[G3] experiment cache (5y, 50+ tickers).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stock_risk.data.fetcher import MarketDataFetcher  # noqa: E402

ROOT = Path(__file__).parent.parent
OHLCV_CACHE = ROOT / "data/experiments/ohlcv"
INDEX_CACHE = ROOT / "data/experiments/indices"

HORIZON = 20
EVENT_THRESHOLD = -0.10


def _cached_history(symbol: str, period: str) -> pd.DataFrame:
    INDEX_CACHE.mkdir(parents=True, exist_ok=True)
    path = INDEX_CACHE / f"{symbol.replace('^', '_')}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    df = MarketDataFetcher().fetch_history(symbol, period=period)
    df.to_parquet(path)
    return df


def _forward_stats(close: pd.Series, low: pd.Series) -> pd.DataFrame:
    r = np.log(close / close.shift(1))
    fwd_vol = (
        r.shift(-HORIZON).rolling(HORIZON).std() * np.sqrt(252)
    )
    fwd_min_close = close.shift(-HORIZON).rolling(HORIZON).min()
    fwd_dd = fwd_min_close / close - 1
    return pd.DataFrame({
        "fwd_vol": fwd_vol,
        "fwd_event": (fwd_dd <= EVENT_THRESHOLD).astype(float).where(fwd_dd.notna()),
    })


def main() -> int:
    try:
        vix = _cached_history("^VIX", "15y")["close"].rename("vix")
        vix3m = _cached_history("^VIX3M", "15y")["close"].rename("vix3m")
        spy = _cached_history("SPY", "15y")
    except Exception as exc:
        print(f"Index fetch failed (rate limit?): {exc}", file=sys.stderr)
        return 1

    term = pd.concat([vix, vix3m], axis=1).dropna()
    term["backwardation"] = term["vix"] > term["vix3m"]
    bwd_share = term["backwardation"].mean()
    print(f"term-structure history: {len(term)} days "
          f"({term.index[0].date()} -> {term.index[-1].date()}), "
          f"backwardation {bwd_share:.1%} of days")

    panels: dict[str, pd.DataFrame] = {"SPY": spy}
    for path in sorted(OHLCV_CACHE.glob("*.parquet")):
        panels[path.stem.replace("_", ".")] = pd.read_parquet(path)
    print(f"stock panel: {len(panels) - 1} tickers + SPY")

    rows = []
    for name, df in panels.items():
        stats = _forward_stats(df["close"], df["low"])
        joined = stats.join(term["backwardation"], how="inner").dropna()
        if len(joined) < 200:
            continue
        for state, grp in joined.groupby("backwardation"):
            rows.append({
                "ticker": name,
                "state": "backwardation" if state else "contango",
                "n_days": len(grp),
                "fwd_vol_mean": grp["fwd_vol"].mean(),
                "fwd_event_rate": grp["fwd_event"].mean(),
            })

    table = pd.DataFrame(rows)
    if table.empty:
        print("no overlapping data — populate the stock cache first", file=sys.stderr)
        return 1

    pooled = table.groupby("state").apply(
        lambda g: pd.Series({
            "tickers": g["ticker"].nunique(),
            "days_avg": g["n_days"].mean(),
            "fwd_vol_mean": np.average(g["fwd_vol_mean"], weights=g["n_days"]),
            "fwd_event_rate": np.average(g["fwd_event_rate"], weights=g["n_days"]),
        }),
        include_groups=False,
    )
    spy_only = table[table["ticker"] == "SPY"].set_index("state")[
        ["n_days", "fwd_vol_mean", "fwd_event_rate"]
    ]

    print("\n== SPY: next-20d conditional on today's term structure ==")
    print(spy_only.round(4).to_string())
    print("\n== pooled stock universe (n-weighted) ==")
    print(pooled.round(4).to_string())

    b, c = "backwardation", "contango"
    if b in pooled.index and c in pooled.index:
        vol_lift = pooled.loc[b, "fwd_vol_mean"] / pooled.loc[c, "fwd_vol_mean"] - 1
        ev_lift = pooled.loc[b, "fwd_event_rate"] / max(pooled.loc[c, "fwd_event_rate"], 1e-9) - 1
        print(f"\nbackwardation vs contango: fwd vol {vol_lift:+.1%}, "
              f"drawdown-event rate {ev_lift:+.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
