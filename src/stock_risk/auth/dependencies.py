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
    return user


def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
) -> Optional[User]:
    """Like get_current_user, but returns None instead of raising when
    there's no/invalid token — for endpoints readable while logged out
    (e.g. the community feed) that still personalize the response
    (e.g. the viewer's own vote) when a valid token is present."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    email = decode_access_token(authorization.removeprefix("Bearer "))
    if email is None:
        return None
    return session.exec(select(User).where(User.email == email)).first()
