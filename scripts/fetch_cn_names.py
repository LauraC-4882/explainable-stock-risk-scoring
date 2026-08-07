"""Regenerate the committed A-share code -> company-name table.

Run this by hand when the mapping needs refreshing (new listings, renames);
it is NOT wired into the app, CI, or any cron. Its whole point is that the
result is a static file in the repo, so the serving path never makes this
call — see src/stock_risk/data/cn_names.py for the read side.

    .venv/bin/python scripts/fetch_cn_names.py          # rewrite the table
    .venv/bin/python scripts/fetch_cn_names.py --check  # CI-style diff check

Source is akshare's `stock_zh_a_spot`, which is **Sina-backed** — the same
provider family as the A-share price path in data/fetcher.py, and chosen for
the same reason. The obvious candidates for this job, `stock_info_a_code_name`
and `stock_individual_info_em`, are both Eastmoney-backed and fail outright
from this project's dev machine (`ConnectionError: connection forcibly closed`
and a `JSONDecodeError` on an HTML error page respectively), exactly as
fetcher.py's module docstring describes for every Eastmoney endpoint.

`stock_zh_a_spot` is a full-market spot quote (~5.5k rows, several MB) and
Sina starts returning HTML error pages when it is called repeatedly — it is
fine as an occasional one-shot and would be a bad thing to put on a request
path, which is the other half of why the output is committed rather than
fetched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parents[1] / "src" / "stock_risk" / "data" / "cn_names.json"

# Sina's own symbol spelling -> the Yahoo-style ticker this app uses
# everywhere else (see data/fetcher.py's _akshare_cn_symbol, which converts
# in the other direction). Note .SS, not .SH: that is Yahoo's spelling for
# Shanghai and the only one _is_cn_ticker recognises.
_PREFIX_TO_SUFFIX = {"sh": ".SS", "sz": ".SZ"}


def _to_yahoo_symbol(sina_code: str) -> str | None:
    """"sz301189" -> "301189.SZ"; None for anything that isn't an A-share.

    Beijing Stock Exchange codes (bj*) come back from the same endpoint but
    are outside this app's supported universe, so they are dropped rather
    than mapped onto an exchange suffix the fetcher cannot serve.
    """
    code = sina_code.strip().lower()
    suffix = _PREFIX_TO_SUFFIX.get(code[:2])
    digits = code[2:]
    if suffix is None or not (len(digits) == 6 and digits.isdigit()):
        return None
    return f"{digits.upper()}{suffix}"


def _spot_frame(attempts: int = 5):
    """`stock_zh_a_spot()`, retried with backoff.

    Sina answers the first call and then starts handing back an HTML error
    page for a while, which surfaces as `JSONDecodeError: Can not decode value
    starting with character '<'` from akshare's demjson. Observed repeatedly
    while building this table. A one-off generator can simply wait it out —
    this is the exact behaviour that makes the endpoint unacceptable on a
    request path.
    """
    import time

    import akshare as ak  # imported lazily so --check failures don't need the network

    for attempt in range(1, attempts + 1):
        try:
            return ak.stock_zh_a_spot()
        except Exception as exc:
            if attempt == attempts:
                raise
            delay = 15 * attempt
            print(f"attempt {attempt}/{attempts} failed ({exc}); retrying in {delay}s",
                  file=sys.stderr)
            time.sleep(delay)


def build_mapping() -> dict[str, str]:
    df = _spot_frame()
    mapping: dict[str, str] = {}
    for sina_code, name in zip(df["代码"], df["名称"]):
        symbol = _to_yahoo_symbol(str(sina_code))
        name = str(name).strip()
        # Suspended/delisted rows occasionally carry a blank or placeholder
        # name; an empty string here would be worse than no entry at all,
        # because the read side treats any hit as authoritative.
        if symbol and name and name != "-":
            mapping[symbol] = name
    return dict(sorted(mapping.items()))


def _serialize(mapping: dict[str, str]) -> str:
    # ensure_ascii=False keeps the Chinese names readable in the diff; the
    # trailing newline keeps the file POSIX-clean.
    return json.dumps(mapping, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed file is stale, without rewriting it",
    )
    args = parser.parse_args()

    mapping = build_mapping()
    if len(mapping) < 4000:
        # The A-share market has been >4k listings for years, so a short read
        # means a truncated or error response, not a shrinking market. Better
        # to fail than to commit a table that silently lost half its symbols.
        print(f"refusing to write: only {len(mapping)} symbols parsed", file=sys.stderr)
        return 1

    payload = _serialize(mapping)
    if args.check:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != payload:
            print(f"{OUT_PATH} is stale — rerun without --check", file=sys.stderr)
            return 1
        print(f"{OUT_PATH} is up to date ({len(mapping)} symbols)")
        return 0

    OUT_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(mapping)} symbols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
