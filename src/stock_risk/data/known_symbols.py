"""Static fallback for /api/search's company-name matching.

/api/search's primary source (yf.Search) is yfinance — subject to the same
Yahoo throttling as everything else in this app, and unlike fetch_history it
was never migrated (see fetcher.py's module docstring), since a symbol
lookup isn't a price-history read. When yf.Search fails or returns nothing
(observed live on Render: empty results for both "Tencent" and "Apple"),
typing a company name instead of its ticker would otherwise add the raw
text as a literal, invalid ticker — this table catches exactly the names a
user would reasonably type for this app's own known universe (the same
tickers in scripts/refresh_snapshots.py's UNIVERSE / EmptyState.jsx's
POPULAR) so the common case still resolves even with yfinance down.

Not a general-purpose symbol search — narrow and static on purpose.
"""

from __future__ import annotations

# (symbol, display name, exchange label, aliases to match against, in
# addition to the symbol and display name themselves).
_ENTRIES: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("AAPL", "Apple Inc.", "NASDAQ", ("apple", "苹果")),
    ("TSLA", "Tesla, Inc.", "NASDAQ", ("tesla", "特斯拉")),
    ("MSFT", "Microsoft Corporation", "NASDAQ", ("microsoft", "微软")),
    ("GOOGL", "Alphabet Inc.", "NASDAQ", ("google", "alphabet", "谷歌")),
    ("NVDA", "NVIDIA Corporation", "NASDAQ", ("nvidia", "英伟达")),
    ("AMZN", "Amazon.com, Inc.", "NASDAQ", ("amazon", "亚马逊")),
    ("META", "Meta Platforms, Inc.", "NASDAQ", ("meta", "facebook", "脸书")),
    ("JPM", "JPMorgan Chase & Co.", "NYSE", ("jpmorgan", "jp morgan", "摩根大通")),
    ("600519.SS", "Kweichow Moutai", "Shanghai", ("moutai", "kweichow moutai", "贵州茅台", "茅台")),
    ("0700.HK", "Tencent Holdings", "HKEX", ("tencent", "腾讯")),
    ("000001.SZ", "Ping An Bank", "Shenzhen", ("ping an bank", "平安银行")),
    ("9988.HK", "Alibaba Group", "HKEX", ("alibaba", "阿里巴巴", "阿里")),
    ("601318.SS", "Ping An Insurance", "Shanghai",
     ("ping an insurance", "ping an", "中国平安", "平安")),
    ("3690.HK", "Meituan", "HKEX", ("meituan", "美团")),
    ("SPY", "SPDR S&P 500 ETF Trust", "NYSE Arca", ("s&p 500", "sp500")),
    ("510300.SS", "CSI 300 ETF", "Shanghai", ("csi 300", "沪深300")),
]


def search_known_symbols(query: str, limit: int = 6) -> list[dict]:
    """Case-insensitive substring match against symbol, display name, and
    aliases. Returns the same shape /api/search's primary yf.Search path
    does, so callers can't tell which source answered."""
    q = query.strip().lower()
    if not q:
        return []
    matches = []
    for symbol, name, exchange, aliases in _ENTRIES:
        haystack = (symbol.lower(), name.lower(), *aliases)
        if any(q in h for h in haystack):
            matches.append({"symbol": symbol, "name": name, "exchange": exchange, "type": "Equity"})
    return matches[:limit]
