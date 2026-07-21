"""Password hashing and JWT issuance/verification."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from ..config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": subject, "exp": expire}, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Return the token's subject (user email), or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


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
