# UI self-review checklist

For use after `bash scripts/ui_shot.sh` — look at the two PNGs it produces
(`ui-desktop.png` at 1280px, `ui-mobile.png` at 375px) and check every item
below against what's actually *visible in the screenshot*. Every item here
must be answerable by looking at the image, not by reasoning about the code.
"Looks good" / "UI is clean" are not checklist items — if you can't point
to the specific pixels that pass or fail an item, rewrite the item.

Iterate at most 3 rounds (change → `bash scripts/ui_shot.sh` → re-check this
list) before flagging remaining failures to a human instead of continuing
to loop.

## Desktop (`ui-desktop.png`, 1280px)

- [ ] The TSLA card is fully visible: header, gauge, "what does this score
      mean" toggle, metric tiles, price chart, daily-risk-score chart, and
      the `risk_note` footer text are all present and none of them are
      cut off at the card's edges.
- [ ] No two elements visually overlap (e.g. the gauge doesn't overlap the
      score number/badge; chart labels don't sit on top of chart lines).
- [ ] No element extends past the card's right edge or the page's right
      edge (would show as content abruptly clipped by the viewport).
- [ ] All text is legible against its background — no dark-gray-on-black
      or light-gray-on-white low-contrast text.
- [ ] The gauge's numeric label, the large score number, and the risk
      label badge (LOW/MODERATE/HIGH/EXTREME) show three *consistent*
      values — same score, matching color coding.

## Mobile (`ui-mobile.png`, 375px)

- [ ] No horizontal scrollbar / no content wider than 375px (check the
      image's own right edge — nothing should be cut off there that
      wasn't also cut off identically at 1280px).
- [ ] The 4-column metric tile row (30D VOL / VAR 95% / BETA / RSI 14)
      either fits on one line per label or wraps in a way that's still
      readable — a label broken mid-word across two lines (e.g. "30D" /
      "VOL" stacked) is a fail, not a stylistic nitpick.
- [ ] Charts are still readable at this width (axis labels not so
      compressed they overlap each other).
- [ ] Header/search/market-switcher controls don't overflow or overlap
      each other at this width.

## Empty state (`ui-empty.png`, desktop — captured since the Riscore rebrand)

- [ ] The brand hero lockup renders complete and in order: shield-in-ring
      icon, the Ri·score wordmark, the INVEST SMARTER · RISK SAFER
      tagline, the circular slogan ring ("Know your risk." / INVEST WITH
      CLARITY), then the search prompt and quick-pick chips.
- [ ] The slogan ring's gradient arc is fully drawn (the harness waits out
      the draw animation — a partially-drawn arc means the timing broke).
- [ ] Quick-pick chips are legible and none of the ambient dots/orbs sit
      on top of interactive content.
- [ ] Loading state (skeleton) is still not captured by the harness — check
      it manually if you touched CardSkeleton.

## Onboarding tour (`ui-onboarding.png`, desktop — captured on first visit before the harness dismisses it)

- [ ] The tour modal is centered, fully visible, and legible against the
      dimmed backdrop — icon, title, body text, progress dots, and the
      Next/Skip controls are all present and none are clipped.
- [ ] The first step ("Welcome to Riscore") is showing, not a later step —
      confirms the tour auto-opens on a fresh visit rather than resuming
      mid-way or failing to open.
- [ ] The header behind the dimmed backdrop still shows the two distinct
      auth buttons (Sign up / Sign in) plus the "?" replay button — the
      tour shouldn't be the only way these are visible.

## Logged-in header + Profile panel (manual check — not part of the scripted flow, since it requires registering a user)

- [ ] Signed out: header shows two distinct buttons, "Sign up" (outline)
      and "Sign in" (solid) — not a single ambiguous button.
- [ ] Signed in: header shows the Watchlist button, a circular avatar
      (colored circle with the account's first initial), the "?" button,
      then the language switcher, in that order, with no overlap.
- [ ] Clicking the avatar opens the Profile panel: avatar, email, "Member
      since <month year>" (a real date, not "Invalid Date" or blank),
      watchlist count, "Replay tutorial", and "Sign out" are all present.
- [ ] "Replay tutorial" closes the Profile panel and reopens the onboarding
      tour from step 1.

## Community platform (`ui-community-widgets.png`, `ui-community-feed.png`,
`ui-community-leaderboard.png`, `ui-profile-community.png` — desktop,
captured logged-in as a throwaway voter with one seeded post + one seeded
vote; see `shoot_community` in `scripts/ui_shot.py`)

- [ ] `ui-community-widgets.png`: the TSLA card shows a populated "Top
      community take" widget — author handle, an accuracy badge, and a
      one-line snippet of the seeded post's body, all inside its own
      bounded panel-tile between the metric tiles and the price chart.
- [ ] Same screenshot: the AAPL card's widget shows the empty "be the
      first" CTA state instead, not a blank space and not the TSLA card's
      post leaking into it.
- [ ] `ui-community-feed.png`: the disclaimer ("the risk score is computed
      from objective market data... other users' personal opinion...") is
      visible without scrolling on the panel's initial view, in a plain
      banner with no × or dismiss control anywhere near it.
- [ ] Same screenshot: the seeded post's 👍 button is in its "pressed"
      state (filled/colored, not the default outline) — confirms the
      voter's own vote is reflected, not just the raw tally.
- [ ] Same screenshot: neither vote button on the seeded post is disabled
      or hidden due to being mistaken for the viewer's own post (the voter
      account did not author it).
- [ ] `ui-community-leaderboard.png`: sorted by "Recent," the author's row
      is visible showing a "new analyst" / pending badge (not "0%") — the
      seeded post has only 1 vote, below the 10-vote leaderboard-accuracy
      threshold, so this is the expected state, not a bug.
- [ ] `ui-profile-community.png`: the Profile panel shows two new rows
      ("Analysis posts" and "Posts voted on") between the watchlist-count
      row and "Replay tutorial," with counts 0 and 1 respectively for this
      voter account, each with a legible "View all" link.
- [ ] No element in any of the four screenshots is clipped by the card's
      or the page's right edge, and no text is illegible against its
      background — same bar as the desktop/mobile checks above.

## Sign-up modal + privacy consent (`ui-signup-consent.png`, desktop —
the modal opened in signUp mode; see `shoot_signup` in `scripts/ui_shot.py`)

- [ ] The modal shows, in order: a Nickname field (with the "shown on your
      posts instead of your email" hint), the Email field, the Password
      field, then a privacy-consent notice paragraph, then a checkbox.
- [ ] The consent notice is legible and actually states what it should —
      that the nickname (not email) is public, and that the admin can see
      the nickname, sign-up email, and usage data, used only for analytics
      and site security. Not a bare "I agree" with no context.
- [ ] The "Continue" submit button is visibly disabled (dimmed) because the
      consent box starts unchecked — confirms the gate works.

## Admin panel (`ui-admin-overview.png`, `ui-admin-usage.png`,
`ui-admin-users.png` — desktop, captured logged-in as the seeded admin;
see `shoot_admin` in `scripts/ui_shot.py`)

- [ ] The header shows a distinct gold-tinted "Admin" nav button (with the
      🛡️ icon) that the community/other screenshots — captured as a
      non-admin — do NOT show. Confirms the button is gated on `is_admin`.
- [ ] `ui-admin-overview.png`: the Admin Dashboard modal is open, centered,
      with three tabs (Overview / Usage / Users); the Overview tab shows
      four stat tiles (Total requests, Unique users, Last 24h, Last 7 days)
      with non-negative integer values, none blank or "NaN".
- [ ] `ui-admin-usage.png`: the hour-of-day bar chart renders with visible
      bars of differing heights (not all-zero, not one flat row) — the
      seeded traffic hit a single UTC hour, so at least one bar is clearly
      taller than the empty hours around it. Below it, a "Top pages" list
      shows real paths (e.g. `/api/score/TSLA`, `/api/community/posts`)
      with integer counts.
- [ ] `ui-admin-users.png`: the Users tab lists at least the admin account
      (with an "Admin" badge) and the seeded member account. The admin's
      own row has NO ban button; the normal member's row DOES have a red
      "Ban" button. A search box sits above the list.
- [ ] No element in any of the three screenshots is clipped by the modal's
      or the page's right edge, and all text is legible against its
      background — same bar as the desktop/mobile checks above.

## Model governance panel (`ui-governance.png`, `ui-governance-features.png`,
`ui-governance-lifecycle.png` at 1280px and `ui-governance-mobile.png` at
375px; see `shoot_governance` in `scripts/ui_shot.py`)

Three desktop frames because the panel is taller than the viewport and the
part below the fold is the part worth reviewing. Captured with `full_page=False`
on purpose: it is a `position: fixed` overlay, and a full-page capture
re-lays-out the modal and photographs an empty header.

- [ ] `ui-governance.png`: with no `models/registry.json`, the Champion
      section shows the gold-tinted "No governance record for the deployed
      model" card — a visible, readable statement, not blank space and not a
      green tick. It names `models/registry.json` (repo-relative, forward
      slashes — an absolute `C:\Users\...` path is a fail) and shows the
      `python scripts/train.py --version …` command in a code block.
- [ ] Same screenshot: NO metric appears anywhere in the Champion section.
      In particular the repo's published 0.671 walk-forward AUC must not be
      rendered as this model's measured value — substituting a documented
      number for an absent record is the exact failure this panel exists to
      avoid. (`≥ 0.6` under Validation gate is a threshold, not a
      measurement, and is expected.)
- [ ] Same screenshot: the Deployed artefact rows show a real repo-relative
      path, a 10-char commit hash with a real date (not "Invalid Date"), a
      truncated SHA-256, and "Loaded and answering requests" in green. The
      Hyperparameters row wraps at the `·` separators — a value broken
      mid-token (`learning_rate=0.0` / `5`) is a fail.
- [ ] `ui-governance-features.png`: the feature ranking shows numbered rows
      with full feature names, a filled bar per row, and a printed importance
      that DECREASES down the list. Bars are scaled to the top feature, so
      rank 1's bar is full width — a list where every bar is a sliver means
      the scaling regressed to absolute.
- [ ] `ui-governance-lifecycle.png`: the `DEVELOPMENT` row's chips are
      `retired` and `validated` only, and the `DEGRADED` row's are `retired`
      and `validated` only. Neither offers `active`. `APPROVED` and `SHADOW`
      do offer `active`. `RETIRED` shows the italic terminal note with no
      chips. These absent edges are the governance claim — if `active`
      appears on the development or degraded row, the page is describing a
      control the registry does not enforce.
- [ ] Same screenshot: the ACTIVE badge is green, DEGRADED is red, and each
      still carries its state name as text — colour is never the only
      signal.
- [ ] `ui-governance-mobile.png` (375px): nothing extends past the right
      edge, the label/value rows have stacked (label above value) rather
      than crushing the value into a ~150px column, and feature names read
      in full rather than truncating to `volatility__vol_6…`. The importance
      bars are intentionally hidden at this width — their absence is correct,
      a 6px sliver is not.

## VaR backtest panel — the ES leg (visible on any expanded card)

- [ ] The panel lists FOUR tests, not three: Kupiec, Christoffersen
      independence, conditional coverage, and "Acerbi–Székely Z2 (were
      breaches as deep as ES said?)". The fourth was computed but never
      returned before this landed, so its absence is a regression.
- [ ] The Acerbi–Székely row shows `Z2 = <signed number> · p = <number>` —
      the other three rows show `p =` only, because Z2 is the sign-carrying
      statistic and a bare p-value hides which direction ES was wrong in.
- [ ] When that row is present, the one-sided explanation paragraph is
      rendered beneath the list ("Z2 below 0 means breaches ran deeper than
      ES predicted…"). A REJECTED ES verdict with no explanation of the
      direction is a fail.

## Email alert settings (`ui-alert-settings.png` at 1280px,
`ui-alert-settings-mobile.png` at 375px; see `shoot_email_alerts` in
`scripts/ui_shot.py`)

Captured logged-in with TSLA armed (threshold 70, spike 15) and AAPL untouched,
so both the configured and the unconfigured state are in one frame.

- [ ] TSLA's row shows two CHECKED boxes, each followed by a number input
      containing 70 and 15 respectively. AAPL's shows the same two labels with
      boxes UNCHECKED and **no** number inputs — the field only exists once the
      trigger is on, so an empty box can't look like a threshold of 0.
- [ ] Under TSLA: "No email sent yet". That line must be absent under AAPL —
      a stock with no trigger armed has nothing to report about sending.
- [ ] The spike label reads "rises by (or more)", not "rises by more than".
      The trigger fires at exactly N (`>=`), and a label that promises `>`
      would be lying about the boundary.
- [ ] Mobile: nothing extends past the right edge, both checkbox rows stay on
      one line each, and the number inputs are still tappable (not shrunk to a
      sliver by the label text).

## The alert email itself (render it, don't reason about it)

`.venv/bin/python -c "from stock_risk.alerts.email import render_alert; ..."`
writes the HTML; open it at 375px.

- [ ] The disclaimer ("not investment advice… does not predict future price
      movements") is visible without scrolling past the fold of the footer, in
      readable grey — not fine print.
- [ ] An unsubscribe link is present and legible.
- [ ] The body states only the two scores, the band, and which trigger fired.
      No sentence tells the reader to do anything, and no price appears
      anywhere. `advice_language_violations()` returning `[]` is the automated
      half of this; the visual half is checking the email doesn't *read* like
      a recommendation even when each sentence passes.

## Cross-check: do the two score displays on the same card agree?

- [ ] The gauge/large-number score at the top of the card and the
      right-hand edge of the "Daily Risk Score" line chart at the bottom
      of the *same* card are showing numbers in the same ballpark (within
      a few points). Two fixes stack here. **[E1]** routed both paths through
      the same `risk_categories.composite_score()` (deleting the old
      `_heuristic_score_row` heuristic) with the same benchmark passthrough
      and VIX-regime weights on the last day. **[E1-regression]** then closed
      the gap the ML fusion gate ([A1]/[A2]) had reopened: the gauge reports
      the ML-*fused* headline, so `score_timeseries()` now fuses the current ML
      drawdown leg into its *final* point exactly as `score()` does (earlier
      points stay pure composite — there is no cheap non-lookahead historical
      ML series). Verified: `curl .../api/score/TSLA` and
      `.../timeseries?period=6mo`'s last point return the *exact same*
      risk_score (diff 0) with ML on or off. If this ever starts failing
      again, that's a real regression, not a known/expected gap.
