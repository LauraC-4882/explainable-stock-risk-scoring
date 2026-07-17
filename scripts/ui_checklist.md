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

## Loading / empty states (capture separately if the harness is extended
to cover them — not produced by the current single-ticker screenshot)

- [ ] Loading state shows the skeleton placeholder, not a broken/blank
      card.
- [ ] Empty state (no tickers added) shows the intended prompt text and
      quick-pick chips, not a blank page.

## Cross-check: do the two score displays on the same card agree?

- [ ] The gauge/large-number score at the top of the card and the
      right-hand edge of the "Daily Risk Score" line chart at the bottom
      of the *same* card are showing numbers in the same ballpark (within
      a few points). **This is currently expected to FAIL** — see [E1] —
      the gauge comes from `RiskScorer.score()`'s percentile composite and
      the chart comes from `score_timeseries()`'s older heuristic
      (`_heuristic_score_row`), and they disagree by a visible margin on
      real data (verified live: gauge showed 66.5, chart's most recent
      points hovered ~70). Leave this item failing and pointing at [E1]
      until that issue reconciles the two scoring paths — don't mark it
      passing just to get a clean checklist.
