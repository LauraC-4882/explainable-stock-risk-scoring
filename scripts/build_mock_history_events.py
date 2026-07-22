"""[G8] Regenerate tests/fixtures/mock_api/history_events_tsla.json.

The screenshot harness (scripts/ui_shot.sh) runs with STOCK_RISK_MOCK=1 and
must never touch the network, so the historical-events panel needs a fixture
like the score/timeseries/outcomes panels already have. Unlike those, this one
is *generated* rather than captured: the real endpoint fetches period="max"
(~15 years for TSLA), and committing thousands of raw daily bars to capture a
payload derived from them would be a large fixture for no extra fidelity.

Instead this builds a synthetic close series with TSLA's real listing date
(2010-06-29) and a plausible shape, then runs it through the *real*
`overlay_events`. That keeps the fixture's structure guaranteed-identical to
production output — same keys, same rounding, same coverage logic — while
exercising all three render branches the panel must handle:

  - coverage "full"    — events starting after 2010-06-29 (COVID, 2022 bear,
                         AI rally, 2023 banks, …)
  - coverage "partial" — events already running at listing (the 2009-2020
                         bull market and post-GFC expansion)
  - coverage "none"    — everything before TSLA existed (1929, 2008, …)

Deterministic: the series is seeded, so re-running produces a byte-identical
fixture and the screenshot harness stays reproducible.

Usage:
    .venv/bin/python scripts/build_mock_history_events.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from stock_risk.market_history import overlay_events

OUT = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "mock_api" / "history_events_tsla.json"
)

# TSLA's actual IPO date, so the "partial coverage" branch lands on the real
# events it lands on in production.
LISTING_DATE = "2010-06-29"
END_DATE = "2026-07-20"
SEED = 20260720


def build_close() -> pd.Series:
    """A seeded geometric random walk on TSLA's real trading calendar span.

    Drift and volatility are set to roughly TSLA-like annualised figures
    (~35% drift, ~55% vol) so the rendered numbers look plausible in a
    screenshot. They are not a claim about TSLA — this series is fixture
    scaffolding whose only job is to make the panel render every branch.
    """
    dates = pd.bdate_range(LISTING_DATE, END_DATE)
    rng = np.random.default_rng(SEED)
    daily = rng.normal(0.35 / 252, 0.55 / np.sqrt(252), len(dates))
    return pd.Series(1.27 * np.exp(np.cumsum(daily)), index=dates, name="close")


def main() -> None:
    payload = overlay_events(build_close())
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    by_coverage: dict[str, int] = {}
    for event in payload["events"]:
        by_coverage[event["coverage"]] = by_coverage.get(event["coverage"], 0) + 1
    print(f"wrote {OUT.relative_to(Path.cwd())}")
    print(f"  events: {payload['events_total']}  coverage: {by_coverage}")


if __name__ == "__main__":
    main()
