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
