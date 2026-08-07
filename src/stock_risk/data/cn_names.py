"""Offline A-share ticker -> company-name lookup.

`fetch_info` is yfinance-only and returns nothing but None values while Yahoo
throttles this deployment, which left the scorecard echoing the ticker as the
company name — a card reading "301189.SZ / 301189.SZ" tells a first-time user
nothing. For A-shares that fallback is avoidable: the names are static facts,
so they are generated once by scripts/fetch_cn_names.py and committed as
cn_names.json.

The read side deliberately has **no network path at all** — no fetch, no
refresh, no "if stale then reload". A name that is a few weeks out of date is
a non-event; another provider on the request path is not. This is the same
reasoning as the committed snapshots/ parquet files, one level up: prefer a
slightly stale local answer to a live dependency that can fail.

Distinct from known_symbols.py, which is a deliberately narrow, hand-written
table serving /api/search's name *matching* for this app's own quick-pick
universe ("not a general-purpose symbol search", per its own docstring). This
module is the opposite: whole-market, machine-generated, and lookup-only.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

_NAMES_PATH = Path(__file__).with_name("cn_names.json")


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    """The committed table, read once per process.

    A missing or corrupt file degrades to "no names available", which is
    exactly the behaviour that existed before this table did — it must never
    be able to break scoring for a ticker whose price data is perfectly fine.
    """
    try:
        with _NAMES_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.warning(f"CN name table missing at {_NAMES_PATH} — names fall back to the ticker")
        return {}
    except Exception as exc:
        logger.warning(f"CN name table at {_NAMES_PATH} is unreadable ({exc}) — ignoring it")
        return {}


def cn_name(ticker: str) -> str | None:
    """Company name for an A-share *ticker* ("301189.SZ" -> "奥尼电子").

    None for anything not in the table, including every non-A-share symbol —
    callers keep whatever fallback they already had.
    """
    return _names().get(ticker.strip().upper())
