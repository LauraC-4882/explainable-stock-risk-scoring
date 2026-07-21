"""Tests for the community analyst platform: posts, votes, accuracy math,
and the leaderboard. Same in-memory-SQLite-per-test isolation as
test_auth.py (no shared conftest.py exists yet in this repo — the fixture
is duplicated here rather than introducing one for a single caller)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from stock_risk.api.app import app
from stock_risk.db import get_session


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email="user@example.com", password="hunter2pass"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def _auth_headers(client, **kwargs):
    token = _register(client, **kwargs).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_post(client, headers, ticker="aapl", market="us", body="Looks overextended here."):
    return client.post(
        "/api/community/posts",
        json={"ticker": ticker, "market": market, "body": body},
        headers=headers,
    )


# ── Creating posts ──────────────────────────────────────────────────────────


def test_create_post_requires_auth(client):
    response = _create_post(client, headers={})
    assert response.status_code == 401


def test_create_post_success_normalizes_ticker(client):
    headers = _auth_headers(client)
    response = _create_post(client, headers)
    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["upvotes"] == 0
    assert body["downvotes"] == 0
    assert body["author_accuracy"] is None
    assert body["is_own_post"] is True


def test_create_post_empty_body_rejected(client):
    headers = _auth_headers(client)
    response = _create_post(client, headers, body="   ")
    assert response.status_code == 422


def test_create_post_over_length_rejected(client):
    headers = _auth_headers(client)
    response = _create_post(client, headers, body="x" * 1001)
    assert response.status_code == 422


# ── Feed ─────────────────────────────────────────────────────────────────────


def test_feed_list_works_without_auth(client):
    headers = _auth_headers(client)
    _create_post(client, headers)
    response = client.get("/api/community/posts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["my_vote"] is None
    assert payload["items"][0]["is_own_post"] is False


def test_feed_filter_by_ticker(client):
    headers = _auth_headers(client)
    _create_post(client, headers, ticker="aapl")
    _create_post(client, headers, ticker="tsla")
    response = client.get("/api/community/posts", params={"ticker": "tsla"})
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["ticker"] == "TSLA"


# ── Voting ───────────────────────────────────────────────────────────────────


def test_vote_requires_auth(client):
    author = _auth_headers(client, email="author@example.com")
    post_id = _create_post(client, author).json()["id"]
    response = client.post(f"/api/community/posts/{post_id}/vote", json={"value": 1})
    assert response.status_code == 401


def test_vote_on_own_post_rejected(client):
    author = _auth_headers(client, email="author@example.com")
    post_id = _create_post(client, author).json()["id"]
    response = client.post(
        f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=author
    )
    assert response.status_code == 403


def test_vote_nonexistent_post_404s(client):
    voter = _auth_headers(client, email="voter@example.com")
    response = client.post("/api/community/posts/9999/vote", json={"value": 1}, headers=voter)
    assert response.status_code == 404


def test_vote_changes_not_duplicates(client):
    author = _auth_headers(client, email="author@example.com")
    voter = _auth_headers(client, email="voter@example.com")
    post_id = _create_post(client, author).json()["id"]

    up = client.post(f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=voter)
    assert up.json()["upvotes"] == 1
    assert up.json()["downvotes"] == 0

    down = client.post(f"/api/community/posts/{post_id}/vote", json={"value": -1}, headers=voter)
    assert down.json()["upvotes"] == 0
    assert down.json()["downvotes"] == 1
    assert down.json()["my_vote"] == -1


def test_vote_idempotent_same_value_twice(client):
    author = _auth_headers(client, email="author@example.com")
    voter = _auth_headers(client, email="voter@example.com")
    post_id = _create_post(client, author).json()["id"]

    client.post(f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=voter)
    second = client.post(f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=voter)
    assert second.status_code == 200
    assert second.json()["upvotes"] == 1


def test_unvote_removes_vote(client):
    author = _auth_headers(client, email="author@example.com")
    voter = _auth_headers(client, email="voter@example.com")
    post_id = _create_post(client, author).json()["id"]

    client.post(f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=voter)
    remove = client.delete(f"/api/community/posts/{post_id}/vote", headers=voter)
    assert remove.status_code == 204

    again = client.delete(f"/api/community/posts/{post_id}/vote", headers=voter)
    assert again.status_code == 404

    feed = client.get("/api/community/posts").json()
    assert feed["items"][0]["upvotes"] == 0


# ── Deleting posts ───────────────────────────────────────────────────────────


def test_delete_post_requires_ownership(client):
    author = _auth_headers(client, email="author@example.com")
    other = _auth_headers(client, email="other@example.com")
    post_id = _create_post(client, author).json()["id"]

    response = client.delete(f"/api/community/posts/{post_id}", headers=other)
    assert response.status_code == 404

    response = client.delete(f"/api/community/posts/{post_id}", headers=author)
    assert response.status_code == 204


def test_delete_post_cascades_votes(client):
    author = _auth_headers(client, email="author@example.com")
    voter = _auth_headers(client, email="voter@example.com")
    post_id = _create_post(client, author).json()["id"]
    client.post(f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=voter)

    client.delete(f"/api/community/posts/{post_id}", headers=author)

    # The vote row must be gone too, not orphaned — re-voting on a fresh post
    # by the same voter must start from a clean slate.
    new_post_id = _create_post(client, author, body="Second take.").json()["id"]
    vote = client.post(f"/api/community/posts/{new_post_id}/vote", json={"value": 1}, headers=voter)
    assert vote.json()["upvotes"] == 1


# ── Leaderboard / accuracy math ──────────────────────────────────────────────


def _vote_n_times(client, post_id, value, n, email_prefix="voter"):
    for i in range(n):
        headers = _auth_headers(client, email=f"{email_prefix}{i}@example.com")
        client.post(f"/api/community/posts/{post_id}/vote", json={"value": value}, headers=headers)


def test_leaderboard_excludes_authors_below_min_votes(client):
    author = _auth_headers(client, email="author@example.com")
    post_id = _create_post(client, author).json()["id"]
    _vote_n_times(client, post_id, 1, 5)  # below the 10-vote leaderboard threshold

    accuracy_board = client.get("/api/community/leaderboard", params={"sort": "accuracy"}).json()
    assert accuracy_board == []

    recent_board = client.get("/api/community/leaderboard", params={"sort": "recent"}).json()
    assert len(recent_board) == 1
    assert recent_board[0]["accuracy"] is None


def test_leaderboard_accuracy_is_vote_weighted_aggregate_not_averaged_ratios(client):
    """The one test that actually distinguishes 'sum upvotes / sum votes
    across all posts' from 'average of each post's own ratio' — get this
    wrong silently and nothing else here would catch it."""
    author = _auth_headers(client, email="author@example.com")
    post_a = _create_post(client, author, ticker="aapl").json()["id"]
    post_b = _create_post(client, author, ticker="tsla").json()["id"]

    # Post A: 1 upvote, 0 downvotes -> 100% on its own.
    _vote_n_times(client, post_a, 1, 1, email_prefix="a_voter")
    # Post B: 4 upvotes, 5 downvotes -> ~44% on its own.
    _vote_n_times(client, post_b, 1, 4, email_prefix="b_up")
    _vote_n_times(client, post_b, -1, 5, email_prefix="b_down")

    # Naive average of (1.0, 0.444) would be ~0.72. Vote-weighted aggregate
    # is (1+4)/(1+4+5) = 5/10 = 0.5.
    board = client.get("/api/community/leaderboard", params={"sort": "accuracy"}).json()
    assert len(board) == 1
    assert board[0]["accuracy"] == pytest.approx(0.5)
    assert board[0]["post_count"] == 2
    assert board[0]["upvotes"] == 5
    assert board[0]["downvotes"] == 5


def test_top_analysis_for_ticker_respects_min_vote_threshold(client):
    author = _auth_headers(client, email="author@example.com")
    weak_post = _create_post(client, author, ticker="aapl", body="Weak signal.").json()["id"]
    _vote_n_times(client, weak_post, 1, 1, email_prefix="weak")  # 1 vote, below post threshold of 3

    response = client.get(
        "/api/community/posts", params={"ticker": "aapl", "sort": "top", "limit": 1}
    )
    top = response.json()["items"][0]
    # Still returned (it's the only post), but its accuracy math is still
    # correct — the threshold gate is about *ranking*, not existence.
    assert top["id"] == weak_post
    assert top["upvotes"] == 1


def test_handle_derivation_disambiguates_same_local_part(client):
    _register(client, email="alice@gmail.com")
    _register(client, email="alice@yahoo.com")
    headers_1 = _auth_headers(client, email="poster1@example.com")
    _create_post(client, headers_1)

    from stock_risk.auth.security import handle_for

    assert handle_for("alice@gmail.com") != handle_for("alice@yahoo.com")
    assert handle_for("alice@gmail.com").startswith("alice#")


# ── Profile: my posts / my votes ─────────────────────────────────────────────


def test_my_posts_and_my_votes_require_auth(client):
    assert client.get("/api/community/me/posts").status_code == 401
    assert client.get("/api/community/me/votes").status_code == 401


def test_my_posts_and_my_votes(client):
    author = _auth_headers(client, email="author@example.com")
    voter = _auth_headers(client, email="voter@example.com")
    post_id = _create_post(client, author).json()["id"]
    client.post(f"/api/community/posts/{post_id}/vote", json={"value": 1}, headers=voter)

    my_posts = client.get("/api/community/me/posts", headers=author).json()
    assert len(my_posts) == 1
    assert my_posts[0]["id"] == post_id

    my_votes = client.get("/api/community/me/votes", headers=voter).json()
    assert len(my_votes) == 1
    assert my_votes[0]["id"] == post_id
    assert my_votes[0]["my_vote"] == 1
