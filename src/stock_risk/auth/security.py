"""Password hashing and JWT issuance/verification."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from ..config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    """Issue a signed access token.

    [R2] shortened the lifetime from a hard-coded week to
    `settings.access_token_expire_minutes` (12h default). There is no
    revocation list — a stateless JWT is valid until it expires — so the
    lifetime *is* the blast radius of a leaked token, and a week was a long
    time to be unable to do anything about one. `iat` is included so
    should_refresh() can reason about age, not just remaining validity.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": subject, "iat": now, "exp": expire},
        settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> Optional[str]:
    """Return the token's subject (user email), or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def token_expires_at(token: str) -> Optional[datetime]:
    """The token's expiry, or None if it can't be read.

    Decoded WITHOUT expiry verification on purpose: this is used to decide
    whether a still-valid token is near enough to expiry to re-issue, and an
    already-expired token simply returns a past datetime that should_refresh
    handles — it must not raise.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    exp = payload.get("exp")
    return datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None


def should_refresh(token: str) -> bool:
    """Whether *token* is close enough to expiry to be re-issued.

    This is what makes the shorter lifetime invisible to an active user: while
    they keep using the app their token is silently replaced before it lapses,
    so shortening the window costs them nothing. An idle user's token expires
    on schedule, which is the security property being bought.
    """
    expires = token_expires_at(token)
    if expires is None:
        return False
    remaining = expires - datetime.now(timezone.utc)
    return remaining < timedelta(minutes=settings.access_token_refresh_within_minutes)


def handle_for(email: str) -> str:
    """Public-safe display name for community posts/leaderboard: the email's
    local-part plus a short deterministic disambiguator, so two different
    emails that share a local-part (alice@gmail.com / alice@yahoo.com) don't
    collide under the same public handle. Avoids adding a display_name column
    to User, which the app's create_all()-only schema setup can't retrofit
    onto an already-created table."""
    local = email.split("@", 1)[0]
    suffix = hashlib.sha256(email.encode("utf-8")).hexdigest()[:4]
    return f"{local}#{suffix}"


def display_name_for(nickname: Optional[str], email: str) -> str:
    """The public-facing name shown to other users: the chosen nickname if
    set, else the email-derived handle. The fallback covers rows created
    before nicknames existed and the seeded admin account (which has none),
    so their posts never render blank."""
    return nickname if nickname else handle_for(email)
