"""Tests for volbt.contract. The fake git lookup means most tests need no git at all;
the last group uses a throwaway real git repo to check the real lookup."""

import os
import re
import shutil
import stat
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from volbt import contract

SHA = "0123456789abcdef0123456789abcdef01234567"
FIXED_NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)


# --- the envelope, with a fake git lookup ---------------------------------------------

def test_envelope_has_exactly_the_three_keys():
    envelope = contract.build_envelope(lambda: (SHA, False), FIXED_NOW)
    assert set(envelope) == {"schema_version", "generated_at", "source_commit"}


def test_schema_version_is_pinned():
    assert contract.SCHEMA_VERSION == "0.1.0"
    assert contract.build_envelope(lambda: (SHA, False), FIXED_NOW)["schema_version"] == "0.1.0"


def test_generated_at_is_utc_iso_with_z():
    envelope = contract.build_envelope(lambda: (SHA, False), FIXED_NOW)
    assert envelope["generated_at"] == "2026-10-27T12:00:00Z"


def test_generated_at_converts_other_timezones_to_utc():
    # 17:00 at UTC+5 is 17 - 5 = 12:00 UTC. Printing 17:00 with a "Z" would be wrong by 5 hours.
    plus_five = timezone(timedelta(hours=5))
    now = datetime(2026, 10, 27, 17, 0, 0, tzinfo=plus_five)
    assert contract.build_envelope(lambda: (SHA, False), now)["generated_at"] == "2026-10-27T12:00:00Z"


def test_generated_at_defaults_to_the_current_time():
    before = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = contract.build_envelope(lambda: (SHA, False))["generated_at"]
    after = datetime.now(timezone.utc)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)
    parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    # The stamp drops fractional seconds, so it can be up to 1 s before the real time.
    assert before <= parsed <= after


def test_source_commit_clean():
    assert contract.source_commit(lambda: (SHA, False)) == SHA


def test_source_commit_dirty_gets_suffix():
    assert contract.source_commit(lambda: (SHA, True)) == SHA + "-dirty"


def test_source_commit_without_head_is_uncommitted():
    assert contract.source_commit(lambda: (None, False)) == "uncommitted"
    # No HEAD means there is nothing to be dirty relative to.
    assert contract.source_commit(lambda: (None, True)) == "uncommitted"


# --- the real lookup, against a throwaway git repo ------------------------------------

def run_git(repo, *args):
    # Identity and signing are passed per command so the test works on any machine's git config.
    base = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "-c", "commit.gpgsign=false"]
    result = subprocess.run([*base, *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    run_git(tmp_path, "init", "-q")
    return tmp_path


def commit_a_file(repo):
    (repo / "a.txt").write_text("one\n")
    run_git(repo, "add", "a.txt")
    run_git(repo, "commit", "-q", "-m", "first")
    return run_git(repo, "rev-parse", "HEAD")


def test_real_lookup_repo_without_commits(repo):
    assert contract.git_state(repo) == (None, False)


def test_real_lookup_outside_any_repo(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    # Stop git searching parent folders for a repo.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert contract.git_state(tmp_path) == (None, False)


def test_real_lookup_clean_repo(repo):
    head = commit_a_file(repo)
    assert len(head) == 40
    assert contract.git_state(repo) == (head, False)


def test_real_lookup_modified_file_is_dirty(repo):
    head = commit_a_file(repo)
    (repo / "a.txt").write_text("two\n")
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_untracked_file_is_dirty(repo):
    head = commit_a_file(repo)
    (repo / "new.txt").write_text("x\n")
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_ignores_the_generated_data_folder(repo):
    head = commit_a_file(repo)
    # Re-running the exporter rewrites these files; that must not flip a clean tree to dirty.
    generated = repo / "app" / "public" / "data"
    generated.mkdir(parents=True)
    (generated / "manifest.json").write_text("{}\n")
    assert contract.git_state(repo) == (head, False)


# --- the real lookup must fail CLOSED ---------------------------------------------------
# A stamp that says "clean" is a claim that the code is reproducible from the hash. When git
# cannot tell us, or the local git config hides changes, the honest answer is "dirty".

def test_real_lookup_corrupt_index_counts_as_dirty(repo):
    head = commit_a_file(repo)
    (repo / "a.txt").write_text("two\n")
    # Truncate the index: `git rev-parse HEAD` still works (it reads refs), but
    # `git status` exits 128 ("index file smaller than expected").
    index = repo / ".git" / "index"
    index.write_bytes(index.read_bytes()[:20])
    # Guard the scenario itself, so this test cannot pass for the wrong reason.
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True).returncode == 0
    assert subprocess.run(["git", "status"], cwd=repo, capture_output=True).returncode != 0
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_corrupt_index_on_an_unmodified_tree_is_still_dirty(repo):
    head = commit_a_file(repo)
    index = repo / ".git" / "index"
    index.write_bytes(index.read_bytes()[:20])
    # Nothing was edited, but we cannot verify that, and "unverifiable" must not read as "clean".
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_sees_untracked_files_even_if_config_hides_them(repo):
    head = commit_a_file(repo)
    run_git(repo, "config", "status.showUntrackedFiles", "no")
    (repo / "new.txt").write_text("x\n")
    # Precondition: with this config a plain `git status --porcelain` prints nothing.
    assert run_git(repo, "status", "--porcelain") == ""
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_sees_a_modified_submodule_even_if_config_ignores_submodules(repo, tmp_path_factory):
    # A second repo to use as the submodule.
    inner = tmp_path_factory.mktemp("inner")
    run_git(inner, "init", "-q")
    (inner / "s.txt").write_text("s\n")
    run_git(inner, "add", "s.txt")
    run_git(inner, "commit", "-q", "-m", "inner")
    # protocol.file.allow: git blocks local-path submodule clones by default.
    run_git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "libsub")
    run_git(repo, "commit", "-q", "-m", "add submodule")
    head = run_git(repo, "rev-parse", "HEAD")
    (repo / "libsub" / "s.txt").write_text("changed\n")
    run_git(repo, "config", "diff.ignoreSubmodules", "all")
    # Precondition: with this config a plain `git status --porcelain` hides the change.
    assert run_git(repo, "status", "--porcelain") == ""
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_sees_an_edit_hidden_by_assume_unchanged(repo):
    head = commit_a_file(repo)
    run_git(repo, "update-index", "--assume-unchanged", "a.txt")
    (repo / "a.txt").write_text("two\n")
    # Precondition: git itself no longer reports the edit.
    assert run_git(repo, "status", "--porcelain") == ""
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_sees_an_edit_hidden_by_skip_worktree(repo):
    head = commit_a_file(repo)
    run_git(repo, "update-index", "--skip-worktree", "a.txt")
    (repo / "a.txt").write_text("two\n")
    assert run_git(repo, "status", "--porcelain") == ""
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_sees_a_new_file_hidden_by_info_exclude(repo):
    head = commit_a_file(repo)
    (repo / ".git" / "info" / "exclude").write_text("new.txt\n")
    (repo / "new.txt").write_text("x\n")
    # Precondition: even with every untracked file listed, git says nothing.
    assert run_git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_sees_a_new_file_hidden_by_the_global_excludes_file(repo, tmp_path_factory, monkeypatch):
    head = commit_a_file(repo)
    home = tmp_path_factory.mktemp("home")
    (home / "ignore").write_text("new.txt\n")
    global_config = home / "gitconfig"
    global_config.write_text(f"[core]\n\texcludesFile = {home / 'ignore'}\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    (repo / "new.txt").write_text("x\n")
    assert run_git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert contract.git_state(repo) == (head, True)


def test_real_lookup_still_honours_the_repos_own_gitignore(repo):
    # A committed .gitignore is part of the code the hash identifies, so what it hides is not a change.
    (repo / ".gitignore").write_text("scratch.txt\n")
    run_git(repo, "add", ".gitignore")
    head = commit_a_file(repo)
    (repo / "scratch.txt").write_text("x\n")
    assert contract.git_state(repo) == (head, False)


def test_real_lookup_ignores_a_hidden_edit_inside_the_generated_data_folder(repo):
    commit_a_file(repo)
    generated = repo / "app" / "public" / "data"
    generated.mkdir(parents=True)
    (generated / "manifest.json").write_text("{}\n")
    run_git(repo, "add", "app/public/data/manifest.json")
    run_git(repo, "commit", "-q", "-m", "generated")
    head = run_git(repo, "rev-parse", "HEAD")
    run_git(repo, "update-index", "--assume-unchanged", "app/public/data/manifest.json")
    (generated / "manifest.json").write_text('{"changed": true}\n')
    (generated / "extra.json").write_text("{}\n")
    assert contract.git_state(repo) == (head, False)


# --- a hung git ------------------------------------------------------------------------
# Real hangs, not a mocked subprocess: a `git status` that blocks on an fsmonitor hook, and a
# `git` on PATH whose rev-parse never returns.

@pytest.fixture
def hang_status(repo, tmp_path_factory, monkeypatch):
    """Returns arm(): make `git status` in `repo` block on a core.fsmonitor hook that also starts
    a long-lived child, and shorten the timeout to 1 s. arm() returns the file the hook writes its
    own pid and its child's pid into (one line per run). Call it AFTER committing, because the
    hook would block `git add` and `git commit` too."""
    pids = tmp_path_factory.mktemp("hook") / "pids"

    def arm():
        hook = pids.parent / "hook.sh"
        hook.write_text(f"#!/bin/sh\nsleep 300 &\necho $$ $! >> '{pids}'\nwait\n")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        run_git(repo, "config", "core.fsmonitor", str(hook))
        monkeypatch.setattr(contract, "GIT_TIMEOUT_SECONDS", 1)
        return pids

    yield arm
    if pids.exists():  # leave nothing running, even when the code under test fails to clean up
        for pid in pids.read_text().split():
            try:
                os.kill(int(pid), 9)
            except ProcessLookupError:
                pass


def test_a_hung_git_status_counts_as_dirty(repo, hang_status):
    head = commit_a_file(repo)
    pids = hang_status()
    started = time.monotonic()
    assert contract.git_state(repo) == (head, True)
    assert time.monotonic() - started < 20  # it gave up after the (patched) 1 s, it did not wait out the hook
    assert pids.exists()  # the hook really ran, so the hang was real


def _running(pid):
    """True if the process exists and is not a zombie (a killed orphan stays a zombie until reaped)."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"


@pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="needs /proc to inspect other processes")
def test_a_timeout_kills_gits_children_too(repo, hang_status):
    commit_a_file(repo)
    pids = hang_status()
    contract.git_state(repo)
    hook_pid, child_pid = map(int, pids.read_text().split()[:2])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and (_running(hook_pid) or _running(child_pid)):
        time.sleep(0.05)
    assert not _running(hook_pid), "the fsmonitor hook outlived the timeout"
    assert not _running(child_pid), "the hook's child outlived the timeout"


def test_a_hung_rev_parse_gives_no_commit(repo, tmp_path_factory, monkeypatch):
    commit_a_file(repo)
    real_git = shutil.which("git")
    bin_dir = tmp_path_factory.mktemp("bin")
    fake = bin_dir / "git"
    fake.write_text(f'#!/bin/sh\n[ "$1" = rev-parse ] && exec sleep 300\nexec "{real_git}" "$@"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(contract, "GIT_TIMEOUT_SECONDS", 1)
    # No HEAD to point at: the stamp becomes "uncommitted", never a made-up clean hash.
    assert contract.git_state(repo) == (None, False)


def test_every_git_call_has_a_timeout(repo, monkeypatch):
    commit_a_file(repo)
    timeouts = []

    class Spy(subprocess.Popen):
        def communicate(self, input=None, timeout=None):
            timeouts.append(timeout)
            return super().communicate(input, timeout)

    monkeypatch.setattr(contract.subprocess, "Popen", Spy)
    contract.git_state(repo)
    # rev-parse, status, ls-files -v (hidden edits) and ls-files --others (untracked files).
    assert len(timeouts) == 4
    assert all(isinstance(t, (int, float)) and 0 < t <= 120 for t in timeouts)


@pytest.mark.parametrize("object_format, hex_length", [("sha1", 40), ("sha256", 64)])
def test_real_lookup_hash_fits_the_apps_7_to_64_hex_pattern(tmp_path, object_format, hex_length):
    # app/src/lib/contract.ts accepts source_commit as [0-9a-f]{7,64}. A SHA-256 repository
    # (git init --object-format=sha256) writes 64 hex digits, which the old {7,40} refused.
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    try:
        run_git(tmp_path, "init", "-q", f"--object-format={object_format}")
    except subprocess.CalledProcessError:
        pytest.skip(f"this git cannot create {object_format} repositories")
    head = commit_a_file(tmp_path)
    assert contract.git_state(tmp_path) == (head, False)
    assert len(head) == hex_length
    assert re.fullmatch(r"[0-9a-f]{7,64}", head)
    assert re.fullmatch(r"[0-9a-f]{7,64}-dirty", contract.source_commit(lambda: (head, True)))
