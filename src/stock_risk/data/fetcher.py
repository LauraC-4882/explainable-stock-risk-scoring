"""Live market data fetcher using yfinance."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
import requests
import yfinance as yf
from cachetools import TTLCache
from loguru import logger

from ..config import settings
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
            try:
                logger.info(
                    f"Fetching history for {ticker} | period={period} interval={interval}"
                )
                tk = yf.Ticker(ticker, session=self._session)
                if start or end:
                    df = tk.history(
                        start=start, end=end, interval=interval,
                        auto_adjust=True, timeout=self.timeout,
                    )
                else:
                    df = tk.history(
                        period=period, interval=interval,
                        auto_adjust=True, timeout=self.timeout,
                    )

                if df.empty:
                    raise ValueError(f"No data returned for ticker '{ticker}'")

                df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
                df.index.name = "date"
                df.columns = [c.lower() for c in df.columns]
                df = df[["open", "high", "low", "close", "volume"]]
                df = validate_ohlcv(df, ticker)
            except Exception as exc:
                # [IP-block resilience] Yahoo throttles shared datacenter IPs
                # for extended windows (see README "Deployment") — a demo that
                # 500s for hours because of upstream IP reputation serves
                # nobody. Fall back to the last persisted snapshot (validated
                # at save time, refreshed daily by CI) and say so loudly; only
                # fail when there is no snapshot either.
                snap = self._load_snapshot(ticker, period, interval)
                if snap is not None and not (start or end):
                    logger.warning(
                        f"{ticker}: live fetch failed ({exc}) — serving snapshot "
                        f"through {snap.index[-1].date()}"
                    )
                    return snap
                raise
            self._save_snapshot(ticker, period, interval, df)
            return df

        return self._cached(self._fast_cache, key, _do)

    @staticmethod
    def _snapshot_path(ticker: str, period: str, interval: str) -> Path:
        safe = ticker.replace("^", "_").replace(".", "_").replace("/", "_")
        return settings.snapshot_dir / f"{safe}_{period}_{interval}.parquet"

    def _save_snapshot(self, ticker: str, period: str, interval: str, df: pd.DataFrame) -> None:
        try:
            path = self._snapshot_path(ticker, period, interval)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        except Exception as exc:
            # Snapshot persistence is best-effort — a read-only filesystem
            # (some PaaS tiers) must never break the live fetch that succeeded.
            logger.warning(f"Could not persist snapshot for {ticker}: {exc}")

    def _load_snapshot(self, ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
        path = self._snapshot_path(ticker, period, interval)
        if not path.exists():
            return None
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            logger.warning(f"Snapshot for {ticker} unreadable: {exc}")
            return None

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

    def _fetch_index_last(self, symbol: str) -> Optional[float]:
        key = ("index_last", symbol)

        def _do() -> Optional[float]:
            try:
                return float(yf.Ticker(symbol, session=self._session).fast_info.last_price)
            except Exception as exc:
                logger.warning(f"Could not fetch {symbol}: {exc}")
                return None

        return self._cached(self._fast_cache, key, _do)

    def fetch_vix(self) -> Optional[float]:
        """Return the latest CBOE VIX index level, or None on failure."""
        return self._fetch_index_last("^VIX")

    def fetch_vix3m(self) -> Optional[float]:
        """[G4] Latest 3-month VIX (^VIX3M) for the term-structure signal:
        near VIX above 3-month VIX (backwardation) = fear concentrated in the
        immediate future, the practitioner-standard market-level risk-off
        switch. None on failure."""
        return self._fetch_index_last("^VIX3M")

    @staticmethod
    def _iv_at_strike(frame, target_strike: float) -> Optional[float]:
        """IV of the option whose strike is nearest *target_strike*, or None
        when the chain side is missing/thin or the IV itself is junk."""
        if frame is None or len(frame) == 0:
            return None
        if "strike" not in frame.columns or "impliedVolatility" not in frame.columns:
            return None
        row = frame.iloc[(frame["strike"] - target_strike).abs().argsort().iloc[0]]
        iv = row.get("impliedVolatility")
        if iv is None or pd.isna(iv) or iv <= 0:
            return None
        return float(iv)

    _EMPTY_OPTIONS_SIGNALS = {
        "atm_iv": None, "otm_put_iv": None, "put_skew": None, "expiry": None,
    }

    def fetch_options_signals(self, ticker: str) -> dict:
        """[G4] Forward-looking signals from ONE nearest-expiry chain snapshot
        (the same single tk.option_chain() call the old ATM-IV fetch already
        paid for — the put side used to be discarded on the floor):

          - atm_iv: median of the at-the-money call and put IVs;
          - otm_put_iv: the put nearest moneyness 0.95 (strike ~= 95% of
            spot — yfinance carries no deltas, so moneyness is the standard
            stand-in for "the crash-insurance strike");
          - put_skew: otm_put_iv - atm_iv (steepens when the market bids up
            crash insurance; Xing-Zhang-Zhao 2010 for the stock-level
            evidence — the SKEW-index-level story is mixed and not used).

        Every field is None (never an exception) when the ticker has no
        options, a one-sided/thin chain, or junk IVs — thin chains must not
        degrade the main scoring request.
        """
        key = ("options_signals", ticker)
        empty = dict(self._EMPTY_OPTIONS_SIGNALS)

        def _do() -> dict:
            try:
                tk = yf.Ticker(ticker, session=self._session)
                expirations = tk.options
                if not expirations:
                    return dict(empty)
                expiry = expirations[0]
                chain = tk.option_chain(expiry)
                spot = float(tk.fast_info.last_price)
                atm_call = self._iv_at_strike(chain.calls, spot)
                atm_put = self._iv_at_strike(chain.puts, spot)
                atm_side_ivs = [v for v in (atm_call, atm_put) if v is not None]
                atm_iv = float(pd.Series(atm_side_ivs).median()) if atm_side_ivs else None
                otm_put_iv = self._iv_at_strike(chain.puts, spot * 0.95)
                put_skew = (
                    otm_put_iv - atm_iv
                    if otm_put_iv is not None and atm_iv is not None
                    else None
                )
                return {
                    "atm_iv": atm_iv,
                    "otm_put_iv": otm_put_iv,
                    "put_skew": put_skew,
                    "expiry": expiry,
                }
            except Exception as exc:
                logger.warning(f"Could not fetch options signals for {ticker}: {exc}")
                return dict(empty)

        return self._cached(self._fast_cache, key, _do, is_empty=lambda r: r == empty)

    def fetch_options_iv(self, ticker: str) -> Optional[float]:
        """Nearest-expiry ATM implied volatility — kept for compatibility,
        now a view over fetch_options_signals (one chain fetch, one cache)."""
        return self.fetch_options_signals(ticker)["atm_iv"]
