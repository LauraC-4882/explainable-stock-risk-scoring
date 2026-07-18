"""Live market data fetcher using yfinance."""

from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd
import requests
import yfinance as yf
from cachetools import TTLCache
from loguru import logger

from .validation import validate_ohlcv

# Market data (price history, VIX, options IV) moves within a trading day —
# 15 minutes bounds staleness without re-fetching on every request.
_FAST_TTL_SECONDS = 15 * 60
# Fundamentals/news/analyst/insider activity change far less often; caching
# them for a day cuts real request volume without materially staling the data.
_SLOW_TTL_SECONDS = 24 * 60 * 60


class _TimeoutSession(requests.Session):
    """Injects a default timeout into every request yfinance makes through
    this session. history() takes an explicit timeout= kwarg of its own, but
    yfinance's property-style accessors (.info, .fast_info, .news, .options,
    .option_chain(), .upgrades_downgrades, .insider_transactions) have no
    timeout parameter to pass — this is the one place that bounds all of
    them, instead of leaving each one able to hang indefinitely if Yahoo's
    upstream stalls.
    """

    def __init__(self, timeout: int):
        super().__init__()
        self._default_timeout = timeout

    def request(self, *args, **kwargs):  # noqa: D102 — requests.Session's own signature
        kwargs.setdefault("timeout", self._default_timeout)
        return super().request(*args, **kwargs)


class MarketDataFetcher:
    """Fetches OHLCV price history, fundamentals, and options data from Yahoo Finance."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._session = _TimeoutSession(timeout)
        self._fast_cache: TTLCache = TTLCache(maxsize=256, ttl=_FAST_TTL_SECONDS)
        self._slow_cache: TTLCache = TTLCache(maxsize=256, ttl=_SLOW_TTL_SECONDS)

    def _cached(
        self,
        cache: TTLCache,
        key: tuple,
        fetch: Callable[[], Any],
        is_empty: Callable[[Any], bool] = lambda r: r is None,
    ) -> Any:
        """Return cache[key], computing it via fetch() on a miss.

        Exceptions from fetch() propagate without being cached (they never
        reach the `cache[key] = result` line). Results fetch() itself
        determined were empty/failed (via its own internal try/except — see
        e.g. fetch_news's `except: return []`) are intentionally not cached
        either, via is_empty, so a transient failure gets retried on the next
        request instead of being pinned as a false "empty" result for a full
        TTL window.
        """
        if key in cache:
            return cache[key]
        result = fetch()
        if not is_empty(result):
            cache[key] = result
        return result

    def fetch_history(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return daily OHLCV DataFrame for *ticker*.

        Args:
            ticker: Stock symbol, e.g. "AAPL".
            period: yfinance period string used when start/end are not given.
            interval: Bar interval ("1d", "1h", …).
            start: ISO date string override.
            end: ISO date string override.
        """
        key = ("history", ticker, period, interval, start, end)

        def _do() -> pd.DataFrame:
            logger.info(f"Fetching history for {ticker} | period={period} interval={interval}")
            tk = yf.Ticker(ticker, session=self._session)
            if start or end:
                df = tk.history(
                    start=start, end=end, interval=interval, auto_adjust=True, timeout=self.timeout
                )
            else:
                df = tk.history(
                    period=period, interval=interval, auto_adjust=True, timeout=self.timeout
                )

            if df.empty:
                raise ValueError(f"No data returned for ticker '{ticker}'")

            df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
            df.index.name = "date"
            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]
            return validate_ohlcv(df, ticker)

        return self._cached(self._fast_cache, key, _do)

    def fetch_info(self, ticker: str) -> dict:
        """Return key fundamentals/metadata for *ticker*."""
        key = ("info", ticker)

        def _do() -> dict:
            logger.info(f"Fetching info for {ticker}")
            tk = yf.Ticker(ticker, session=self._session)
            info = tk.info or {}
            keys = [
                "shortName", "sector", "industry", "marketCap", "beta",
                "trailingPE", "forwardPE", "dividendYield", "52WeekChange",
                "sharesOutstanding", "floatShares",
            ]
            return {k: info.get(k) for k in keys}

        return self._cached(self._slow_cache, key, _do, is_empty=lambda r: not r)

    def fetch_news(self, ticker: str, limit: int = 8) -> list[dict]:
        """Return recent news headlines for *ticker* via yfinance (no API key required)."""
        key = ("news", ticker, limit)

        def _do() -> list[dict]:
            logger.info(f"Fetching news for {ticker}")
            try:
                tk = yf.Ticker(ticker, session=self._session)
                items = tk.news or []
            except Exception as exc:
                logger.warning(f"Could not fetch news for {ticker}: {exc}")
                return []

            articles = []
            for item in items[:limit]:
                content = item.get("content", item)  # yfinance nests fields under "content"
                title = content.get("title")
                if not title:
                    continue
                articles.append({
                    "title": title,
                    "summary": content.get("summary") or content.get("description") or "",
                    "publisher": (content.get("provider") or {}).get("displayName")
                        if isinstance(content.get("provider"), dict) else content.get("publisher"),
                    "published_at": content.get("pubDate") or content.get("providerPublishTime"),
                    "link": (content.get("canonicalUrl") or {}).get("url")
                        if isinstance(content.get("canonicalUrl"), dict) else content.get("link"),
                })
            return articles

        return self._cached(self._slow_cache, key, _do, is_empty=lambda r: not r)

    def fetch_analyst_activity(self, ticker: str, lookback_days: int = 90) -> dict:
        """Recent analyst rating-change counts via yfinance (no extra API key).

        Downgrades are a forward-looking risk signal — analysts often move
        ahead of a drawdown, not just react to one.
        """
        key = ("analyst_activity", ticker, lookback_days)
        empty = {"downgrade_count": 0, "upgrade_count": 0}

        def _do() -> dict:
            logger.info(f"Fetching analyst activity for {ticker}")
            try:
                df = yf.Ticker(ticker, session=self._session).upgrades_downgrades
            except Exception as exc:
                logger.warning(f"Could not fetch analyst activity for {ticker}: {exc}")
                return empty

            if df is None or df.empty:
                return empty

            df = df.reset_index()
            date_col = next((c for c in df.columns if "date" in c.lower()), None)
            if date_col is not None:
                try:
                    dates = pd.to_datetime(df[date_col], utc=True).dt.tz_localize(None)
                    cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
                    df = df[dates >= cutoff]
                except Exception:
                    df = df.head(20)  # date parsing failed — fall back to "most recent N rows"
            else:
                df = df.head(20)

            action_col = next((c for c in df.columns if c.lower() == "action"), None)
            if action_col is None:
                return empty

            actions = df[action_col].astype(str).str.lower()
            return {
                "downgrade_count": int(actions.eq("downgrade").sum()),
                "upgrade_count": int(actions.eq("upgrade").sum()),
            }

        return self._cached(self._slow_cache, key, _do, is_empty=lambda r: r == empty)

    def fetch_insider_activity(self, ticker: str) -> dict:
        """Recent insider transaction summary via yfinance (no extra API key)."""
        key = ("insider_activity", ticker)
        empty = {"sale_count": 0, "purchase_count": 0, "net_transaction_count": 0}

        def _do() -> dict:
            logger.info(f"Fetching insider activity for {ticker}")
            try:
                df = yf.Ticker(ticker, session=self._session).insider_transactions
            except Exception as exc:
                logger.warning(f"Could not fetch insider transactions for {ticker}: {exc}")
                return empty

            if df is None or df.empty or "Transaction" not in df.columns:
                return empty

            transaction = df["Transaction"].astype(str).str.lower()
            sale_count = int(transaction.str.contains("sale").sum())
            purchase_count = int(transaction.str.contains("purchase").sum())
            return {
                "sale_count": sale_count,
                "purchase_count": purchase_count,
                "net_transaction_count": purchase_count - sale_count,
            }

        return self._cached(self._slow_cache, key, _do, is_empty=lambda r: r == empty)

    def fetch_vix(self) -> Optional[float]:
        """Return the latest CBOE VIX index level, or None on failure."""
        key = ("vix",)

        def _do() -> Optional[float]:
            try:
                return float(yf.Ticker("^VIX", session=self._session).fast_info.last_price)
            except Exception as exc:
                logger.warning(f"Could not fetch VIX: {exc}")
                return None

        return self._cached(self._fast_cache, key, _do)

    def fetch_options_iv(self, ticker: str) -> Optional[float]:
        """Return the nearest-expiry at-the-money implied volatility, or None."""
        key = ("options_iv", ticker)

        def _do() -> Optional[float]:
            try:
                tk = yf.Ticker(ticker, session=self._session)
                expirations = tk.options
                if not expirations:
                    return None
                chain = tk.option_chain(expirations[0])
                spot = tk.fast_info.last_price
                calls = chain.calls
                atm = calls.iloc[(calls["strike"] - spot).abs().argsort().iloc[0]]
                return float(atm.get("impliedVolatility", float("nan")))
            except Exception as exc:
                logger.warning(f"Could not fetch options IV for {ticker}: {exc}")
                return None

        return self._cached(self._fast_cache, key, _do)
