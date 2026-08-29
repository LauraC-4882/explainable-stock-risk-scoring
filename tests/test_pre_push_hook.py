"""scripts/git-hooks/pre-push — the behind-origin/main warning.

Exercised against throwaway local repositories (a file-path "origin"), so the
hook's `git fetch origin main` works with zero network — consistent with the
suite-wide socket guard. The hook's contract, asserted here:

  * behind origin/main  -> warning on stderr naming the commit count, exit 0
  * up to date          -> silence, exit 0
  * no origin at all    -> silence, exit 0 (never blocks, never crashes)

It is a WARNING hook by design; nothing here asserts a non-zero exit, and a
change that makes it start blocking should fail these tests loudly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "scripts" / "git-hooks" / "pre-push"


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _commit(cwd: Path, name: str) -> None:
    (cwd / name).write_text(name, encoding="utf-8")
    _git(cwd, "add", name)
    _git(
        cwd, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "-m", f"add {name}",
    )


def _run_hook(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(HOOK)], cwd=cwd, capture_output=True, text=True
    )


def _clone_pair(tmp_path: Path) -> tuple[Path, Path]:
    """(clone, second_clone) sharing a bare file-path origin with one commit."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    _commit(seed, "base.txt")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    return clone, seed


def test_warns_with_the_commit_count_when_behind(tmp_path):
    clone, seed = _clone_pair(tmp_path)
    _commit(seed, "ahead1.txt")
    _commit(seed, "ahead2.txt")
    _git(seed, "push", "-q", "origin", "HEAD:main")

    result = _run_hook(clone)  # clone still at base
    assert result.returncode == 0, result.stderr
    assert "behind origin/main" in result.stderr
    assert "2 commit(s)" in result.stderr


def test_silent_and_green_when_up_to_date(tmp_path):
    clone, _ = _clone_pair(tmp_path)
    result = _run_hook(clone)
    assert result.returncode == 0, result.stderr
    assert "behind" not in result.stderr


def test_silent_and_green_without_an_origin(tmp_path):
    lone = tmp_path / "lone"
    _git(tmp_path, "init", "-q", "-b", "main", str(lone))
    _commit(lone, "only.txt")
    result = _run_hook(lone)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == ""
