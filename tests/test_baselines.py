"""The collect-only archive in `.baselines/` must name commits that exist.

A pytest count is a baseline only if the list of ids it summarises is archived
under the sha that produced it (`.baselines/README.md`). The archive is keyed by
sha, so it is only as good as the sha: a rebase-merge rewrites hashes, and an
archive taken on an unpushed branch names a commit no fresh clone holds. Either
way the file would sit there looking authoritative while describing a commit
nobody can check out. These tests make that loud, with the same semantics as
the hash-citation gate in test_docs_consistency.py: unresolvable is a failure,
not a pass, and a shallow clone announces its skip rather than going quiet.
"""

from __future__ import annotations

import re
import subprocess
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BASELINES = _REPO / ".baselines"
_ARCHIVE_NAME = re.compile(r"^[0-9a-f]{40}\.txt$")


def _archives() -> list[Path]:
    return sorted(p for p in _BASELINES.iterdir() if p.suffix == ".txt")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=_REPO, capture_output=True, text=True)


def _archive_offenders(
    names: list[str],
    base: str,
    object_type: Callable[[str], str | None],
    is_ancestor: Callable[[str], bool],
) -> list[str]:
    """Classify each archive name; returns offence strings.

    object_type / is_ancestor are injected so the fire-check below can drive
    every branch without a git subprocess — the pattern test_docs_consistency
    uses for its own gate, and for the same reason: a check that has never
    been seen to fail is not known to check anything.
    """
    offenders = []
    for name in names:
        if not _ARCHIVE_NAME.match(name):
            offenders.append(
                f".baselines/{name}: not named by a full 40-character commit "
                "sha (short shas are ambiguous over time; use `git rev-parse HEAD`)"
            )
            continue
        sha = name[:-4]
        kind = object_type(sha)
        if kind is None:
            offenders.append(
                f".baselines/{name}: {sha} does not resolve to any object in "
                "this clone — the archive names a commit that no longer exists "
                "(rebase-rewritten, or taken on an unpushed branch)"
            )
        elif kind != "commit":
            offenders.append(f".baselines/{name}: {sha} resolves to a {kind}, not a commit")
        elif not is_ancestor(sha):
            offenders.append(f".baselines/{name}: {sha} is not reachable from {base}")
    return offenders


def test_the_archive_is_seeded():
    assert _archives(), (
        ".baselines/ holds no archive; seed it with the command in "
        ".baselines/README.md before citing a pytest count as a baseline"
    )


def test_every_archive_is_a_plain_list_of_test_ids():
    """One collected id per line and nothing else, so `wc -l` is the count and
    two archives diff cleanly. The timing summary pytest prints last is the
    line that would otherwise make byte comparison meaningless."""
    for path in _archives():
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines, f"{path.name} is empty"
        stray = [line for line in lines if "::" not in line]
        assert not stray, (
            f"{path.name} contains lines that are not test ids "
            f"(strip pytest's summary/timing line): {stray[:3]}"
        )


def test_every_archived_sha_is_a_commit_reachable_from_main():
    shallow = _git("rev-parse", "--is-shallow-repository").stdout.strip()
    if shallow == "true":
        message = (
            "baseline-sha reachability check SKIPPED: shallow clone "
            "(set fetch-depth: 0 in the workflow to enable it)"
        )
        print(f"\n[test_baselines] {message}")
        warnings.warn(message, stacklevel=2)
        pytest.skip(message)

    base = "origin/main"
    if _git("rev-parse", "--verify", "-q", base).returncode != 0:
        base = "HEAD"

    def object_type(sha: str) -> str | None:
        probe = _git("cat-file", "-t", sha)
        return probe.stdout.strip() if probe.returncode == 0 else None

    def is_ancestor(sha: str) -> bool:
        return _git("merge-base", "--is-ancestor", sha, base).returncode == 0

    offenders = _archive_offenders(
        [p.name for p in _archives()], base, object_type, is_ancestor
    )
    assert not offenders, (
        "Stale or malformed collect-only archives in .baselines/:\n  "
        + "\n  ".join(offenders)
    )


def test_the_reachability_check_can_actually_fire():
    """Every branch of _archive_offenders produces an offence on the input it
    exists for, and the good case produces none."""
    good = "a" * 40 + ".txt"
    missing = "b" * 40 + ".txt"
    blob = "c" * 40 + ".txt"
    orphan = "d" * 40 + ".txt"
    short = "abcdef1.txt"

    kinds = {"a" * 40: "commit", "c" * 40: "blob", "d" * 40: "commit"}
    offenders = _archive_offenders(
        [good, missing, blob, orphan, short],
        "origin/main",
        object_type=kinds.get,
        is_ancestor=lambda sha: sha == "a" * 40,
    )
    assert len(offenders) == 4, offenders
    assert any(missing in o and "does not resolve" in o for o in offenders)
    assert any(blob in o and "blob" in o for o in offenders)
    assert any(orphan in o and "not reachable" in o for o in offenders)
    assert any(short in o and "40-character" in o for o in offenders)
    assert not any(good in o for o in offenders)
