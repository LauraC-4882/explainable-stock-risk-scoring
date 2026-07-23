"""Tests for the admin migration helper, admin-seed idempotency, ban
enforcement, and the admin analytics/moderation endpoints. Same
in-memory-SQLite-per-test isolation as test_auth.py/test_community.py."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from stock_risk.api.app import app
from stock_risk.auth.admin import ensure_admin_user
from stock_risk.auth.models import User
from stock_risk.auth.security import verify_password
from stock_risk.db import get_session


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture()
def client(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(
    client, email="user@example.com", password="hunter2pass", nickname=None, consent=True
):
    if nickname is None:
        local = email.split("@")[0]
        nickname = local if len(local) >= 2 else local + "user"
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "nickname": nickname, "consent": consent},
    )


def _auth_headers(client, **kwargs):
    token = _register(client, **kwargs).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_admin(engine, email="admin@example.com", password="adminpass1"):
    with Session(engine) as session:
        ensure_admin_user(session, email, password)
    # Log in fresh so the token reflects the just-created row.
    from stock_risk.auth.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(email)}"}


# The `ensure_columns` helper this file used to test was retired in [R1] —
# schema changes now go through versioned Alembic migrations. Its replacement
# is covered by tests/test_migrations.py, which is strictly stronger: it
# asserts the models and the migration head cannot drift apart, that a
# downgrade/upgrade round trip is reversible, and that real seeded rows survive
# an upgrade — none of which ensure_columns could express.


# ── ensure_admin_user ────────────────────────────────────────────────────────


def test_ensure_admin_user_creates(engine):
    with Session(engine) as session:
        ensure_admin_user(session, "owner@example.com", "adminpass1")
        user = session.exec(select(User).where(User.email == "owner@example.com")).first()
        assert user is not None
        assert user.is_admin is True
        assert verify_password("adminpass1", user.hashed_password)


def test_ensure_admin_user_promotes_without_touching_password(engine):
    with Session(engine) as session:
        from stock_risk.auth.security import hash_password

        session.add(
            User(email="owner@example.com", hashed_password=hash_password("their-own-password"))
        )
        session.commit()

        ensure_admin_user(session, "owner@example.com", "a-totally-different-password")

        user = session.exec(select(User).where(User.email == "owner@example.com")).first()
        assert user.is_admin is True
        assert verify_password("their-own-password", user.hashed_password)
        assert not verify_password("a-totally-different-password", user.hashed_password)


def test_ensure_admin_user_stable_across_repeat_boots(engine):
    with Session(engine) as session:
        ensure_admin_user(session, "owner@example.com", "password-a")
        ensure_admin_user(session, "owner@example.com", "password-b")
        user = session.exec(select(User).where(User.email == "owner@example.com")).first()
        assert verify_password("password-a", user.hashed_password)
        assert not verify_password("password-b", user.hashed_password)


def test_ensure_admin_user_noop_when_unset(engine):
    with Session(engine) as session:
        ensure_admin_user(session, None, None)
        assert session.exec(select(User)).first() is None


def test_ensure_admin_user_rejects_short_password(engine):
    with Session(engine) as session:
        ensure_admin_user(session, "owner@example.com", "short")
        assert session.exec(select(User)).first() is None


def test_ensure_admin_user_unbans_the_admin_account(engine):
    with Session(engine) as session:
        ensure_admin_user(session, "owner@example.com", "adminpass1")
        user = session.exec(select(User).where(User.email == "owner@example.com")).first()
        user.is_banned = True
        session.add(user)
        session.commit()

        ensure_admin_user(session, "owner@example.com", "adminpass1")
        user = session.exec(select(User).where(User.email == "owner@example.com")).first()
        assert user.is_banned is False


# ── Ban enforcement ──────────────────────────────────────────────────────────


def _ban(engine, email):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        user.is_banned = True
        session.add(user)
        session.commit()


def test_banned_user_gets_403_on_me(client, engine):
    headers = _auth_headers(client, email="banned@example.com")
    _ban(engine, "banned@example.com")
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 403


def test_banned_user_cannot_login(client, engine):
    _register(client, email="banned@example.com", password="hunter2pass")
    _ban(engine, "banned@example.com")
    response = client.post(
        "/api/auth/login", json={"email": "banned@example.com", "password": "hunter2pass"}
    )
    assert response.status_code == 403


def test_banned_user_still_sees_public_feed(client, engine):
    headers = _auth_headers(client, email="banned@example.com")
    _ban(engine, "banned@example.com")
    response = client.get("/api/community/posts", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


# ── Admin guardrails ─────────────────────────────────────────────────────────


def test_non_admin_cannot_access_admin_routes(client):
    headers = _auth_headers(client)
    assert client.get("/api/admin/analytics/summary", headers=headers).status_code == 403
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.post("/api/admin/users/1/ban", headers=headers).status_code == 403


def test_anonymous_cannot_access_admin_routes(client):
    assert client.get("/api/admin/analytics/summary").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_admin_cannot_ban_self(client, engine):
    admin_headers = _make_admin(engine)
    admin_id = client.get("/api/auth/me", headers=admin_headers).json()["id"]
    response = client.post(f"/api/admin/users/{admin_id}/ban", headers=admin_headers)
    assert response.status_code == 403


def test_admin_cannot_ban_another_admin(client, engine):
    admin_headers = _make_admin(engine, email="owner@example.com")
    with Session(engine) as session:
        ensure_admin_user(session, "second-admin@example.com", "adminpass1")
        second_admin = session.exec(
            select(User).where(User.email == "second-admin@example.com")
        ).first()
        second_admin_id = second_admin.id

    response = client.post(f"/api/admin/users/{second_admin_id}/ban", headers=admin_headers)
    assert response.status_code == 403


def test_admin_ban_and_unban_user(client, engine):
    admin_headers = _make_admin(engine)
    user_headers = _auth_headers(client, email="user@example.com")
    user_id = client.get("/api/auth/me", headers=user_headers).json()["id"]

    ban = client.post(f"/api/admin/users/{user_id}/ban", headers=admin_headers)
    assert ban.status_code == 200
    assert ban.json()["is_banned"] is True

    # Idempotent on repeat.
    ban_again = client.post(f"/api/admin/users/{user_id}/ban", headers=admin_headers)
    assert ban_again.status_code == 200
    assert ban_again.json()["is_banned"] is True

    unban = client.post(f"/api/admin/users/{user_id}/unban", headers=admin_headers)
    assert unban.status_code == 200
    assert unban.json()["is_banned"] is False


def test_admin_ban_unknown_user_404s(client, engine):
    admin_headers = _make_admin(engine)
    assert client.post("/api/admin/users/9999/ban", headers=admin_headers).status_code == 404


def test_admin_list_users(client, engine):
    admin_headers = _make_admin(engine)
    _register(client, email="alice@example.com", nickname="AliceRisk")
    _register(client, email="bob@example.com", nickname="BobRisk")

    response = client.get("/api/admin/users", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3  # admin + alice + bob
    emails = {u["email"] for u in body["items"]}
    assert {"alice@example.com", "bob@example.com"} <= emails
    # The admin sees the public nickname alongside the email.
    nicknames = {u["nickname"] for u in body["items"]}
    assert {"AliceRisk", "BobRisk"} <= nicknames

    # Search matches nickname, not just email.
    by_email = client.get("/api/admin/users", params={"q": "alice@"}, headers=admin_headers)
    assert by_email.json()["total"] == 1
    by_nick = client.get("/api/admin/users", params={"q": "bobrisk"}, headers=admin_headers)
    assert by_nick.json()["total"] == 1


# ── Admin post moderation (extends the existing delete endpoint) ────────────


def test_admin_can_delete_any_post_and_it_cascades_votes(client, engine):
    admin_headers = _make_admin(engine)
    author_headers = _auth_headers(client, email="author@example.com")
    voter_headers = _auth_headers(client, email="voter@example.com")

    post_id = client.post(
        "/api/community/posts",
        json={"ticker": "AAPL", "market": "us", "body": "Ad: buy my course!"},
        headers=author_headers,
    ).json()["id"]
    client.post(
        f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=voter_headers
    )

    response = client.delete(f"/api/community/posts/{post_id}", headers=admin_headers)
    assert response.status_code == 204

    feed = client.get("/api/community/posts").json()
    assert feed["total"] == 0


def test_non_owner_non_admin_still_cannot_delete(client):
    author_headers = _auth_headers(client, email="author@example.com")
    other_headers = _auth_headers(client, email="other@example.com")
    post_id = client.post(
        "/api/community/posts",
        json={"ticker": "AAPL", "market": "us", "body": "A normal post."},
        headers=author_headers,
    ).json()["id"]
    assert (
        client.delete(f"/api/community/posts/{post_id}", headers=other_headers).status_code == 404
    )


def test_post_response_can_delete_reflects_admin_and_ownership(client, engine):
    admin_headers = _make_admin(engine)
    author_headers = _auth_headers(client, email="author@example.com")
    client.post(
        "/api/community/posts",
        json={"ticker": "AAPL", "market": "us", "body": "Some analysis."},
        headers=author_headers,
    )

    as_admin = client.get("/api/community/posts", headers=admin_headers).json()["items"][0]
    assert as_admin["can_delete"] is True
    assert as_admin["is_own_post"] is False

    as_author = client.get("/api/community/posts", headers=author_headers).json()["items"][0]
    assert as_author["can_delete"] is True
    assert as_author["is_own_post"] is True

    anonymous = client.get("/api/community/posts").json()["items"][0]
    assert anonymous["can_delete"] is False


# ── Analytics numeric-type safety ────────────────────────────────────────────


def test_admin_analytics_summary_shape_and_numeric_types(client, engine):
    """Defensive test per CLAUDE.md's standing numpy-scalar-leak rule: not
    because this codepath uses numpy, but because it's cheap insurance
    against a future aggregate query reintroducing that bug class
    unnoticed (see test_explain.py's equivalent regression test)."""
    admin_headers = _make_admin(engine)
    client.get("/api/score/AAPL")  # generate a couple of tracked page views
    client.get("/api/community/posts")

    response = client.get("/api/admin/analytics/summary", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["total_requests"], int)
    assert isinstance(body["unique_users"], int)
    assert len(body["hourly_histogram"]) == 24
    assert len(body["daily_counts"]) == 14
    for bucket in body["hourly_histogram"]:
        assert isinstance(bucket["hour"], int)
        assert isinstance(bucket["count"], int)
    for bucket in body["daily_counts"]:
        assert isinstance(bucket["date"], str)
        assert isinstance(bucket["count"], int)
    for entry in body["top_paths"]:
        assert isinstance(entry["count"], int)


def test_admin_authored_posts_carry_the_moderator_flag(client, engine):
    """author_is_admin drives the frontend's moderator badge. It must be True
    on every route that serialises a post (feed, create, vote) — a badge that
    appears in the feed but vanishes from the vote response would flicker off
    the moment a user votes."""
    admin_headers = _make_admin(engine, email="modbadge@example.com")
    member_headers = _auth_headers(client, email="plain-member@example.com")

    created = client.post(
        "/api/community/posts",
        json={"ticker": "AAPL", "market": "us", "body": "Volatility regime looks sticky."},
        headers=admin_headers,
    )
    assert created.status_code == 201
    assert created.json()["author_is_admin"] is True

    member_post = client.post(
        "/api/community/posts",
        json={"ticker": "AAPL", "market": "us", "body": "Watching the same setup."},
        headers=member_headers,
    )
    assert member_post.json()["author_is_admin"] is False

    feed = client.get("/api/community/posts", headers=member_headers).json()["items"]
    by_body = {p["body"]: p["author_is_admin"] for p in feed}
    assert by_body["Volatility regime looks sticky."] is True
    assert by_body["Watching the same setup."] is False

    voted = client.post(
        f"/api/community/posts/{created.json()['id']}/vote",
        json={"value": 1},
        headers=member_headers,
    )
    assert voted.json()["author_is_admin"] is True
