"""HTTP presentation of the scoring failure taxonomy.

`stock_risk.errors` decides *what went wrong*; this module decides what the
caller sees. One table (`ERROR_SPECS`) owns the whole mapping — status code,
safe English message, and how loudly to log — so there is exactly one place to
look when asking "what does the user get when X fails?".

The response body is deliberately flat:

    {"error": "UPSTREAM_UNAVAILABLE",
     "message": "Market data is temporarily unavailable — …",
     "detail":  "…same string…",
     "ticker":  "AAPL",
     "status":  503}

`error` is the machine-readable contract the frontend switches on (never the
message text, which is prose and will be reworded). `detail` duplicates
`message` because FastAPI's own error bodies use `detail` and every existing
client — `ui/web/src/api.js`, the backtest and portfolio callers, anything
hitting the API directly — already reads it; dropping it would have been a
silent breaking change for a saved keystroke.

`message` is always drawn from the table, never from `str(exc)`. That is the
whole point: a raw exception message can carry a file path, a SQL fragment, an
API key in a URL, or an internal hostname, and none of that belongs in a
browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..data.quality import MIN_TRADING_DAYS
from ..errors import ScoreErrorCode


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    message: str
    # "exception" -> full traceback (we suspect ourselves); "warning" -> one
    # line (an expected operating condition — a traceback per request would
    # bury the real errors); "info" -> the user typed something wrong, which
    # is not an event worth alarming anyone about.
    log_level: str


ERROR_SPECS: dict[ScoreErrorCode, ErrorSpec] = {
    ScoreErrorCode.TICKER_NOT_FOUND: ErrorSpec(
        status=404,
        message="Ticker not found — check the symbol and its exchange suffix.",
        log_level="info",
    ),
    ScoreErrorCode.INSUFFICIENT_DATA: ErrorSpec(
        # 422, not 404: the symbol is real and the request is well-formed, we
        # simply cannot produce an honest number from what exists yet. Matches
        # the status /api/score/{ticker}/backtest already returns for its own
        # "not enough history" case.
        status=422,
        # States the actual threshold rather than a vague "not enough data".
        # The number is what makes this message actionable: it tells a user
        # holding a fresh IPO that the answer is "wait", and roughly how long,
        # instead of leaving them to wonder whether they typed something wrong.
        # Interpolated from the constant so the copy cannot drift from the
        # check; the localized equivalents are held to the same number by
        # tests/test_scoring_errors.py.
        message=(
            f"Not enough listing history to score this stock — "
            f"at least {MIN_TRADING_DAYS} trading days are required."
        ),
        log_level="info",
    ),
    ScoreErrorCode.UPSTREAM_UNAVAILABLE: ErrorSpec(
        status=503,
        # Wording kept from the pre-taxonomy UPSTREAM_UNAVAILABLE_DETAIL: it
        # is the one message a user may read in English (direct API callers),
        # and it has to say what happened, whose fault it is, and what to do.
        message=(
            "Market data is temporarily unavailable — the upstream data provider is "
            "rate-limiting this server and no cached snapshot covers this symbol. "
            "Please try again in a few minutes."
        ),
        log_level="warning",
    ),
    ScoreErrorCode.CALCULATION_FAILED: ErrorSpec(
        status=500,
        # Says nothing about *why*, on purpose. The traceback goes to the
        # server log; the user gets a statement of fact they can act on by
        # trying a different stock.
        message="Scoring failed for this stock.",
        log_level="exception",
    ),
    ScoreErrorCode.DELISTED: ErrorSpec(
        status=422,
        message="This stock may be suspended or delisted — no recent trading data.",
        log_level="info",
    ),
}


class ScoringHTTPError(HTTPException):
    """An HTTPException that also carries its `ScoreErrorCode`.

    Subclasses HTTPException so FastAPI's normal machinery (and any
    `except HTTPException` already in the request path) treats it as the error
    response it is; the registered handler below is what turns it into the
    flat body above. Starlette resolves handlers by walking `type(exc).__mro__`
    and taking the first match, so registering this subclass takes precedence
    over the built-in HTTPException handler without disturbing it for every
    other endpoint.
    """

    def __init__(self, code: ScoreErrorCode, ticker: Optional[str] = None):
        spec = ERROR_SPECS[code]
        super().__init__(status_code=spec.status, detail=spec.message)
        self.code = code
        self.ticker = ticker

    @property
    def log_level(self) -> str:
        return ERROR_SPECS[self.code].log_level


def scoring_error_handler(request: Request, exc: ScoringHTTPError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code.value,
            "message": exc.detail,
            "detail": exc.detail,  # legacy field — see this module's docstring
            "ticker": exc.ticker,
            "status": exc.status_code,
        },
    )
