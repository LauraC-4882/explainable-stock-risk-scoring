"""[R2] Audit log for security-relevant and privileged actions.

Distinct from `PageView` (analytics: every request, for a usage dashboard) and
from application logs (ephemeral, unstructured, gone on redeploy). This is the
answer to "who banned this user, and when?" — a durable, queryable record of
actions that change someone else's access or content.

Design choices worth stating:

* **Actor stored as an email string, not a FK.** An audit row must survive the
  actor's account being deleted; a foreign key would either block the delete or
  cascade the evidence away. The whole point of an audit trail is that it
  outlives the thing it describes.
* **Append-only by convention, enforced by having no update/delete path.**
  Nothing in the codebase mutates an AuditLog row.
* **Failures are recorded too**, not just successes. A hundred failed admin
  attempts is the signal you actually want; logging only what succeeded hides
  exactly the reconnaissance phase you'd want to catch.
* **Never blocks the request.** Same contract as ModelMonitor.record() — an
  audit write that fails is logged loudly but does not turn a successful ban
  into a 500.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlmodel import Field, Session, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditAction:
    """Action names, as constants so a typo is an ImportError not a silently
    unqueryable row."""

    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGIN_LOCKED = "auth.login.locked"
    REGISTER = "auth.register"
    USER_BANNED = "admin.user.ban"
    USER_UNBANNED = "admin.user.unban"
    POST_DELETED = "moderation.post.delete"
    REPORT_DISMISSED = "moderation.report.dismiss"
    ADMIN_ACCESS_DENIED = "admin.access.denied"
    RATE_LIMITED = "security.rate_limited"


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str = Field(index=True)
    # Email rather than user_id — see module docstring on outliving the actor.
    actor_email: Optional[str] = Field(default=None, index=True)
    # What was acted upon: a user email, a post id, a ticker. Free-form because
    # the target's type varies by action and a polymorphic FK would add
    # complexity for no query benefit at this scale.
    target: Optional[str] = Field(default=None, index=True)
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    success: bool = True
    created_at: datetime = Field(default_factory=_utc_now, index=True)


def record_audit(
    session: Session,
    action: str,
    *,
    actor_email: Optional[str] = None,
    target: Optional[str] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
    success: bool = True,
) -> None:
    """Append an audit row. Never raises — see the module docstring.

    Commits its own row rather than joining the caller's transaction: an audit
    entry describing an attempt must persist even when the attempt itself is
    rolled back, which is precisely the interesting case for a failure.
    """
    try:
        session.add(
            AuditLog(
                action=action,
                actor_email=actor_email,
                target=target,
                detail=detail,
                ip_address=ip_address,
                success=success,
            )
        )
        session.commit()
    except Exception as exc:
        logger.exception(f"[audit] failed to record {action} (request still served): {exc}")
        try:
            session.rollback()
        except Exception:
            # Rollback on an already-broken session is best-effort; the caller's
            # request must still complete either way.
            pass


def client_ip(request) -> Optional[str]:
    """Best-effort client IP for an audit row.

    Same proxy-trust rule as ratelimit.client_key: an untrusted
    X-Forwarded-For is attacker-controlled, and recording a forged IP in an
    audit log is worse than recording none — it looks authoritative.
    """
    from ..config import settings

    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client else None
