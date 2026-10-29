"""The Python -> app JSON contract envelope.

Python writes JSON files into app/public/data/; the React app only ever reads
those files. Nothing else crosses the boundary. Every file starts with the same
small envelope so the app (and a human) can tell, for any file:

    schema_version  which version of the file layout this is
    generated_at    when it was written (UTC, ISO-8601, trailing "Z")
    source_commit   which code produced it

If the layout of any file changes in a way the app would notice, bump
SCHEMA_VERSION.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

# 0.1.0: the manifest and illustrative_surface.json. 0.2.0: data_quality.json added (a new file is a
# MINOR bump, because a viewer that does not know it still reads the others).
SCHEMA_VERSION = "0.2.0"

REPO_ROOT = Path(__file__).resolve().parents[2]

# The exporter writes its JSON here, inside the repo. Re-exporting changes
# these files, so counting them as "dirty" would make source_commit differ
# between two exports of identical code. We leave this folder out of the check.
GENERATED_DIR = "app/public/data"

# A git lookup returns (HEAD commit hash or None if there is no commit yet,
# is the working tree dirty). It is a parameter everywhere so tests can pass a
# fake and never need a real git repo.
GitLookup = Callable[[], tuple[str | None, bool]]


# Seconds before a git call is abandoned. A hung git (a stuck network filesystem, a lock
# held by another process) must not freeze the exporter; a timeout is treated as a failure.
GIT_TIMEOUT_SECONDS = 30


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    """SIGKILL git and everything it started (hooks, fsmonitor, credential helpers)."""
    try:
        # start_new_session made git the leader of its own group, so the group id is its pid.
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError, PermissionError):  # no killpg (Windows) / already gone
        process.kill()


def _git(args: list[str], cwd: Path) -> str | None:
    """Run `git <args>` in cwd; return stdout, or None if git failed, timed out or is missing."""
    try:
        # start_new_session: git gets its own process group, so a timeout can kill its children
        # too. subprocess.run would kill only git and leave a hung hook or fsmonitor daemon running.
        with subprocess.Popen(
            ["git", *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",  # a non-UTF-8 file name must not crash the stamp
            start_new_session=True,
        ) as process:
            try:
                stdout, _ = process.communicate(timeout=GIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                _kill_process_group(process)
                return None
    except FileNotFoundError:  # git is not installed
        return None
    if process.returncode != 0:
        return None
    return stdout.strip()


def git_state(repo_dir: Path | None = None) -> tuple[str | None, bool]:
    """The real lookup: (HEAD hash or None, working tree dirty?)."""
    cwd = repo_dir or REPO_ROOT
    # `git rev-parse HEAD` fails in a repo with no commits (or outside a repo):
    # that is how we detect "nothing to point at yet".
    head = _git(["rev-parse", "HEAD"], cwd)
    if head is None:
        return None, False
    outside_generated = [".", f":(exclude){GENERATED_DIR}"]
    # Three questions, each one a place a change can hide. The answer is "clean" only if all three
    # ran and printed nothing. A git call that fails is None, and None is not "" (see below).
    #
    # 1. Tracked files that differ from HEAD or the index. --porcelain prints one line per change
    #    and nothing when clean. --ignore-submodules=none beats `diff.ignoreSubmodules=all` (which
    #    would hide a modified submodule). --untracked-files=no because question 3 handles those.
    changed = _git(
        ["status", "--porcelain", "--untracked-files=no", "--ignore-submodules=none", "--", *outside_generated],
        cwd,
    )
    # 2. Files git was told to stop looking at. `update-index --assume-unchanged` and
    #    `--skip-worktree` make `git status` skip a file, so an edit to it reads as clean.
    #    `ls-files -v` tags those entries: lowercase = assume-unchanged, S = skip-worktree.
    tagged = _git(["ls-files", "-v", "--", *outside_generated], cwd)
    hidden = None if tagged is None else "\n".join(
        line for line in tagged.splitlines() if line[:1].islower() or line[:1] == "S"
    )
    # 3. Untracked files. Only the repo's own .gitignore files may hide one: those are committed, so
    #    they are part of the code the hash names. .git/info/exclude, core.excludesFile and
    #    status.showUntrackedFiles are per-machine, and a stamp must not depend on them.
    untracked = _git(["ls-files", "--others", "--exclude-per-directory=.gitignore", "--", *outside_generated], cwd)
    # FAIL CLOSED. Any of these can fail while `rev-parse` succeeds (a corrupt or unreadable
    # .git/index exits 128). `_git` reports that as None, and `bool(None)` is False, which would
    # stamp an unknown tree as clean. "Could not check" must not read as "nothing changed", so a
    # failed call counts as dirty. The only clean answer is every call succeeding and printing nothing.
    answers = (changed, hidden, untracked)
    return head, any(answer is None or answer != "" for answer in answers)


def source_commit(git_lookup: GitLookup = git_state) -> str:
    """Hash of HEAD, plus "-dirty" if uncommitted changes exist; "uncommitted" if no HEAD."""
    head, dirty = git_lookup()
    if head is None:
        return "uncommitted"
    return f"{head}-dirty" if dirty else head


def build_envelope(
    git_lookup: GitLookup = git_state, now: datetime | None = None
) -> dict[str, str]:
    """The three envelope fields every exported JSON file starts with."""
    # `now` is a parameter so a test can pin the clock.
    moment = now or datetime.now(timezone.utc)
    # astimezone(utc) converts any timezone-aware time to UTC, so "Z" is true.
    stamp = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": stamp,
        "source_commit": source_commit(git_lookup),
    }
