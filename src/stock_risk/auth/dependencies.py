"""FastAPI dependency for resolving the authenticated user from a Bearer token."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from .models import User
from .security import decode_access_token


def get_current_user(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    email = decode_access_token(authorization.removeprefix("Bearer "))
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.is_banned:
        # No token blacklist needed: every request already re-queries User
        # by email, so a ban takes effect on the very next authenticated
        # request regardless of how much of the token's lifetime remains.
        raise HTTPException(status_code=403, detail="This account has been suspended")
    return user


def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
) -> Optional[User]:
    """Like get_current_user, but returns None instead of raising when
    there's no/invalid token — for endpoints readable while logged out
    (e.g. the community feed) that still personalize the response
    (e.g. the viewer's own vote) when a valid token is present.

    A banned user also resolves to None here (not a raised error): ban
    means "can't act," not "can't view the same public content everyone
    else can view" — raising would turn an ordinary feed load into a
    broken page for someone whose token just happens to still be valid."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    email = decode_access_token(authorization.removeprefix("Bearer "))
    if email is None:
        return None
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None or user.is_banned:
        return None
    return user
