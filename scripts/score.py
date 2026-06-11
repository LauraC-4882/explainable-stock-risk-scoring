"""Score a single ticker from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from stock_risk.scoring.scorer import RiskScorer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score a stock ticker")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default="2y")
    args = parser.parse_args()

    scorer = RiskScorer()
    result = scorer.score(args.ticker, period=args.period)
    print(json.dumps(result, indent=2))
