"""Top up ScoreSnapshot for every watchlisted ticker.

The watchlist board (/api/watchlist/overview) reads only stored snapshots, and
those are normally written as a side effect of ordinary traffic — someone opens
a stock, that day's reading gets recorded. That covers actively-viewed tickers
but not one a user starred and then didn't open, which would sit at "no reading
yet" forever.

This job closes that gap: once a day, score every distinct watchlisted ticker
that has no reading for today. Rate-limit tolerant by design — a ticker that
fails is skipped and retried tomorrow, and the job always exits 0 so an
upstream outage never shows up as a red cron (same contract as
scripts/refresh_snapshots.py; see README "Deployment").
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loguru import logger  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from stock_risk.auth.models import ScoreSnapshot, WatchlistItem  # noqa: E402
from stock_risk.db import engine, init_db  # noqa: E402
from stock_risk.scoring.scorer import RiskScorer, market_for_ticker  # noqa: E402


def main() -> int:
    init_db()
    today = datetime.now(timezone.utc).date()

    with Session(engine) as session:
        watched = sorted({i.ticker for i in session.exec(select(WatchlistItem)).all()})
        already = {
            s.ticker
            for s in session.exec(
                select(ScoreSnapshot).where(ScoreSnapshot.captured_on == today)
            ).all()
        }

    todo = [t for t in watched if t not in already]
    if not watched:
        print("no watchlisted tickers — nothing to refresh")
        return 0
    print(
        f"{len(watched)} watchlisted, {len(already)} already have today's reading, "
        f"{len(todo)} to do"
    )

    scorer = RiskScorer()
    ok, failed = [], []
    for ticker in todo:
        try:
            result = scorer.score(ticker)
            with Session(engine) as session:
                session.add(
                    ScoreSnapshot(
                        ticker=ticker,
                        market=market_for_ticker(ticker),
                        risk_score=float(result["risk_score"]),
                        risk_label=str(result.get("risk_label", "")),
                        captured_on=today,
                    )
                )
                session.commit()
            ok.append(ticker)
            logger.info(f"{ticker}: {result['risk_score']}")
        except Exception as exc:
            failed.append(ticker)
            logger.warning(f"{ticker}: {str(exc)[:100]}")

    print(f"recorded {len(ok)}/{len(todo)} snapshots; failed: {failed or 'none'}")
    if todo and not ok:
        # Visible in the Actions log without failing the run — an upstream
        # throttle is an outage, not a broken commit.
        print("::warning title=score snapshots::0 tickers recorded (upstream likely throttled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
