"""Site-owner admin: idempotent account seeding + the require_admin gate."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException
from loguru import logger
from sqlmodel import Session, select

from .dependencies import get_current_user
from .models import User
from .security import hash_password

MIN_PASSWORD_LENGTH = 8  # matches /api/auth/register's own rule


def ensure_admin_user(
    session: Session, admin_email: Optional[str], admin_password: Optional[str]
) -> None:
    """Create-or-promote the site owner's admin account, called on every
    app boot rather than a one-off seed script — a one-off would vanish
    along with data/app.db on the next Render redeploy (see db.py). Takes
    the email/password as explicit args (not read from the settings
    singleton internally) so tests can call this directly with arbitrary
    values, with no env-var monkeypatch gymnastics against a singleton
    constructed once at import time.

    Behavior, in order:
    1. Either value unset -> log once, no-op. Admin features are simply
       unavailable until both are configured, same treatment as an unset
       JWT_SECRET_KEY elsewhere in this app.
    2. Password shorter than MIN_PASSWORD_LENGTH -> log an error, skip
       (rather than seeding a known-weak admin account).
    3. No existing row for that email -> create it with is_admin=True.
    4. Existing row, not yet admin -> promote is_admin=True. Never touches
       hashed_password: a user who already registered with this email
       keeps the password they chose.
    5. Existing row, already admin -> also force is_banned=False. This app
       has no password-reset flow and, by design, only one admin account
       exists — self-healing a stray is_banned=True on it here is the only
       recovery path that exists.
    Never logs the password itself, only the outcome.
    """
    if not admin_email or not admin_password:
        logger.warning(
            "ADMIN_EMAIL/ADMIN_PASSWORD not set — no admin account will exist "
            "until both are configured."
        )
        return
    if len(admin_password) < MIN_PASSWORD_LENGTH:
        logger.error(
            f"ADMIN_PASSWORD is shorter than {MIN_PASSWORD_LENGTH} characters — "
            "refusing to seed a known-weak admin account. Set a longer ADMIN_PASSWORD."
        )
        return

    user = session.exec(select(User).where(User.email == admin_email)).first()
    if user is None:
        session.add(
            User(email=admin_email, hashed_password=hash_password(admin_password), is_admin=True)
        )
        session.commit()
        logger.warning(f"[admin] created admin account for {admin_email}")
        return

    changed = False
    if not user.is_admin:
        user.is_admin = True
        changed = True
        logger.warning(f"[admin] promoted existing account {admin_email} to admin")
    if user.is_banned:
        user.is_banned = False
        changed = True
        logger.warning(f"[admin] un-banned admin account {admin_email}")
    if changed:
        session.add(user)
        session.commit()


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
