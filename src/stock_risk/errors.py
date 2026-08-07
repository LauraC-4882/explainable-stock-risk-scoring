"""The scoring failure taxonomy — one enum every layer agrees on.

Before this module, every way a score could fail collapsed into one of two
HTTP responses: a 404 carrying whatever `str(exc)` happened to say, or a 500
saying "Internal scoring error". Both are useless to the person who typed the
ticker. "Internal scoring error" in particular misattributes an upstream
outage, a brand-new IPO with 12 days of history, and a genuine bug in our own
code to the same (wrong) cause, and gives the user nothing to act on.

`ScoreErrorCode` is the contract. The backend classifies every exception on
the scoring path into exactly one code (see `classify_scoring_error`); the API
layer maps the code to a status and a safe English message
(`api/errors.py`); the frontend maps the same code to localized copy and
decides whether a retry button makes sense (`ui/web/src/api.js`). Adding a
failure mode means adding a member here and following the compile-ish errors
outward — not inventing a new bespoke string at a call site.

Two rules this taxonomy exists to enforce:

* **A raw exception message never reaches the user.** Codes carry a
  developer-facing message for the log; the user-facing copy is chosen from
  the code, never from `str(exc)`.
* **CALCULATION_FAILED is the only default.** An exception we did not
  anticipate is a bug until proven otherwise, and bugs get a full server-side
  traceback rather than being rebranded as somebody else's outage.
"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar, Optional


class ScoreErrorCode(str, Enum):
    """Why a scoring request could not be served.

    `str` mixin so the value serializes as a plain string in a JSON response
    body and compares equal to its own literal in tests and in the frontend's
    lookup table.
    """

    # The symbol does not resolve on any exchange we can reach. User-fixable:
    # check the spelling / exchange suffix.
    TICKER_NOT_FOUND = "TICKER_NOT_FOUND"

    # The symbol resolves, but there is not enough price history behind it to
    # rank today's metrics against (a recent IPO, or a name that trades so
    # rarely its sessions don't accumulate). Not retryable — it needs time to
    # pass, not another request.
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

    # Every price source for this ticker failed and no snapshot could stand in
    # — the provider is throttling or down. The ONLY code worth offering a
    # retry button for, because it is the only one where the same request can
    # plausibly succeed a minute later.
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"

    # We had data and could not turn it into a trustworthy number: NaN through
    # the pipeline, a model that would not converge, a division by zero, a
    # violated data contract, or an exception nobody anticipated. Always
    # logged with a full traceback server-side; never explained to the user
    # beyond "scoring failed for this stock".
    CALCULATION_FAILED = "CALCULATION_FAILED"

    # Data exists but stops well before today — the listing is suspended,
    # halted, or gone. Distinguished from TICKER_NOT_FOUND because the symbol
    # is real and the user's spelling is fine; nothing they retype will help.
    DELISTED = "DELISTED"


class ScoringError(Exception):
    """Base for failures that already know their own `ScoreErrorCode`.

    Subclasses also inherit from the built-in exception type callers outside
    the scoring path already catch (`ValueError` for "this data is wrong",
    `RuntimeError` for "this environment is broken"), so introducing this
    taxonomy did not change what any existing `except` clause catches.
    """

    code: ClassVar[ScoreErrorCode] = ScoreErrorCode.CALCULATION_FAILED

    def __init__(self, message: str, *, ticker: Optional[str] = None):
        super().__init__(message)
        self.ticker = ticker


class TickerNotFoundError(ScoringError, ValueError):
    """No source returned any rows for this symbol."""

    code = ScoreErrorCode.TICKER_NOT_FOUND


class InsufficientDataError(ScoringError, ValueError):
    """Fewer usable sessions than the scoring pipeline needs (see
    data/quality.py for the threshold and why it is where it is)."""

    code = ScoreErrorCode.INSUFFICIENT_DATA


class DelistedError(ScoringError, ValueError):
    """History exists but its most recent session is far enough in the past
    that the symbol is best described as suspended or delisted."""

    code = ScoreErrorCode.DELISTED


class CalculationFailedError(ScoringError):
    """The pipeline ran and could not produce a trustworthy number."""

    code = ScoreErrorCode.CALCULATION_FAILED


class UpstreamUnavailableError(ScoringError, RuntimeError):
    """Every price source for this ticker failed and no snapshot could stand
    in for them.

    Still subclasses RuntimeError, as it did when it lived in
    `data/fetcher.py` (which re-exports it), so callers that catch
    RuntimeError keep working unchanged.
    """

    code = ScoreErrorCode.UPSTREAM_UNAVAILABLE


def classify_scoring_error(exc: BaseException) -> ScoreErrorCode:
    """Map any exception raised on the scoring path to exactly one code.

    Order matters and is deliberate:

    1. Anything that declared its own code wins outright.
    2. Transport-level failures that escaped the fetcher's own handling (an
       akshare/Twelve Data timeout raised outside `fetch_history`, say) are an
       outage, not a bug.
    3. A bare `ValueError` reaching here comes from the fetch boundary, which
       raises it to mean "this symbol yielded nothing" — the behaviour the API
       already had (`except ValueError -> 404`) and the reason
       `TickerNotFoundError` subclasses ValueError rather than replacing it.
    4. Everything else is CALCULATION_FAILED: unrecognised means unanticipated
       means it gets a traceback, not a euphemism.
    """
    if isinstance(exc, ScoringError):
        return exc.code

    # Imported here rather than at module scope: this module is the one piece
    # of the taxonomy that the frontend contract, the tests and the API schema
    # all import, and it must stay cheap and dependency-free to import.
    import requests

    if isinstance(exc, (requests.exceptions.RequestException, TimeoutError, ConnectionError)):
        return ScoreErrorCode.UPSTREAM_UNAVAILABLE

    if isinstance(exc, ValueError):
        return ScoreErrorCode.TICKER_NOT_FOUND

    return ScoreErrorCode.CALCULATION_FAILED
