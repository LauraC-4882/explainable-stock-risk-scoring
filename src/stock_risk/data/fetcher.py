"""Live market data fetcher.

[Data-source migration, 2026-07] Price history no longer comes from a single
source. yfinance's chronic datacenter-IP throttling (see README "Deployment")
motivated splitting fetch_history by market, each routed to whichever source
was actually verified live (not assumed) to work for that market:

  - US equities  -> Twelve Data (a real commercial API, not a scrape) when
    TWELVE_DATA_KEY is configured; yfinance otherwise (unchanged behavior
    for local dev/CI without a key).
  - CN A-shares   -> akshare, Sina-backed (`stock_zh_a_daily`) — verified
    live; akshare's eastmoney-backed functions (the library's own most
    common examples, incl. `stock_zh_a_hist`) got connection-reset from
    this dev machine on every attempt, Sina/Tencent-backed ones didn't.
  - CN ETFs (the CSI 300 benchmark) -> akshare `fund_etf_hist_sina` — the
    stock-only Sina endpoint above 404s on ETF codes, so the CN path tries
    the stock endpoint first and falls back to the ETF one.
  - HK equities   -> akshare, Tencent-backed (`stock_hk_daily`) — verified
    live, full OHLCV including real volume.
  - ^HSI (the HK beta benchmark) -> akshare, Sina-backed
    (`stock_hk_index_daily_sina`) — verified live. This is what makes the
    whole "China" bucket (A-shares + HK equities + the HK benchmark) fully
    akshare-backed with ZERO yfinance dependency in its price/beta path.
  - ^VIX, ^VIX3M stay on yfinance: they're US CBOE volatility indices
    feeding only the soft, already-degrading market-regime signal — not
    any China-bucket price/beta computation — so leaving them on yfinance
    costs nothing when they fail (the score still returns without them).

Every path still funnels through the same OHLCV contract (validate_ohlcv),
the same TTL cache, and the same snapshot fallback below — a provider
outage degrades exactly like a yfinance outage always has.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import akshare as ak
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

# period string -> calendar days of history to request/keep. Padded above the
# trading-day equivalent (roughly 0.69x calendar days) so weekends/holidays
# never leave a request short; only "2y" and "5y" are actually reached by the
# app today (see scorer.py's _fetch_period_for_display), the rest are kept
# for completeness/robustness against future callers.
_PERIOD_TO_DAYS = {
    "5d": 7, "1mo": 31, "3mo": 93, "6mo": 186,
    "1y": 370, "2y": 740, "5y": 1830, "10y": 3660,
}


def _is_index_symbol(ticker: str) -> bool:
    return ticker.startswith("^")


# Index symbols akshare's Sina endpoint serves, keyed by the app's Yahoo-style
# symbol -> akshare's own symbol. ^HSI is the HK beta benchmark
# (MARKET_BENCHMARKS["hk"]); routing it here is what makes the whole China
# bucket — A-shares, HK equities, AND the HK benchmark — fully akshare-backed
# with zero yfinance dependency in the price path. ^VIX/^VIX3M are deliberately
# NOT here: they feed only the soft, already-degrading market-regime signal,
# not any China-bucket price/beta computation, so they stay on yfinance.
_AKSHARE_INDEX_SYMBOLS = {"^HSI": "HSI"}


def _is_cn_ticker(ticker: str) -> bool:
    return ticker.upper().endswith((".SS", ".SZ"))


def _is_hk_ticker(ticker: str) -> bool:
    return ticker.upper().endswith(".HK")


def _akshare_cn_symbol(ticker: str) -> str:
    """"600519.SS" -> "sh600519", "000001.SZ" -> "sz000001"."""
    code, _, suffix = ticker.upper().partition(".")
    prefix = "sz" if suffix == "SZ" else "sh"
    return f"{prefix}{code}"


def _akshare_hk_symbol(ticker: str) -> str:
    """"0700.HK" -> "00700" — akshare's HK functions want a 5-digit code."""
    return ticker.upper().removesuffix(".HK").zfill(5)


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
                # Only the plain period-based path (no explicit date window)
                # is covered by the new per-market sources — every current
                # caller uses period=, and start/end is kept on the original
                # yfinance path since no caller actually exercises it today
                # (see the module docstring for why each market routes where
                # it does).
                if not (start or end) and interval == "1d":
                    if _is_cn_ticker(ticker):
                        df = self._fetch_cn_akshare(ticker, period)
                    elif _is_hk_ticker(ticker):
                        df = self._fetch_hk_akshare(ticker, period)
                    elif ticker in _AKSHARE_INDEX_SYMBOLS:
                        df = self._fetch_index_akshare(_AKSHARE_INDEX_SYMBOLS[ticker], period)
                    elif not _is_index_symbol(ticker) and settings.twelve_data_key:
                        df = self._fetch_us_twelvedata(ticker, period)
                    else:
                        df = self._fetch_yfinance(ticker, period, interval, start, end)
                else:
                    df = self._fetch_yfinance(ticker, period, interval, start, end)

                if df.empty:
                    raise ValueError(f"No data returned for ticker '{ticker}'")
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

    def _fetch_yfinance(
        self, ticker: str, period: str, interval: str,
        start: Optional[str], end: Optional[str],
    ) -> pd.DataFrame:
        """The original path — still used for indices, US without a Twelve
        Data key, and any explicit start/end window."""
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
            return df
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
        df.index.name = "date"
        df.columns = [c.lower() for c in df.columns]
        return df[["open", "high", "low", "close", "volume"]]

    def _fetch_us_twelvedata(self, ticker: str, period: str) -> pd.DataFrame:
        """US equities via Twelve Data's REST API directly (no SDK — one
        endpoint, and this keeps the same timeout/error-handling shape as
        every other source here). Response shape verified against Twelve
        Data's own docs: {"values": [{"datetime", "open", "high", "low",
        "close", "volume"}, ...], "status": "ok"|"error"}, newest-first."""
        days = _PERIOD_TO_DAYS.get(period, 740)
        outputsize = min(5000, max(30, int(days * 0.75)))  # ~0.69 trading-days/calendar-day, padded
        resp = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": ticker,
                "interval": "1day",
                "outputsize": outputsize,
                "apikey": settings.twelve_data_key,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") == "error":
            raise ValueError(f"Twelve Data error for {ticker}: {payload.get('message')}")
        values = payload.get("values")
        if not values:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    def _fetch_cn_akshare(self, ticker: str, period: str) -> pd.DataFrame:
        """CN A-shares via akshare's Sina-backed stock_zh_a_daily; falls back
        to the Sina ETF endpoint for ETF codes (e.g. the CSI 300 benchmark
        510300.SS), which 404s on the stock-only endpoint. Both verified
        live — akshare's eastmoney-backed equivalents did not (see module
        docstring)."""
        symbol = _akshare_cn_symbol(ticker)
        try:
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
        except Exception:
            df = ak.fund_etf_hist_sina(symbol=symbol)
        return self._normalize_akshare_history(df, period)

    def _fetch_hk_akshare(self, ticker: str, period: str) -> pd.DataFrame:
        """HK equities via akshare's Tencent-backed stock_hk_daily — verified
        live, full OHLCV including real volume."""
        symbol = _akshare_hk_symbol(ticker)
        df = ak.stock_hk_daily(symbol=symbol, adjust="qfq")
        return self._normalize_akshare_history(df, period)

    def _fetch_index_akshare(self, ak_symbol: str, period: str) -> pd.DataFrame:
        """HK indices (currently just ^HSI, the HK beta benchmark) via
        akshare's Sina-backed stock_hk_index_daily_sina — verified live, full
        OHLCV. Its eastmoney counterpart (stock_hk_index_daily_em) got
        connection-reset from this dev machine, same as every other
        eastmoney-backed akshare function (see module docstring)."""
        df = ak.stock_hk_index_daily_sina(symbol=ak_symbol)
        return self._normalize_akshare_history(df, period)

    @staticmethod
    def _normalize_akshare_history(df: pd.DataFrame, period: str) -> pd.DataFrame:
        """akshare's history functions return full available history, not a
        windowed period — trim to the requested window here, uniformly for
        every akshare-backed market."""
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df.index.name = "date"
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        days = _PERIOD_TO_DAYS.get(period, 740)
        cutoff = df.index.max() - pd.Timedelta(days=days)
        return df[df.index >= cutoff]

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
