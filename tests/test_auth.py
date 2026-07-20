"""Tests for auth registration/login and per-user watchlist CRUD.

Each test gets a fresh in-memory SQLite DB via a dependency override on
get_session, isolated from both the real data/app.db and other tests.
"""

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


def test_register_returns_token(client):
    response = _register(client)
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_register_duplicate_email_rejected(client):
    _register(client)
    assert _register(client).status_code == 409


def test_register_short_password_rejected(client):
    assert _register(client, password="short").status_code == 422


def test_login_success(client):
    _register(client)
    response = client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "hunter2pass"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password_rejected(client):
    _register(client)
    response = client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "wrong"}
    )
    assert response.status_code == 401


def test_login_unknown_email_rejected(client):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "hunter2pass"}
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_returns_current_user(client):
    headers = _auth_headers(client)
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["created_at"]  # populated, not null — Profile panel's "Member since"


def test_watchlist_requires_auth(client):
    assert client.get("/api/watchlist").status_code == 401


def test_watchlist_add_list_delete(client):
    headers = _auth_headers(client)

    add = client.post(
        "/api/watchlist", json={"ticker": "aapl", "market": "us"}, headers=headers
    )
    assert add.status_code == 201
    assert add.json()["ticker"] == "AAPL"  # normalized to uppercase

    assert len(client.get("/api/watchlist", headers=headers).json()) == 1

    item_id = add.json()["id"]
    assert client.delete(f"/api/watchlist/{item_id}", headers=headers).status_code == 204
    assert client.get("/api/watchlist", headers=headers).json() == []


def test_watchlist_delete_missing_item_404s(client):
    headers = _auth_headers(client)
    assert client.delete("/api/watchlist/999", headers=headers).status_code == 404


def test_watchlist_add_duplicate_ticker_is_idempotent(client):
    headers = _auth_headers(client)
    first = client.post(
        "/api/watchlist", json={"ticker": "AAPL", "market": "us"}, headers=headers
    ).json()
    second = client.post(
        "/api/watchlist", json={"ticker": "AAPL", "market": "us"}, headers=headers
    ).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/watchlist", headers=headers).json()) == 1


def test_watchlist_cross_user_isolation(client):
    headers_a = _auth_headers(client, email="a@example.com")
    headers_b = _auth_headers(client, email="b@example.com")

    added = client.post(
        "/api/watchlist", json={"ticker": "AAPL", "market": "us"}, headers=headers_a
    ).json()

    assert client.get("/api/watchlist", headers=headers_b).json() == []
    assert (
        client.delete(f"/api/watchlist/{added['id']}", headers=headers_b).status_code == 404
    )
    # a's item must survive b's attempted delete
    assert len(client.get("/api/watchlist", headers=headers_a).json()) == 1
