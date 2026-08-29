"""The tail-validation sample set is declared, not discovered.

`scripts/validate_tail.py` used to take its sample from
`snapshots/*.parquet`, so the published tail figures depended on what the
machine running it happened to have cached — 6 files in a fresh checkout, 101
on a box that had run the cross-sectional builder. These tests pin the
replacement: a committed manifest, a hard error when it and the disk disagree
in the direction that would shrink the sample, and a loud note when they
disagree in the direction that would grow it.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SNAPSHOTS = _REPO / "snapshots"
_MANIFEST = _SNAPSHOTS / "validation_manifest.txt"
_SCRIPT = _REPO / "scripts" / "validate_tail.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_validate_tail", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entries() -> list[str]:
    return [
        line.split("#", 1)[0].strip()
        for line in _MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]


# ── the manifest itself ──────────────────────────────────────────────────────


def test_manifest_is_not_empty():
    assert _entries(), "an empty manifest would validate nothing and still pass"


def test_every_manifest_entry_is_tracked_by_git():
    """A sample file that is not in version control cannot be reproduced by
    anyone else, which defeats the point of declaring the sample at all."""
    tracked = subprocess.run(
        ["git", "ls-files", "snapshots/"],
        cwd=_REPO, capture_output=True, text=True, check=True,
    ).stdout.split()
    tracked_names = {Path(p).name for p in tracked}

    untracked = [name for name in _entries() if name not in tracked_names]
    assert untracked == [], f"manifest lists files git does not track: {untracked}"


def test_manifest_entries_exist_on_disk():
    missing = [name for name in _entries() if not (_SNAPSHOTS / name).exists()]
    assert missing == [], f"manifest lists files that are not present: {missing}"


# ── the loader's behaviour ───────────────────────────────────────────────────


def test_the_sample_comes_from_the_manifest_not_the_directory(tmp_path, capsys):
    """The actual regression guard, stated behaviourally.

    A source-text check for `glob(` cannot express this: the loader still globs
    the directory, deliberately, to report what it is *ignoring*. What must
    never happen is a globbed file entering the sample. So this puts an extra
    parquet on disk and asserts it is absent from the loaded frames.
    """
    module = _load_module()

    listed = _entries()[0]
    (tmp_path / listed).write_bytes((_SNAPSHOTS / listed).read_bytes())
    (tmp_path / "ZZZZ_NOT_DECLARED_2y_1d.parquet").write_bytes(
        (_SNAPSHOTS / listed).read_bytes()
    )
    (tmp_path / "validation_manifest.txt").write_text(f"{listed}\n", encoding="utf-8")

    frames = module._load_snapshots(tmp_path)

    assert set(frames) == {listed.replace("_2y_1d.parquet", "")}
    assert not any("ZZZZ" in ticker for ticker in frames)

    captured = capsys.readouterr()
    assert "sample set: 1 files from manifest" in captured.out
    assert "IGNORED (not in manifest): 1 files" in captured.err
    assert "ZZZZ_NOT_DECLARED_2y_1d.parquet" in captured.err


def test_a_declared_file_missing_from_disk_is_fatal(tmp_path):
    """The counter-example, in the spirit of
    test_docs_consistency.py::test_every_assertion_above_can_actually_fire:
    prove the check can go red, or it proves nothing.

    Skipping here would let the sample silently shrink while the run still
    reported success — the exact failure mode the manifest exists to stop.
    """
    module = _load_module()
    (tmp_path / "validation_manifest.txt").write_text(
        "DOES_NOT_EXIST_2y_1d.parquet\n", encoding="utf-8"
    )

    with pytest.raises(FileNotFoundError) as excinfo:
        module._load_snapshots(tmp_path)

    assert "DOES_NOT_EXIST_2y_1d.parquet" in str(excinfo.value)


def test_a_missing_manifest_is_fatal_rather_than_falling_back(tmp_path):
    """No fallback to globbing. A fallback would restore the original bug at
    the moment nobody is looking for it."""
    module = _load_module()
    (tmp_path / "SOMETHING_2y_1d.parquet").write_bytes(b"not really parquet")

    with pytest.raises(FileNotFoundError, match="manifest"):
        module._load_snapshots(tmp_path)


def test_the_loader_does_not_select_by_globbing(tmp_path):
    """Narrower than "the file contains no glob(", which cannot hold — the
    ignored-files report needs a directory listing.

    What is asserted instead: with a manifest present, adding files to the
    directory does not change the sample. That is the property the source-text
    check was reaching for.
    """
    module = _load_module()
    listed = _entries()[0]
    payload = (_SNAPSHOTS / listed).read_bytes()
    (tmp_path / listed).write_bytes(payload)
    (tmp_path / "validation_manifest.txt").write_text(f"{listed}\n", encoding="utf-8")

    before = set(module._load_snapshots(tmp_path))
    for i in range(3):
        (tmp_path / f"EXTRA{i}_2y_1d.parquet").write_bytes(payload)
    after = set(module._load_snapshots(tmp_path))

    assert before == after, "files appearing on disk changed the sample"
