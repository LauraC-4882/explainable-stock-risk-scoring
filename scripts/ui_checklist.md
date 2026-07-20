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

## Cross-check: do the two score displays on the same card agree?

- [ ] The gauge/large-number score at the top of the card and the
      right-hand edge of the "Daily Risk Score" line chart at the bottom
      of the *same* card are showing numbers in the same ballpark (within
      a few points). **Fixed by [E1]**: `score_timeseries()` now computes
      every day (including the last one) via the same
      `risk_categories.composite_score()` the gauge uses, with the same
      benchmark passthrough and the same VIX-regime weights applied to the
      last day — not the old separate `_heuristic_score_row` heuristic
      (deleted). Verified live: `curl .../api/score/TSLA` and
      `curl .../api/score/TSLA/timeseries?period=6mo`'s last point now
      return the *exact same* risk_score (diff 0, both TSLA and AAPL) —
      not just "within a few points." If this item ever starts failing
      again, that's a real regression, not a known/expected gap.
