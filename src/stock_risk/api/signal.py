"""Public, read-only signal API — the one integration surface for sibling apps.

`GET /api/v1/signal/{ticker}` and `GET /api/v1/signal?tickers=...` hand a
compact, versioned view of the risk scorecard to another service (Portfolio
Lab) over plain HTTP. Nothing here is a new computation: every number comes
out of the same `RiskScorer.score()` result the web UI renders, through the
same `_score_ticker` funnel in api/app.py (cache, single-flight, monitoring,
score-snapshot upsert), and is then *reshaped* by `build_signal`. The routes
themselves are declared in api/app.py next to the scoring routes they reuse;
this module holds everything that does not need the app object.

Design choices worth stating once:

* **Numbers travel as strings with fixed decimals.** A float on the wire is
  re-parsed by whatever the consumer's JSON library does with it, and two
  services comparing "the same" score can disagree in the last bit. A string
  is the same string everywhere. `score` and `history_days` are integers by
  contract and stay integers.
* **Versioned.** `schema_version` is bumped whenever a field is renamed,
  removed, or changes meaning; adding an optional field does not bump it.
* **Errors are the existing taxonomy, untouched.** `ScoreErrorCode` is what
  every other route answers with, and the codes a consumer switches on must
  be the same ones — TICKER_NOT_FOUND (404), INSUFFICIENT_DATA (422),
  UPSTREAM_UNAVAILABLE (503), plus DELISTED (422) and CALCULATION_FAILED
  (500). No `str(exc)` reaches the body; api/errors.py owns the copy.
* **No investment advice, by construction.** The payload is measurements and
  a model probability. It carries no label like "high" or "low", no
  direction, no suggested action; the README section documents that scores
  are relative to each stock's own history and are not investment advice,
  and tests/test_signal_api.py runs the product's advice-language guard over
  this route's copy.
"""

from __future__ import annotations

import hmac
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import Header, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth.models import SignalSnapshot
from ..config import settings
from ..security import RateLimiter, client_ip

SIGNAL_SCHEMA_VERSION = "1.0"
MAX_BATCH_TICKERS = 20

# Public names for the five percentile-composite categories. The internal
# names are kept short because they are dict keys in a dozen places; the
# public ones say what the category measures to someone who has never read
# risk_categories.py.
FACTOR_NAMES: dict[str, str] = {
    "volatility": "volatility",
    "tail": "tail_risk",
    "drawdown": "drawdown",
    "sensitivity": "market_sensitivity",
    "liquidity": "liquidity",
}

# The regime is published under the contract's names, which are the scorer's
# own (risk_categories.regime_for_vix). Mapped explicitly rather than passed
# through so a future rename inside the scorer cannot silently change the
# wire value. "not_available" — the scorer's answer for every non-US ticker,
# because the VIX is a US instrument — has no honest member of the three, so
# it is null rather than dressed up as "calm".
REGIME_NAMES: dict[str, str] = {"calm": "calm", "elevated": "elevated", "panic": "panic"}

FACTOR_DECIMALS = 2  # percentiles, 0-100
SHAP_DECIMALS = 4  # log-odds contributions
PROBABILITY_DECIMALS = 4

# Cache lifetime advertised to consumers. One hour, not one day: a snapshot is
# keyed on the UTC day, and a consumer whose local cache expires at the day
# boundary would otherwise serve yesterday's number well into today.
CACHE_CONTROL = "max-age=3600"


# ── Response contract ────────────────────────────────────────────────────────


class SignalFactors(BaseModel):
    """Category percentiles within the stock's own history, as strings with
    two decimals, or null when a category could not be scored."""

    volatility: Optional[str] = None
    tail_risk: Optional[str] = None
    drawdown: Optional[str] = None
    market_sensitivity: Optional[str] = None
    liquidity: Optional[str] = None


class SignalShap(BaseModel):
    """Per-category sums of the ML leg's SHAP contributions (log-odds units,
    four decimals). Additive: the six sum to the model's total shift from its
    base rate. `other` holds features outside the five categories (momentum,
    Sharpe/Sortino), kept so the decomposition stays complete."""

    volatility: str
    tail_risk: str
    drawdown: str
    market_sensitivity: str
    liquidity: str
    other: str


class SignalResponse(BaseModel):
    """One ticker's public signal, schema_version "1.0".

    Every non-integer number is a string with a fixed number of decimals:
    `factors` two (percentiles, 0-100), `shap` four (log-odds contributions),
    `ml_drawdown_prob_20d` four (a probability, 0-1). `score` and
    `history_days` are integers. `shap.market_sensitivity` and
    `shap.liquidity` are always "0.0000" because no ML feature is mapped to
    those categories; the six `shap` values remain an additive decomposition
    of the model's log-odds shift.
    """

    schema_version: str
    ticker: str
    market: str
    # Trading date of the last bar the score is computed from (YYYY-MM-DD).
    as_of: str
    # When the score was computed, ISO-8601 UTC with a trailing "Z".
    computed_at: str
    # The fused risk score, rounded to an integer 0-100.
    score: int
    regime: Optional[Literal["calm", "elevated", "panic"]] = None
    factors: SignalFactors
    # Null when the ML leg is not serving (ENABLE_ML=0 or no artefact).
    shap: Optional[SignalShap] = None
    # Calibrated probability, 0-1 as a string with four decimals, of a >10%
    # drawdown within the next 20 trading days. Null when the ML leg is off.
    ml_drawdown_prob_20d: Optional[str] = None
    model_version: str
    # Sessions the percentile ranking was computed over.
    history_days: Optional[int] = None


class SignalError(BaseModel):
    ticker: str
    code: str


class SignalBatchResponse(BaseModel):
    results: list[SignalResponse]
    errors: list[SignalError]


# ── Scorecard -> signal ──────────────────────────────────────────────────────


def _fixed(value, decimals: int) -> Optional[str]:
    """`value` as a fixed-decimal string, or None for None/NaN/non-numeric.

    Goes through `float()` first, so a stray numpy scalar is a native float
    before it is formatted — the same rule CLAUDE.md §3.5 applies at every
    response boundary.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return f"{number:.{decimals}f}"


def build_signal(result: dict, *, model_version: str) -> dict:
    """Reshape one `RiskScorer.score()` result into the public signal body.

    Pure: no I/O, no clock. `computed_at` is the scorecard's own timestamp,
    not `now()`, so a signal served from the daily snapshot says when its
    number was actually produced.
    """
    breakdown = result.get("risk_breakdown") or {}
    factors = {
        public: _fixed((breakdown.get(internal) or {}).get("score"), FACTOR_DECIMALS)
        for internal, public in FACTOR_NAMES.items()
    }

    explanation = result.get("ml_drawdown_explanation") or {}
    contributions = explanation.get("category_contributions")
    shap = None
    if contributions is not None:
        shap = {
            public: _fixed(contributions.get(internal, 0.0), SHAP_DECIMALS)
            for internal, public in FACTOR_NAMES.items()
        }
        shap["other"] = _fixed(contributions.get("other", 0.0), SHAP_DECIMALS)

    # The scorecard carries the probability as a percentage (P x 100, one
    # decimal) because that is how the UI shows it; a machine consumer gets
    # the probability itself.
    probability = result.get("ml_drawdown_probability")
    ml_prob = None
    if probability is not None:
        ml_prob = _fixed(float(probability) / 100.0, PROBABILITY_DECIMALS)

    regime_raw = (result.get("market_regime") or {}).get("regime")
    market_raw = (result.get("market_regime") or {}).get("market") or "us"
    history_days = result.get("history_days")

    return {
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "ticker": str(result["ticker"]).upper(),
        "market": str(market_raw).upper(),
        "as_of": result.get("as_of"),
        "computed_at": result["timestamp"],
        "score": int(round(float(result["risk_score"]))),
        "regime": REGIME_NAMES.get(regime_raw),
        "factors": factors,
        "shap": shap,
        "ml_drawdown_prob_20d": ml_prob,
        "model_version": model_version,
        "history_days": None if history_days is None else int(history_days),
    }


def resolve_model_version(model, *, model_dir: Path, repo_root: Path) -> str:
    """A stable identifier for the ML leg answering requests.

    Preference order: the governance registry's champion version (the name a
    human would recognise), else the artefact's content hash (what is actually
    on disk, whether or not anyone registered it), else "unversioned" when the
    artefact cannot be read. "unavailable" when no model is loaded at all —
    then `shap` and `ml_drawdown_prob_20d` are null too, and the consumer can
    see why.

    Computed once at startup by the caller: every input is fixed at deploy
    time, and hashing the artefact per request would be pointless work.
    """
    if model is None:
        return "unavailable"

    try:
        from ..governance.registry import ModelRegistry

        registry_path = repo_root / "models" / "registry.json"
        if registry_path.exists():
            champion = ModelRegistry(registry_path).champion("downside_risk")
            if champion is not None:
                return f"{champion.name}@{champion.version}"
    except Exception as exc:
        # A malformed registry must not take the signal endpoint down with it;
        # the artefact hash below is still a truthful identifier.
        logger.warning(f"[signal] registry unreadable, falling back to artefact hash: {exc}")

    from ..governance.snapshot import _sha256

    digest = _sha256(Path(model_dir) / "downside_risk_xgb.joblib")
    return f"sha256:{digest[:12]}" if digest else "unversioned"


# ── Auth ─────────────────────────────────────────────────────────────────────


def require_signal_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
) -> None:
    """Open when SIGNAL_API_KEYS is unset; otherwise the header must match one.

    Constant-time comparison against every configured key rather than an early
    `in` check, so timing does not reveal which prefix of a key was right. One
    401 message for "missing" and "wrong": telling a caller which of the two it
    was is a small help to a legitimate integrator and a larger one to anyone
    guessing.
    """
    keys = settings.signal_api_key_list
    if not keys:
        return
    provided = (x_api_key or "").encode()
    if not any(hmac.compare_digest(provided, key.encode()) for key in keys):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Rate limiting ────────────────────────────────────────────────────────────

# A dedicated bucket, keyed by IP only (there is no user on this surface).
# Sustained rate is the per-minute allowance spread across the minute; burst
# equals the allowance so an idle client can spend a full minute's worth at
# once, which is what a "60/min" limit means to the caller reading the docs.
_signal_limiter = RateLimiter(
    rate=settings.signal_rate_limit_per_minute / 60.0,
    burst=float(settings.signal_rate_limit_per_minute),
)


def signal_limiter() -> RateLimiter:
    return _signal_limiter


def enforce_signal_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 with Retry-After once the per-IP bucket is dry.

    Honours `settings.rate_limit_enabled` like the general middleware, so the
    test suite's default-off switch covers this bucket too (tests/conftest.py
    also resets it between tests). The general middleware charges this route
    nothing — see `_ENDPOINT_COSTS` in api/app.py — so a batch of twenty
    tickers is one unit here and nowhere else.
    """
    if not settings.rate_limit_enabled:
        return
    key = f"ip:{client_ip(request) or 'unknown'}"
    allowed, retry_after = _signal_limiter.check(key, cost=1.0)
    if allowed:
        return
    logger.warning(f"[signal] rate limited {key} on {request.url.path}")
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded. Please slow down.",
        headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
    )


# ── Daily snapshot cache ─────────────────────────────────────────────────────


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def cached_signal(session: Session, ticker: str, today: date) -> Optional[dict]:
    """Today's stored payload for *ticker*, or None.

    Only a row captured *today* counts; yesterday's row is left alone and
    overwritten by the next computation rather than served. The stored text
    is decoded and returned as-is — it is the same dict `build_signal` made.
    """
    row = session.exec(
        select(SignalSnapshot).where(
            SignalSnapshot.ticker == ticker,
            SignalSnapshot.captured_on == today,
            SignalSnapshot.schema_version == SIGNAL_SCHEMA_VERSION,
        )
    ).first()
    if row is None:
        return None
    try:
        return json.loads(row.payload)
    except json.JSONDecodeError as exc:
        # A corrupt row is recomputed and overwritten, never served.
        logger.warning(f"[signal] unreadable snapshot for {ticker} on {today}: {exc}")
        return None


def store_signal(session: Session, payload: dict, today: date) -> None:
    """Upsert today's row for the payload's ticker (one per ticker per day)."""
    ticker = payload["ticker"]
    as_of = date.fromisoformat(payload["as_of"]) if payload.get("as_of") else today
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    existing = session.exec(
        select(SignalSnapshot).where(
            SignalSnapshot.ticker == ticker, SignalSnapshot.captured_on == today
        )
    ).first()
    if existing is not None:
        existing.market = payload["market"]
        existing.as_of = as_of
        existing.schema_version = payload["schema_version"]
        existing.payload = encoded
        existing.computed_at = datetime.now(timezone.utc)
        session.add(existing)
    else:
        session.add(
            SignalSnapshot(
                ticker=ticker,
                market=payload["market"],
                as_of=as_of,
                schema_version=payload["schema_version"],
                payload=encoded,
                captured_on=today,
            )
        )
    session.commit()


def parse_batch_tickers(raw: str) -> list[str]:
    """Split, trim, upper-case and de-duplicate a `tickers=` query value.

    Request-shape problems are plain 422s with fixed text, the same category
    as FastAPI's own validation errors — not scoring outcomes, so none of the
    five ScoreErrorCodes is stretched to cover them.
    """
    seen: list[str] = []
    for part in raw.split(","):
        ticker = part.strip().upper()
        if ticker and ticker not in seen:
            seen.append(ticker)
    if not seen:
        raise HTTPException(status_code=422, detail="Provide at least one ticker")
    if len(seen) > MAX_BATCH_TICKERS:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_BATCH_TICKERS} tickers per request",
        )
    return seen
