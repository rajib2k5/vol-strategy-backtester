"""ADR-0009 test 6, as changed on 2026-10-29: dolt runs only in our private mirror, never in the
shared clone, and the loader only reads.

Three layers, each tested here:
1. the SQL guard (our own code): every statement the loader sends is a plain read;
2. the target: dolt only ever runs in the mirror, and a path that resolves inside the shared
   clone is refused before any process starts;
3. the export checks `dolt status` on the mirror before and after, and refuses a dirty one.

No test touches the real clone or the real mirror. VOL_DATA_DIR points at tmp_path, and the
real-dolt test builds its own tiny "shared clone" and copies it, as the project did.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from volbt import config
from volbt.data import dolthub

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.parametrize("sql", dolthub.LOADER_SQL)
@pytest.mark.parametrize("word", ["INSERT", "UPDATE", "DELETE", "CALL DOLT_", "COMMIT"])
def test_the_loader_sql_contains_no_write(sql, word):
    assert word not in sql.upper()


@pytest.mark.parametrize("sql", dolthub.LOADER_SQL)
def test_the_loader_sql_passes_the_guard(sql):
    dolthub.assert_read_only_sql(sql)


@pytest.mark.parametrize("sql", [
    "INSERT INTO option_chain VALUES (1)",
    "insert into option_chain values (1)",
    "UPDATE option_chain SET bid = 0",
    "DELETE FROM option_chain",
    "CALL DOLT_COMMIT('-am', 'x')",
    "call dolt_gc()",
    "COMMIT",
    "SELECT 1; DELETE FROM option_chain",
    "SELECT * FROM option_chain WHERE 1 = 1; UPDATE option_chain SET bid = 1",
    "  \n delete from option_chain",
    "REPLACE INTO option_chain VALUES (1)",       # not a SELECT/SHOW/DESCRIBE
    "CREATE TABLE x (a int)",
    "SELECT * FROM option_chain WHERE act_symbol = 'SPY'; COMMIT",
    "SELECT DOLT_COMMIT('-am', 'x')",              # dolt's function form of the procedure
    "select dolt_gc()",
    "SELECT * FROM option_chain INTO OUTFILE '/tmp/x.csv'",
])
def test_the_guard_refuses_writes(sql):
    with pytest.raises(dolthub.UnsafeSqlError):
        dolthub.assert_read_only_sql(sql)


def test_a_second_statement_is_refused_even_when_it_names_no_banned_word():
    # DROP is not on the banned list and the first statement is a plain SELECT, so only the
    # one-statement check can stop this one.
    with pytest.raises(dolthub.UnsafeSqlError, match="one statement per call"):
        dolthub.assert_read_only_sql("SELECT 1; DROP TABLE option_chain")
    dolthub.assert_read_only_sql("SELECT 1;")          # a trailing semicolon is still one statement


# Written out here, not read from the module: a test that took the list from the code under
# test would shrink with it.
@pytest.mark.parametrize("word", ["INSERT", "UPDATE", "DELETE", "CALL DOLT_", "COMMIT", "DOLT_", "INTO"])
def test_every_banned_word_is_refused_on_its_own(word):
    # Inside an otherwise plain SELECT and a single statement, so no other check can catch it.
    with pytest.raises(dolthub.UnsafeSqlError, match=word):
        dolthub.assert_read_only_sql(f"SELECT a FROM t WHERE b = 1 {word} x")


def test_the_guard_allows_a_column_that_merely_contains_a_banned_word():
    dolthub.assert_read_only_sql("SELECT updated_at, deleted_flag FROM t")


def test_dolt_sql_refuses_before_running_anything(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("dolt was started")

    monkeypatch.setattr(dolthub, "run_dolt", must_not_run)
    with pytest.raises(dolthub.UnsafeSqlError):
        dolthub.dolt_sql("DELETE FROM option_chain")


# --- where dolt runs ----------------------------------------------------------------------------

@pytest.fixture
def layout(monkeypatch, tmp_path):
    """VOL_DATA_DIR in tmp_path, with a shared clone and a mirror that each look like a dolt repo."""
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "vendors"))
    clone, mirror = config.dolthub_options_dir(), config.dolthub_mirror_dir()
    for folder in (clone, mirror):
        (folder / ".dolt").mkdir(parents=True)
    return {"clone": clone, "mirror": mirror, "work": tmp_path / "work"}


@pytest.fixture
def no_process(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("a process was started")

    monkeypatch.setattr(dolthub.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(dolthub.subprocess, "run", must_not_run)


def test_the_mirror_is_under_this_project_s_cache_and_not_in_the_clone(layout):
    assert layout["mirror"] == config.data_dir() / "vol-strategy-backtester" / "cache" / "dolt_mirror" / "options"
    assert not config.inside_shared_clone(layout["mirror"])


@pytest.mark.parametrize("where", ["the clone", "inside the clone", "a symlink to the clone", "a .. path into the clone"])
def test_dolt_is_never_run_in_the_shared_clone(layout, no_process, tmp_path, where):
    clone = layout["clone"]
    target = {"the clone": clone,
              "inside the clone": clone / ".dolt",
              "a .. path into the clone": layout["mirror"] / ".." / ".." / ".." / ".." / "dolthub" / "options",
              "a symlink to the clone": tmp_path / "looks-private"}[where]
    if where == "a symlink to the clone":
        target.symlink_to(clone)
    with pytest.raises(config.SharedCloneError):
        dolthub.run_dolt(["status"], target, layout["work"])
    with pytest.raises(config.SharedCloneError):
        dolthub.dolt_sql(dolthub.SQL_DESCRIBE, target, layout["work"])


def test_a_work_folder_inside_the_shared_clone_is_refused(layout, no_process):
    # dolt writes its home (DOLT_ROOT_PATH) under the work folder, so that must not be in the clone.
    with pytest.raises(config.SharedCloneError):
        dolthub.run_dolt(["status"], layout["mirror"], layout["clone"] / "work")


def test_without_dolt_nothing_is_run(layout, monkeypatch):
    monkeypatch.setattr(dolthub.shutil, "which", lambda name: None)

    def must_not_run(*args, **kwargs):
        raise AssertionError("a process was started")

    monkeypatch.setattr(dolthub.subprocess, "run", must_not_run)
    with pytest.raises(dolthub.DoltUnavailable):
        dolthub.run_dolt(["status"], None, layout["work"])


def test_by_default_dolt_runs_in_the_mirror_with_its_home_in_the_work_folder(layout, monkeypatch):
    seen = {}

    def fake_run(command, cwd, env, **kwargs):
        seen.update(command=command, cwd=cwd, env=env)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(dolthub.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(dolthub.subprocess, "run", fake_run)
    assert dolthub.dolt_status(None, layout["work"]) == "ok"
    assert seen["command"] == ["dolt", "status"]
    assert Path(seen["cwd"]) == layout["mirror"]
    assert Path(seen["env"]["DOLT_ROOT_PATH"]).is_relative_to(layout["work"])


# --- the export -----------------------------------------------------------------------------------

def _fake_dolt(monkeypatch, statuses=None):
    """Replace run_dolt with canned output, recording every SQL statement sent.

    `statuses` lists what successive `dolt status` calls print (default: clean every time).
    """
    sent = []
    describe = (FIXTURES / "dolthub_describe.csv").read_text(encoding="utf-8")
    rows = (FIXTURES / "dolthub_spy_20rows.csv").read_text(encoding="utf-8")
    clean = "On branch master\nnothing to commit, working tree clean\n"
    queue = list(statuses or [])

    def fake(args, mirror=None, work=None, timeout=0):
        if args[0] == "status":
            return queue.pop(0) if queue else clean
        sql = args[-1]
        sent.append(sql)
        return describe if sql.startswith("DESCRIBE") else rows

    monkeypatch.setattr(dolthub, "run_dolt", fake)
    return sent


DIRTY = "On branch master\nChanges not staged for commit:\n\tmodified: option_chain\n"


def test_the_export_sends_only_the_loader_sql(monkeypatch, tmp_path):
    sent = _fake_dolt(monkeypatch)
    evidence = dolthub.export_spy_rows(tmp_path / "out" / "spy.parquet", tmp_path / "mirror", tmp_path / "work")
    assert sent == list(dolthub.LOADER_SQL)
    assert evidence["rows"] == 20
    assert dolthub.CLEAN_STATUS in evidence["dolt_status_before"] and dolthub.CLEAN_STATUS in evidence["dolt_status_after"]
    assert (tmp_path / "out" / "spy.parquet").exists()


def test_a_dirty_mirror_is_not_read(monkeypatch, tmp_path):
    sent = _fake_dolt(monkeypatch, statuses=[DIRTY])
    with pytest.raises(dolthub.DirtyMirrorError, match="before"):
        dolthub.export_spy_rows(tmp_path / "out" / "spy.parquet", tmp_path / "mirror", tmp_path / "work")
    assert sent == []                                     # not even the DESCRIBE was sent
    assert not (tmp_path / "out" / "spy.parquet").exists()


def test_a_mirror_that_turns_dirty_during_the_export_writes_no_parquet(monkeypatch, tmp_path):
    _fake_dolt(monkeypatch, statuses=["nothing to commit, working tree clean", DIRTY])
    with pytest.raises(dolthub.DirtyMirrorError, match="after"):
        dolthub.export_spy_rows(tmp_path / "out" / "spy.parquet", tmp_path / "mirror", tmp_path / "work")
    assert not (tmp_path / "out" / "spy.parquet").exists()


# --- a real dolt, on a throwaway clone and its copy ------------------------------------------------

def listing(folder: Path) -> list[tuple[str, int, int, int]]:
    """(relative path, size, mtime ns, ctime ns) of every entry: ctime moves on any write."""
    return [(p.relative_to(folder).as_posix(), p.lstat().st_size, p.lstat().st_mtime_ns, p.lstat().st_ctime_ns)
            for p in sorted(folder.rglob("*"))]


@pytest.mark.skipif(shutil.which("dolt") is None, reason="needs dolt on PATH")
def test_a_real_dolt_runs_in_the_mirror_and_leaves_the_clone_alone(layout, tmp_path):
    # Our own throwaway "shared clone", with its own dolt home: nothing outside tmp_path is written.
    clone, mirror = layout["clone"], layout["mirror"]
    shutil.rmtree(clone), shutil.rmtree(mirror)
    clone.mkdir()
    home = tmp_path / "home"
    (home / ".dolt").mkdir(parents=True)
    (home / ".dolt" / "config_global.json").write_text(
        '{"metrics.disabled":"true","user.name":"t","user.email":"t@example.com"}')
    env = {"DOLT_ROOT_PATH": str(home), "PATH": os.environ["PATH"]}
    for args in (["init"], ["sql", "-q", "CREATE TABLE t (a int primary key); INSERT INTO t VALUES (7)"],
                 ["add", "."], ["commit", "-m", "fixture"]):
        subprocess.run(["dolt", *args], cwd=clone, env=env, check=True, capture_output=True)
    subprocess.run(["cp", "-a", str(clone), str(mirror)], check=True)   # how the project made its mirror
    clone_before, mirror_before = listing(clone), listing(mirror)

    out = dolthub.dolt_sql("SELECT a FROM t", None, layout["work"])
    status = dolthub.dolt_status(None, layout["work"])

    assert out.splitlines() == ["a", "7"]
    assert dolthub.CLEAN_STATUS in status
    assert listing(clone) == clone_before            # the shared clone: not a byte, not a timestamp
    assert listing(mirror) != mirror_before          # dolt's housekeeping went to the mirror, as it may


# --- round 2 of the M1 review: the guard may not follow VOL_DATA_DIR (mirror_guard.py's cases) ----
#
# With VOL_DATA_DIR pointed elsewhere, the protected path moved with it: the real clone then passed
# as a mirror, and VOLBT_WORK_DIR=<real clone>/work was accepted. HOME is pointed at tmp_path here,
# so "the default clone" below is a throwaway; the account's real home is tested on its own, with
# the check alone and no process.

@pytest.fixture
def elsewhere(monkeypatch, tmp_path):
    """HOME in tmp_path with a dolt-looking default clone, and VOL_DATA_DIR somewhere else entirely."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    clone = tmp_path / "home" / "data" / "vol-projects" / "dolthub" / "options"
    (clone / ".dolt").mkdir(parents=True)
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "elsewhere"))
    (config.dolthub_mirror_dir() / ".dolt").mkdir(parents=True)
    return {"clone": clone, "work": tmp_path / "work"}


@pytest.mark.parametrize("where", ["the clone", "a symlink to it", "a .. path into it", "a ~ path", "a relative path"])
def test_the_default_clone_is_refused_whatever_vol_data_dir_says(elsewhere, no_process, tmp_path, monkeypatch, where):
    clone = elsewhere["clone"]
    monkeypatch.chdir(tmp_path)
    target = {"the clone": clone,
              "a symlink to it": tmp_path / "looks-private",
              "a .. path into it": clone.parent / "x" / ".." / "options",
              "a ~ path": Path("~/data/vol-projects/dolthub/options"),
              "a relative path": clone.relative_to(tmp_path)}[where]
    if where == "a symlink to it":
        target.symlink_to(clone)
    assert config.dolthub_options_dir() != clone            # VOL_DATA_DIR names another clone
    with pytest.raises(config.SharedCloneError):
        dolthub.run_dolt(["status"], target, elsewhere["work"])


def test_a_work_folder_in_the_default_clone_is_refused_whatever_vol_data_dir_says(elsewhere, no_process, monkeypatch):
    with pytest.raises(config.SharedCloneError):
        dolthub.run_dolt(["status"], None, elsewhere["clone"] / "work")
    monkeypatch.setenv("VOLBT_WORK_DIR", str(elsewhere["clone"] / "work"))
    with pytest.raises(config.SharedCloneError):
        config.work_dir()


def test_the_account_s_real_default_clone_is_refused_whatever_home_says(elsewhere):
    # HOME and VOL_DATA_DIR both point into tmp_path; the account database still names the real
    # home. Only the path checks run: no process, and nothing is read or written there.
    pwd = pytest.importorskip("pwd")
    real = Path(pwd.getpwuid(os.getuid()).pw_dir) / "data" / "vol-projects" / "dolthub" / "options"
    assert config.inside_shared_clone(real) and config.inside_shared_clone(real / "work")
    with pytest.raises(config.SharedCloneError):
        dolthub.mirror_dir(real)


def test_a_mirror_outside_this_project_s_cache_is_refused(elsewhere, no_process, tmp_path):
    stray = tmp_path / "some" / "dolt_copy"
    (stray / ".dolt").mkdir(parents=True)
    with pytest.raises(dolthub.MirrorPathError):
        dolthub.run_dolt(["status"], stray, elsewhere["work"])
    escape = config.dolthub_mirror_dir() / ".." / ".." / ".." / ".." / ".." / "some" / "dolt_copy"
    with pytest.raises(dolthub.MirrorPathError):
        dolthub.run_dolt(["status"], escape, elsewhere["work"])
    # the mirror itself, and a path that only looks odd but resolves to it, are accepted
    assert dolthub.mirror_dir(None) == config.dolthub_mirror_dir()
    assert dolthub.mirror_dir(config.dolthub_mirror_dir() / ".." / "options") is not None
