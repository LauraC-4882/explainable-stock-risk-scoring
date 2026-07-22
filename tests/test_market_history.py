"""[G8] Tests for the historical market-event overlay (market_history.py).

Two halves: integrity of the curated event table (it is hand-written data, so
the things a typo breaks are asserted rather than assumed), and the overlay
arithmetic, exercised on synthetic series where every return, drawdown and
coverage classification is known by construction.

Plus the project's standing "no numpy scalars in API responses" walk
(CLAUDE.md rule 4) over the full payload — `_stats` computes on a pandas
Series, so every value it returns is a numpy scalar until it is cast.
"""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from stock_risk.market_history import (
    EVENTS,
    KINDS,
    MIN_BARS,
    SOURCES,
    overlay_events,
)


def _series(start: str, values: list[float]) -> pd.Series:
    """Close series on consecutive business days from *start*."""
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)))


# ── Curated data integrity ───────────────────────────────────────────────────


def test_event_ids_are_unique():
    ids = [e.id for e in EVENTS]
    assert len(ids) == len(set(ids))


def test_every_event_has_a_known_kind():
    assert {e.kind for e in EVENTS} <= set(KINDS)


def test_every_kind_is_actually_represented():
    # The UI groups by kind; a kind declared but never used would render an
    # empty group header.
    assert {e.kind for e in EVENTS} == set(KINDS)


def test_dates_parse_and_end_follows_start():
    for event in EVENTS:
        start = pd.Timestamp(event.start)
        if event.end is None:
            continue
        assert pd.Timestamp(event.end) > start, f"{event.id} ends before it starts"


def test_ongoing_events_have_not_already_ended():
    # An `end=None` event is rendered as "ongoing". If one of these actually
    # concluded, the row is now lying — this test is the reminder to date it.
    ongoing = [e.id for e in EVENTS if e.end is None]
    assert ongoing, "at least one ongoing event is expected"
    for event in EVENTS:
        if event.end is None:
            assert pd.Timestamp(event.start).date() <= date.today()


def test_every_cited_source_key_resolves():
    for event in EVENTS:
        for key in event.sources:
            assert key in SOURCES, f"{event.id} cites unknown source {key!r}"


def test_every_declared_source_is_actually_cited():
    cited = {key for e in EVENTS for key in e.sources}
    assert cited == set(SOURCES), "unused source entry in SOURCES"


def test_summaries_are_bilingual():
    for event in EVENTS:
        assert event.name and event.name_zh, f"{event.id} missing a name"
        assert event.summary and event.summary_zh, f"{event.id} missing a summary"


# ── Overlay arithmetic ───────────────────────────────────────────────────────


def test_return_drawdown_and_vol_over_a_known_window():
    # 40 business days from 2021-01-01, flat 100 except a dip to 50 midway and
    # a close at 200 — return +100%, worst drawdown -50%.
    values = [100.0] * 40
    values[20] = 50.0
    values[-1] = 200.0
    close = _series("2021-01-01", values)

    event = type(EVENTS[0])(
        id="t", kind="bull", name="T", name_zh="T",
        start="2021-01-01", end="2021-12-31", region="us",
        summary="s", summary_zh="s", sources=(),
    )
    row = overlay_events(close, events=(event,))["events"][0]

    assert row["coverage"] == "full"
    assert row["return_pct"] == 100.0
    assert row["max_drawdown_pct"] == -50.0
    assert row["trading_days"] == 40
    assert row["annualized_vol_pct"] > 0


def test_coverage_is_partial_when_the_stock_listed_mid_event():
    # Price history starts 2021-06-01; the event started 2021-01-01.
    close = _series("2021-06-01", [100.0] * 60)
    event = type(EVENTS[0])(
        id="t", kind="bear", name="T", name_zh="T",
        start="2021-01-01", end="2021-12-31", region="us",
        summary="s", summary_zh="s", sources=(),
    )
    row = overlay_events(close, events=(event,))["events"][0]

    assert row["coverage"] == "partial"
    # Stats describe only the part actually traded, and say so via observed_*.
    assert row["observed_start"] == "2021-06-01"


def test_event_outside_price_history_is_reported_not_dropped():
    close = _series("2021-01-01", [100.0] * 60)
    event = type(EVENTS[0])(
        id="t", kind="crisis", name="T", name_zh="T",
        start="1929-10-01", end="1932-07-08", region="us",
        summary="s", summary_zh="s", sources=(),
    )
    result = overlay_events(close, events=(event,))
    row = result["events"][0]

    assert result["events_total"] == 1
    assert result["events_covered"] == 0
    assert row["coverage"] == "none"
    assert row["return_pct"] is None
    assert row["max_drawdown_pct"] is None
    assert row["observed_start"] is None


def test_too_few_bars_degrades_to_no_coverage():
    # The window overlaps, but by fewer than MIN_BARS sessions — describing a
    # handful of prints as the event's return would be noise.
    close = _series("2021-01-01", [100.0] * 60)
    end = close.index[MIN_BARS - 2].strftime("%Y-%m-%d")
    event = type(EVENTS[0])(
        id="t", kind="crisis", name="T", name_zh="T",
        start="2021-01-01", end=end, region="us",
        summary="s", summary_zh="s", sources=(),
    )
    row = overlay_events(close, events=(event,))["events"][0]

    assert row["trading_days"] < MIN_BARS
    assert row["coverage"] == "none"
    assert row["return_pct"] is None


def test_ongoing_event_runs_to_the_end_of_price_history():
    close = _series("2021-01-01", list(np.linspace(100.0, 200.0, 60)))
    event = type(EVENTS[0])(
        id="t", kind="bull", name="T", name_zh="T",
        start="2021-01-01", end=None, region="us",
        summary="s", summary_zh="s", sources=(),
    )
    result = overlay_events(close, events=(event,))
    row = result["events"][0]

    assert row["ongoing"] is True
    assert row["observed_end"] == result["price_history_end"]
    assert row["return_pct"] == 100.0


def test_events_are_sorted_newest_first():
    close = _series("2000-01-01", [100.0] * 4000)
    rows = overlay_events(close)["events"]
    starts = [r["start"] for r in rows]
    assert starts == sorted(starts, reverse=True)


def test_tz_aware_index_is_handled():
    # A tz-aware index compared against a naive Timestamp raises rather than
    # coercing, so the overlay normalises first.
    close = _series("2021-01-01", [100.0] * 60)
    close.index = close.index.tz_localize("UTC")
    result = overlay_events(close)
    assert result["price_history_start"] == "2021-01-01"


def test_empty_series_raises():
    with pytest.raises(ValueError):
        overlay_events(pd.Series(dtype=float))


# ── Payload contract ─────────────────────────────────────────────────────────


def test_payload_states_it_does_not_feed_the_risk_score():
    close = _series("2021-01-01", [100.0] * 60)
    assert overlay_events(close)["contributes_to_risk_score"] is False


def test_payload_is_json_serializable_with_no_numpy_scalars():
    """CLAUDE.md rule 4: a numpy.float32/float64 reaching an API response
    raises inside json.dumps (or slips through and breaks ModelMonitor)."""
    close = _series("2005-01-03", list(np.linspace(10.0, 400.0, 5000)))
    payload = overlay_events(close)

    json.dumps(payload)  # raises TypeError on any un-cast numpy scalar

    leaks = []

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
        elif type(obj).__module__ == "numpy":
            leaks.append(f"{path} = {type(obj).__name__}")

    walk(payload)
    assert leaks == [], f"numpy scalars leaked into the payload: {leaks}"


def test_full_table_runs_against_a_long_history():
    # Every curated event, against a series spanning 2005-2026: nothing in the
    # table should raise, and the modern events should be covered.
    close = _series("2005-01-03", list(np.linspace(10.0, 400.0, 5500)))
    result = overlay_events(close)

    assert result["events_total"] == len(EVENTS)
    assert result["events_covered"] > 0
    by_id = {r["id"]: r for r in result["events"]}
    assert by_id["cri_gfc"]["coverage"] == "full"        # 2007-2009, in range
    assert by_id["cri_tulip"]["coverage"] == "none"      # 1637, never in range
