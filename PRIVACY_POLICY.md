# Privacy Policy

_Last updated: 2026-07-26_

Riscore is a personal, open-source project, not a company. This policy
describes what a deployment of this code stores about you. Every item below
corresponds to an actual field in the source — see the file references if you
want to verify a claim rather than take it on trust.

## What we collect

**Your account** (`auth/models.py`, `User`) — created when you sign up:

- Your **email address**, used to sign in and to identify your account.
- Your **password, hashed with bcrypt**. The plain-text password is never
  stored and never written to logs.
- Your **nickname**, shown publicly on your Community posts. Your email is
  never shown publicly.
- Account timestamps and status flags (created date, banned, admin).

**Your content** — only what you create:

- **Watchlist** (`WatchlistItem`): the tickers you follow, their market, your
  private notes on them, and when you added them.
- **Community posts** (`AnalystPost`): the ticker and the text you wrote.
  These are **publicly visible** to anyone using the site.
- **Votes and reports** (`PostVote`, `PostReport`): which post you voted on,
  up or down, and any post you flagged for moderation.

**Usage records** — two separate logs, both visible only to the site admin:

- **Request telemetry** (`PageView`): one row per non-static request, holding
  the path, HTTP method, response status, timestamp, and your email if you
  were signed in. It powers the admin usage dashboard. It does **not** record
  your IP address.
- **Security audit log** (`security/audit.py`, `AuditLog`): written only for
  security-relevant events — sign-in success and failure, account lockout,
  registration, admin bans/unbans, post moderation, denied admin access, and
  rate limiting. These rows **do include your IP address**, to make abuse and
  intrusion attempts investigable. Ordinary browsing does not create one.

## What we do not do

- **We do not sell your data**, and we do not share it with advertisers or
  data brokers.
- **No third-party analytics or trackers.** There is no Google Analytics,
  Sentry, Segment, or similar in this codebase.
- **No tracking cookies.** The site sets no cookies at all; your session token
  is kept in your browser's `localStorage` and is cleared when you sign out.
- **No advertising, no profiling, no automated decisions about you.**

## Data sent to third parties

To compute a risk score, the **ticker symbol** you look up is sent to the
market-data provider for that market — Yahoo Finance via `yfinance`, Twelve
Data (US, if configured), or `akshare` (China A-shares). Your identity is not
sent with it: those providers receive a stock symbol and the server's IP, not
your email or account. Their own privacy policies govern what they do with
that request.

The site is hosted on a third-party platform, which necessarily processes
network traffic to serve you the page.

## Deleting your data

- **Your posts**: you can delete any post you wrote, yourself, at any time.
- **Your account**: there is currently **no self-service delete button**.
  Closing an account is handled manually by the admin. To request it, either
  open an issue on the project's GitHub repository, or contact the admin
  account through the in-app Community board. We do not publish a support
  email address.
- **Backups**: the deployment keeps a small rolling set of recent database
  backups. Deleted data can persist in those backups until they rotate out.
- **Audit rows outlive the account by design.** A security audit entry is kept
  even after the account it refers to is closed — an audit trail that can be
  erased by the person it describes is not an audit trail. These rows hold an
  email address, an action name, and an IP.

## Retention

Account data and your content are kept until the account is closed. The
request-telemetry and audit tables currently have **no automatic pruning
policy** — rows accumulate for the life of the deployment.

## Changes

This policy may change as the project changes. Material changes will be
reflected in this file, and its history is public in the repository's git log.

---

_Riscore displays statistical risk metrics from historical market data. It is
not investment advice._
