Daily-refreshed OHLCV snapshots (parquet) used as the fetch fallback when
Yahoo throttles the egress IP. Written by MarketDataFetcher on successful
fetches and by .github/workflows/refresh-snapshot.yml on a weekday cron.

Filenames are `{ticker}_{period}_{interval}.parquet`, but the fallback is no
longer keyed on an exact period match: `_load_best_snapshot` prefers the exact
period, then the shortest snapshot that still covers the requested window
(trimmed to it), then the longest shorter one. The cron only persists "2y"
while `score_timeseries` asks for "5y", so exact-match-only meant
`/api/score/{ticker}/outcomes` 500'd under throttling with a perfectly usable
snapshot sitting right here on disk.
