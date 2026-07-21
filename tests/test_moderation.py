"""Tests for the rule-based post filter and the report/admin-review flow.

The false-positive tests are the important ones: the filter must never
block entity/event vocabulary ("Taiwan", "election", "war", "sell-off"),
because geopolitical and macro events ARE risk analysis on this platform.
Same in-memory-SQLite-per-test isolation as the other API test modules.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from stock_risk.api.app import app
from stock_risk.auth.admin import ensure_admin_user
from stock_risk.db import get_session
from stock_risk.moderation import check_post_body

# ── Filter unit tests: legitimate analysis must pass ─────────────────────────

LEGITIMATE_POSTS = [
    # Entity/event words are core vocabulary, not violations.
    "TSMC faces real geopolitical risk from Taiwan Strait tensions — vol regime shifted.",
    "Election uncertainty is lifting implied volatility across the board this quarter.",
    "The war in Ukraine and new sanctions keep energy names in a high-beta regime.",
    "Trade war escalation would hit semiconductor supply chains hardest.",
    "台积电面临台湾地缘政治风险，选举不确定性正在推高波动率。",
    "贸易战升级会冲击半导体板块，关税消息是主要的尾部风险来源。",
    # Market verbs in analytical (non-directive) use.
    "Heavy sell-off yesterday; RSI now deep in oversold territory.",
    "Sell pressure dominated the tape, but buying interest returned near the close.",
    "Sellers outnumbered buyers 3:1 during the drawdown.",
    "近期卖出压力明显，买入意愿低迷，流动性指标走弱。",
    # Product names without contact-info structure.
    "Tencent's WeChat payments business is the main revenue driver to watch.",
    "Telegram and WhatsApp adoption trends matter for Meta's engagement risk.",
]


@pytest.mark.parametrize("body", LEGITIMATE_POSTS)
def test_legitimate_analysis_is_never_blocked(body):
    assert check_post_body(body) is None, f"false positive on: {body!r}"


# ── Filter unit tests: violations are caught ─────────────────────────────────

VIOLATIONS = [
    ("Strong buy here, price target $500 by December!", "trading_directive"),
    ("Buy now before earnings, guaranteed profit, can't lose.", "trading_directive"),
    ("This is going to the moon, all in!", "trading_directive"),
    ("建议买入，目标价500，稳赚不赔！", "trading_directive"),
    ("赶紧上车，必涨，跟我买就对了。", "trading_directive"),
    ("DM me for paid signals, join my telegram group t.me/stocktips", "solicitation"),
    ("Great analysis! wechat: abc123 for more", "solicitation"),
    ("加我微信详聊，有付费群带你操作。", "solicitation"),
    ("你就是个傻逼，懂什么风险分析。", "abuse"),
]


@pytest.mark.parametrize("body,expected_category", VIOLATIONS)
def test_violations_are_caught_with_correct_category(body, expected_category):
    assert check_post_body(body) == expected_category


# ── API integration: filter + report flow ────────────────────────────────────


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


def _register(client, email="user@example.com", password="hunter2pass", nickname=None):
    if nickname is None:
        nickname = email.split("@")[0]
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "nickname": nickname, "consent": True},
    )


def _auth_headers(client, **kwargs):
    token = _register(client, **kwargs).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(engine, email="admin@example.com"):
    with Session(engine) as session:
        ensure_admin_user(session, email, "adminpass1")
    from stock_risk.auth.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(email)}"}


def _create_post(client, headers, body="Volatility regime looks stretched here.", ticker="AAPL"):
    return client.post(
        "/api/community/posts",
        json={"ticker": ticker, "market": "us", "body": body},
        headers=headers,
    )


def test_create_post_blocked_by_filter_returns_moderation_code(client):
    headers = _auth_headers(client)
    response = _create_post(client, headers, body="Strong buy, price target $500!")
    assert response.status_code == 422
    assert response.json()["detail"] == "moderation:trading_directive"
    # Nothing was persisted.
    assert client.get("/api/community/posts").json()["total"] == 0


def test_create_post_with_geopolitical_analysis_succeeds(client):
    headers = _auth_headers(client)
    response = _create_post(
        client, headers, body="Taiwan election uncertainty is the key tail risk for TSM here."
    )
    assert response.status_code == 201


def test_report_post_flow(client):
    author = _auth_headers(client, email="author@example.com")
    reporter = _auth_headers(client, email="reporter@example.com")
    post_id = _create_post(client, author).json()["id"]

    response = client.post(
        f"/api/community/posts/{post_id}/report",
        json={"reason": "off_topic"},
        headers=reporter,
    )
    assert response.status_code == 201

    # Duplicate report by the same user -> 409.
    dup = client.post(
        f"/api/community/posts/{post_id}/report",
        json={"reason": "political"},
        headers=reporter,
    )
    assert dup.status_code == 409


def test_report_requires_auth_and_rejects_own_post_and_bad_reason(client):
    author = _auth_headers(client, email="author@example.com")
    post_id = _create_post(client, author).json()["id"]

    assert (
        client.post(f"/api/community/posts/{post_id}/report", json={"reason": "abuse"}).status_code
        == 401
    )
    own = client.post(
        f"/api/community/posts/{post_id}/report", json={"reason": "abuse"}, headers=author
    )
    assert own.status_code == 403
    reporter = _auth_headers(client, email="reporter@example.com")
    bad = client.post(
        f"/api/community/posts/{post_id}/report",
        json={"reason": "i-just-dislike-it"},
        headers=reporter,
    )
    assert bad.status_code == 422
    missing = client.post(
        "/api/community/posts/9999/report", json={"reason": "abuse"}, headers=reporter
    )
    assert missing.status_code == 404


def test_admin_sees_pending_reports_and_can_dismiss(client, engine):
    admin = _admin_headers(engine)
    author = _auth_headers(client, email="author@example.com", nickname="AuthorNick")
    reporter = _auth_headers(client, email="reporter@example.com", nickname="ReporterNick")
    post_id = _create_post(client, author, body="Some borderline take.").json()["id"]
    client.post(
        f"/api/community/posts/{post_id}/report", json={"reason": "political"}, headers=reporter
    )

    listing = client.get("/api/admin/reports", headers=admin)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    report = body["items"][0]
    assert report["reason"] == "political"
    assert report["status"] == "pending"
    assert report["post_ticker"] == "AAPL"
    assert report["post_body"] == "Some borderline take."
    assert report["reporter_handle"] == "ReporterNick"
    assert report["post_author_handle"] == "AuthorNick"

    dismiss = client.post(f"/api/admin/reports/{report['id']}/dismiss", headers=admin)
    assert dismiss.status_code == 204
    assert client.get("/api/admin/reports", headers=admin).json()["total"] == 0
    # Still visible with status=all.
    all_reports = client.get("/api/admin/reports", params={"status": "all"}, headers=admin)
    assert all_reports.json()["total"] == 1
    assert all_reports.json()["items"][0]["status"] == "dismissed"


def test_deleting_post_cascades_its_reports(client, engine):
    admin = _admin_headers(engine)
    author = _auth_headers(client, email="author@example.com")
    reporter = _auth_headers(client, email="reporter@example.com")
    post_id = _create_post(client, author).json()["id"]
    client.post(
        f"/api/community/posts/{post_id}/report", json={"reason": "abuse"}, headers=reporter
    )
    assert client.get("/api/admin/reports", headers=admin).json()["total"] == 1

    assert client.delete(f"/api/community/posts/{post_id}", headers=admin).status_code == 204
    all_reports = client.get("/api/admin/reports", params={"status": "all"}, headers=admin)
    assert all_reports.json()["total"] == 0


def test_reports_endpoints_are_admin_only(client):
    user = _auth_headers(client)
    assert client.get("/api/admin/reports", headers=user).status_code == 403
    assert client.post("/api/admin/reports/1/dismiss", headers=user).status_code == 403
    assert client.get("/api/admin/reports").status_code == 401
