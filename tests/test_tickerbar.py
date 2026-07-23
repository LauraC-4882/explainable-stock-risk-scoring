"""GET /api/tickerbar — snapshot-derived header marquee data.

The endpoint's contract is as much about what it must NOT do as what it
returns: it reads only persisted snapshot parquets, never scores and never
fetches, because a decorative marquee firing scoring runs per page load
would be a self-inflicted stampede on the free-tier dyno.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from stock_risk.api import app as app_module
    from stock_risk.config import settings

    monkeypatch.setattr(settings, "snapshot_dir", tmp_path)
    # Reset the in-process cache so each test sees its own snapshot dir.
    app_module._tickerbar_cache["rows"] = None
    app_module._tickerbar_cache["at"] = 0.0
    return TestClient(app_module.app)


def _write_snapshot(directory, ticker: str, closes: list[float]):
    safe = ticker.replace("^", "_").replace(".", "_").replace("/", "_")
    idx = pd.bdate_range("2026-07-01", periods=len(closes))
    df = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1000},
        index=idx,
    )
    df.to_parquet(directory / f"{safe}_2y_1d.parquet")
    return idx[-1].date()


def test_returns_last_close_change_and_as_of(client, tmp_path):
    as_of = _write_snapshot(tmp_path, "AAPL", [100.0, 110.0])
    res = client.get("/api/tickerbar")
    assert res.status_code == 200
    entries = res.json()["entries"]
    assert len(entries) == 1
    row = entries[0]
    assert row["ticker"] == "AAPL"
    assert row["last"] == 110.0
    assert row["change_pct"] == 10.0
    # Every row carries its data age — the frontend labels it rather than
    # implying a live feed.
    assert row["as_of"] == str(as_of)


def test_missing_snapshots_are_omitted_not_errors(client):
    res = client.get("/api/tickerbar")
    assert res.status_code == 200
    assert res.json()["entries"] == []


def test_cn_ticker_filename_mapping(client, tmp_path):
    _write_snapshot(tmp_path, "600519.SS", [1300.0, 1305.0])
    entries = client.get("/api/tickerbar").json()["entries"]
    assert [e["ticker"] for e in entries] == ["600519.SS"]


def test_single_row_snapshot_is_skipped(client, tmp_path):
    # One close can't produce a day-over-day change; skip rather than fake it.
    _write_snapshot(tmp_path, "AAPL", [100.0])
    assert client.get("/api/tickerbar").json()["entries"] == []


def test_universe_contains_no_hong_kong_listings(client):
    from stock_risk.api.app import _TICKERBAR_UNIVERSE

    assert not any(t.endswith(".HK") or t.startswith("^HSI") for t in _TICKERBAR_UNIVERSE)
