"""Documentation cannot drift back to a retracted claim.

Three defects of the same shape have now been found in this project, all in the
path where a computed number becomes an outward claim:

1. the reported VaR was `rolling(21).quantile(0.05)` — the 2nd order statistic
   of 21 returns, exceeded 2/22 = 9.09% of the time at any tail thickness, which
   the docs read as evidence of fat tails (fixed, `93b5871`);
2. `validate_tail.py` picks its ticker set by globbing `snapshots/`, so the
   "9 tickers, 4,613 ticker-days" the README once quoted was a directory state,
   not a declared sample (open — see SESSION_LEDGER.md);
3. that same script graded a log-return VaR line against `pct_return`
   (resolved — the realised-loss series now reads `log_return`, the same
   convention the forecast is estimated from; `301189_SZ` turns from pass
   to reject as a result, and the README says so).

Each one produced a precise-looking figure whose inputs were undefined. This
file guards the documentation half: the retracted numbers and the retracted
*attribution* must not come back, and any text that mentions the 21-day series
has to keep saying what it is.

It deliberately does NOT assert current measured values. Those depend on the
ticker set, the snapshot refresh and the return convention — all in motion —
so pinning them here would recreate defect (1) in the test suite itself.
"""

from __future__ import annotations

import re
import subprocess
import warnings

import pytest

# ── What counts as a document ────────────────────────────────────────────────
DOC_SUFFIXES = (".md",)

# Paired anchors that carve out a superseded claim kept deliberately as
# evidence. Content between them is exempt; everything else is scanned.
ANCHOR_OPEN = re.compile(r"<!--\s*historical-record:\s*[\w-]+\s*-->")
ANCHOR_CLOSE = re.compile(r"<!--\s*/historical-record\s*-->")


def _tracked_docs() -> list[str]:
    """Documentation files, from `git ls-files` — NOT from a filesystem walk.

    This matters and is not stylistic. The repository has historically
    contained an untracked nested clone of itself carrying a pre-fix copy of
    the sources, and every developer has untracked scratch files. A filesystem
    walk would scan both, so CI would fail or pass depending on what happened
    to be lying in someone's working directory. Only tracked content is a claim
    this project makes.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return [p for p in out.split("\0") if p.endswith(DOC_SUFFIXES)]


def _read(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8", errors="replace")


def _strip_historical(text: str) -> str:
    """Blank out anchored regions, preserving line count so numbers still map
    to the right line when a failure is reported."""
    out, pos = [], 0
    while True:
        opened = ANCHOR_OPEN.search(text, pos)
        if not opened:
            out.append(text[pos:])
            break
        closed = ANCHOR_CLOSE.search(text, opened.end())
        out.append(text[pos : opened.start()])
        if not closed:  # unbalanced — assertion 5 reports it; exempt nothing
            out.append(text[opened.start() :])
            break
        out.append("\n" * text[opened.start() : closed.end()].count("\n"))
        pos = closed.end()
    return "".join(out)


FENCED_CODE = re.compile(r"^```.*?^```", re.M | re.S)


def _blocks(text: str) -> list[str]:
    """Blank-line-separated blocks, with fenced code removed first.

    A JSON response example that lists `var_95_21d` as a key is a schema, not a
    prose claim about calibration — the qualifier rule below is about what the
    documentation *asserts*, and requiring English caveats inside a code fence
    would only push people to delete the example. Line count is preserved so
    reported offsets still line up.
    """
    stripped = FENCED_CODE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return [b for b in re.split(r"\n\s*\n", stripped) if b.strip()]


# How far a qualifying phrase may sit from the mention it qualifies. Chosen
# explicitly rather than inherited from a default:
#
#   0 (strict same block) is trivially evaded — put `var_95_21d` in one
#     paragraph and "scoring feature" in the next and the check passes while a
#     reader still sees an unqualified mention;
#   1 matches how people actually write (a claim, then its caveat, or a heading
#     paragraph followed by detail) without letting the qualifier drift to the
#     other end of the document.
#
# The check is "SOME window containing the mention is qualified", not "EVERY
# window" — a mention necessarily appears in several overlapping windows, and
# requiring all of them is the same as requiring same-block.
NEIGHBOURHOOD = 1


def _unqualified_blocks(text: str, mention: re.Pattern, qualifier: re.Pattern) -> list[str]:
    blocks = _blocks(text)
    bad = []
    for i, block in enumerate(blocks):
        if not mention.search(block):
            continue
        lo, hi = max(0, i - NEIGHBOURHOOD), min(len(blocks), i + NEIGHBOURHOOD + 1)
        if not any(qualifier.search(b) for b in blocks[lo:hi]):
            bad.append(block)
    return bad


DOCS = _tracked_docs()


# ── 1. Retracted numbers ─────────────────────────────────────────────────────

RETRACTED_NUMBERS = ("9.25%", "1160.9", "37,833", "3,498")


def test_retracted_breach_numbers_are_not_asserted_as_current():
    offenders = []
    for path in DOCS:
        body = _strip_historical(_read(path))
        for token in RETRACTED_NUMBERS:
            if token in body:
                offenders.append(f"{path}: {token!r}")
    assert not offenders, (
        "Retracted 21-day-estimator figures reappeared outside a "
        "<!-- historical-record: ... --> block:\n  " + "\n  ".join(offenders)
    )


# ── 2. Retracted attribution ─────────────────────────────────────────────────

FAT_TAIL = re.compile(r"fat[- ]tail|肥尾|厚尾|heavier tails", re.I)
REJECTION = re.compile(r"\breject\b|拒绝|拒絕|breach rate|突破率", re.I)


def test_breach_rates_are_not_attributed_to_fat_tails():
    """The specific wrong claim: a high breach rate proves fatter tails. It does
    not — the estimator's own plotting position can produce one at any tail
    thickness, which is exactly what happened here."""
    # Scoped to a single block: the claim and its correction have to sit
    # together. A correction a paragraph away does not stop the sentence itself
    # from reading as an assertion.
    correction = re.compile(
        r"not\b.{0,40}(fat|tail)|wrong|withdrawn|错误归因|artefact|artifact|order statistic",
        re.I,
    )
    offenders = []
    for path in DOCS:
        for block in _blocks(_strip_historical(_read(path))):
            if FAT_TAIL.search(block) and REJECTION.search(block) and not correction.search(block):
                offenders.append(f"{path}: {block.strip()[:110]}...")
    assert not offenders, (
        "A breach rate is attributed to fat tails without the correction:\n  "
        + "\n  ".join(offenders)
    )


# ── 3. The 21-day series must never be presented as the reported VaR ─────────

# `volatility__cvar_95_21d` is the model's internal feature-namespace name as
# it appears in SHAP output. It is self-evidently a feature, so it needs no
# separate qualifier; a negative lookbehind keeps it out of this check.
SHORT_SERIES = re.compile(r"(?<!__)\b(?:c?var_95_21d)\b")
# Deliberately specific phrases, NOT a loose `feature\b`. The first version of
# this list included the bare word, and a mutation test — injecting "The tile
# shows var_95_21d directly." into the README — passed, because "feature"
# occurs in half the paragraphs of a project README. A qualifier that common
# qualifies nothing.
QUALIFIER = re.compile(
    r"scoring feature|scoring input|评分特征|評分特徵|"
    r"not the reported|非报告用|非報告用|"
    r"order statistic|次序统计量|次序統計量",
    re.I,
)


def test_the_21_day_series_is_always_qualified():
    """Not "never mention 21-day" — these documents are *about* it. The rule is
    that a mention has to carry the distinction that it is a scoring input and
    not the reported 95% VaR."""
    offenders = []
    for path in DOCS:
        for block in _unqualified_blocks(
            _strip_historical(_read(path)), SHORT_SERIES, QUALIFIER
        ):
            offenders.append(f"{path}: {block.strip()[:110]}...")
    assert not offenders, (
        "var_95_21d mentioned without saying it is a scoring feature rather "
        "than the reported VaR:\n  " + "\n  ".join(offenders)
    )


# ── 4. The reported VaR's window is stated consistently ──────────────────────


def test_reported_var_is_not_described_as_a_21_day_window():
    offenders = []
    pattern = re.compile(r"95%\s*VaR[^.\n]{0,120}?21[- ]?(?:day|日)[^.\n]{0,60}", re.I)
    # A sentence naming BOTH windows is the correction ("uses a 100-day
    # quantile ... the 21-day series it replaced"), not the error. Exempting on
    # the presence of the real window keeps the check on the claim itself
    # rather than on any co-occurrence of the two numbers.
    corrective = re.compile(r"100[- ]?(?:day|日)|used to be|replaced|old\b|former", re.I)
    for path in DOCS:
        body = _strip_historical(_read(path))
        for m in pattern.finditer(body):
            if corrective.search(m.group(0)):
                continue
            offenders.append(f"{path}: {m.group(0)!r}")
    assert not offenders, (
        "The reported 95% VaR is described with a 21-day window; it uses 100 "
        "(RiskMetrics.VAR_WINDOW):\n  " + "\n  ".join(offenders)
    )


# ── 5. Anchors must be balanced ──────────────────────────────────────────────


def test_historical_record_anchors_are_balanced():
    """The worst failure mode of an exemption mechanism: an unclosed opener
    silently exempts the entire rest of the file, so every other assertion here
    quietly stops applying."""
    offenders = []
    for path in DOCS:
        body = _read(path)
        opens, closes = len(ANCHOR_OPEN.findall(body)), len(ANCHOR_CLOSE.findall(body))
        if opens != closes:
            offenders.append(f"{path}: {opens} open vs {closes} close")
    assert not offenders, "Unbalanced historical-record anchors:\n  " + "\n  ".join(offenders)


# ── 6. Cited commits must exist on main ──────────────────────────────────────

HASH = re.compile(r"`([0-9a-f]{7,12})`")


def test_cited_commit_hashes_are_reachable_from_main():
    """A rebase-merge rewrites hashes. This project has already published a
    document citing `1c1e938`, the pre-rebase hash of the very commit these
    docs describe — unreachable the moment it landed."""
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if shallow == "true":
        # Announced, never silent: a quietly-skipped gate is the failure mode
        # this project just spent a session removing from the font check.
        message = (
            "commit-hash reachability check SKIPPED: shallow clone "
            "(set fetch-depth: 0 in the workflow to enable it)"
        )
        print(f"\n[test_docs_consistency] {message}")
        warnings.warn(message, stacklevel=2)
        pytest.skip(message)

    base = "origin/main"
    if subprocess.run(["git", "rev-parse", "--verify", "-q", base],
                      capture_output=True).returncode != 0:
        base = "HEAD"

    offenders = []
    for path in DOCS:
        for candidate in set(HASH.findall(_read(path))):
            is_commit = subprocess.run(
                ["git", "cat-file", "-t", candidate], capture_output=True, text=True
            )
            if is_commit.returncode != 0 or is_commit.stdout.strip() != "commit":
                continue  # a hex-looking token that is not a commit here
            if subprocess.run(
                ["git", "merge-base", "--is-ancestor", candidate, base],
                capture_output=True,
            ).returncode != 0:
                offenders.append(f"{path}: {candidate} not reachable from {base}")
    assert not offenders, (
        "Documentation cites commits that are not on the mainline (a rebase "
        "probably rewrote them):\n  " + "\n  ".join(offenders)
    )


# ── 8. No stray control characters in tracked text ───────────────────────────

# Everything a text file is allowed to contain below U+0020. Anything else in
# that range arrives by accident rather than by authorship.
ALLOWED_CONTROL = frozenset({0x09, 0x0A, 0x0D})  # tab, LF, CR


def _tracked_files() -> list[str]:
    """Every tracked path, not only documentation — same `git ls-files`
    reasoning as `_tracked_docs`, without the suffix filter."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return [p for p in out.split("\0") if p]


def _control_char_offenders(path: str) -> list[str]:
    """`path:line:col 0xNN` for every disallowed character; [] for a binary file.

    A file counts as binary only when it BOTH contains a NUL byte AND fails to
    decode as UTF-8. Requiring only the NUL left the check with one structural
    blind spot, and it was the worst one available: NUL is itself a C0 control
    character, so the single byte most likely to be written into a source file
    by an escaping accident was also the byte that switched the check off. A
    valid UTF-8 file carrying one stray NUL was reported as clean.

    Still no suffix allowlist. An allowlist needs maintaining, and the first
    file type nobody remembers to add becomes silently exempt.

    Offsets are counted over the decoded text, so a column is a character
    rather than a byte and points where an editor puts the cursor.
    """
    from pathlib import Path

    data = Path(path).read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if b"\x00" in data:
            return []
        # Undecodable but NUL-free: not binary by the rule above, so it is
        # still scanned. Undecodable runs become replacement characters, which
        # are not control characters and so cannot manufacture a violation.
        text = data.decode("utf-8", errors="replace")

    offenders, line, col = [], 1, 1
    for char in text:
        point = ord(char)
        if point < 0x20 and point not in ALLOWED_CONTROL:
            offenders.append(f"{path}:{line}:{col} 0x{point:02x}")
        if point == 0x0A:
            line, col = line + 1, 1
        else:
            col += 1
    return offenders


def test_tracked_text_has_no_stray_control_characters():
    """A control character in prose occupies no visual space, so it survives
    both the diff and the rendered view and reaches main.

    Line and column are reported because locating one is the entire difficulty:
    the reader sees text that looks correct, and the byte that makes it wrong is
    invisible.
    """
    offenders = []
    for path in _tracked_files():
        offenders.extend(_control_char_offenders(path))
    assert not offenders, (
        "Disallowed control characters in tracked text (allowed: tab, LF, CR):\n  "
        + "\n  ".join(offenders)
    )


# ── The guard's own guard ────────────────────────────────────────────────────


def test_every_assertion_above_can_actually_fire():
    """A checker that never fires proves nothing, and this file has already
    shipped blind once.

    Two of the six assertions passed against a deliberately-broken README
    during development: `QUALIFIER` matched a bare `feature\b`, a word that
    occurs in half the paragraphs of any project README, and `SHORT_SERIES`
    was written with two literal backspace bytes where `\b` was intended, so
    it matched nothing at all. Both looked green against the real documents,
    because the real documents happen not to contain the failure mode.

    So the patterns are exercised here against synthetic text that MUST trip
    them. This is unit-level (no subprocess, no file mutation) — the end-to-end
    mutation run belongs in review, not in every CI cycle.
    """
    unqualified = "The metric tile shows var_95_21d directly."
    qualified = (
        "The tile shows var_95_21d, a scoring feature rather than the reported VaR."
    )
    assert SHORT_SERIES.search(unqualified), "mention pattern matches nothing"
    assert not QUALIFIER.search(unqualified), "qualifier pattern is too permissive"
    assert QUALIFIER.search(qualified), "qualifier pattern misses its own phrasing"

    assert _unqualified_blocks(unqualified, SHORT_SERIES, QUALIFIER) == [unqualified]
    assert _unqualified_blocks(qualified, SHORT_SERIES, QUALIFIER) == []

    # The neighbourhood rule: a qualifier one block away counts, two does not.
    near = f"This is a scoring feature.\n\n{unqualified}"
    far = f"This is a scoring feature.\n\nfiller\n\n{unqualified}"
    assert _unqualified_blocks(near, SHORT_SERIES, QUALIFIER) == []
    assert _unqualified_blocks(far, SHORT_SERIES, QUALIFIER) == [unqualified]

    # The model's own namespaced feature name needs no separate qualifier.
    assert not SHORT_SERIES.search("volatility__cvar_95_21d: -1.479")

    # Retracted figures and the retracted attribution.
    assert any(tok in "breaches 9.25% of days" for tok in RETRACTED_NUMBERS)
    assert FAT_TAIL.search("fat tails") and REJECTION.search("Kupiec reject")

    # Anchors: an unclosed opener must not silently exempt the rest of a file.
    unclosed = "<!-- historical-record: x -->\nbody 9.25%"
    assert "9.25%" in _strip_historical(unclosed), (
        "an unbalanced anchor exempted content instead of leaving it scanned"
    )
