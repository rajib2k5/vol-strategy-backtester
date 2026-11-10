"""tools/smoke_m4.py on the made-up signal store (milestone 4, part B, task 11): it prints M3's health whitelist and
the s-defined share and nothing else, deletes every ledger it writes, and records its runs past 2019 through the run
gate of a TEMPORARY repository (never the repository's runs_of_record.jsonl). Made-up values only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import engine_helpers as eh
import engine_store as es
import signal_store as ss
from volbt import build

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import prereg  # noqa: E402
import smoke_m4  # noqa: E402

WINDOW = (es.FIRST_SNAPSHOT, es.LAST_SNAPSHOT)
RUNS = tuple((structure, "optionsdx", "quote") for structure in smoke_m4.STRUCTURES) + (
    ("short_straddle", "optionsdx", "surface"),)
# The made-up store holds OptionsDX quotes only, so the smoke's surface run is made on (optionsdx, surface), a stand-in
# for the tool's (dolthub, surface). The gate accepts a health run only on the tools' pairs (prereg.HEALTH_PAIRS; fix
# pass 6, item H4), so the tests that run the stand-in through the real gate add it to the smoke's pairs.
STAND_IN = ("optionsdx", "surface")


def accept_the_stand_in(monkeypatch) -> None:
    monkeypatch.setitem(prereg.HEALTH_PAIRS, "smoke", (*prereg.HEALTH_PAIRS["smoke"], STAND_IN))
WHITELIST = ("== health:", "run_id ", "timings ", "cash = initial", "marks per open lot", "mark sources",
             "mark flags", "DEGRADED days", "orders: ", "option fills", "hedge rows", "event ",
             "P&L, NAV levels and returns: not printed", "## smoke: ", "s defined on ", "ledger deleted: ")


def temp_repo(root: Path) -> Path:
    """A throwaway git repository holding an empty, committed spent.jsonl: what the run gate reads (never the
    project's repository)."""
    repo = root / "repo"
    directory = prereg.prereg_dir(repo)
    directory.mkdir(parents=True)
    (directory / prereg.SPENT).write_text("")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(root), "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1"}
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "made up")):
        subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c",
                        "commit.gpgsign=false", "-C", str(repo), *args], check=True, capture_output=True, env=env)
    assert repo.resolve() != prereg.REPO
    return repo


def repo_record_hash():
    path = prereg.prereg_dir(prereg.REPO) / prereg.RECORDS
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return ss.signal_store(tmp_path_factory.mktemp("smoke_store"))


def test_the_smoke_prints_the_whitelist_and_the_share_and_deletes_its_ledgers(store, tmp_path, capsys, monkeypatch):
    accept_the_stand_in(monkeypatch)
    before = repo_record_hash()
    runs_root, repo = tmp_path / "runs", temp_repo(tmp_path)
    shares = smoke_m4.smoke(store, runs_root, prereg.make_run_gate(repo), runs=RUNS, window=WINDOW)
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert lines and all(line.startswith(WHITELIST) for line in lines), [l for l in lines if not l.startswith(WHITELIST)]
    assert sum(line.startswith("ledger deleted: ") for line in lines) == len(RUNS) == len(shares)
    assert not any(runs_root.glob("run_id=*"))
    # The share is the signals table's: the same run, kept, counts the same sessions with s defined.
    for structure, source, mode, defined, total in shares:
        kept = eh.run(store, tmp_path / f"kept_{structure}_{mode}", smoke_m4.smoke_strategy(structure, source),
                      **{k: v for k, v in vars(smoke_m4.smoke_config(source, mode, *WINDOW)).items()
                         if k not in ("sample_start", "sample_end", "split")})
        signals = eh.table(kept, "signals")
        assert (defined, total) == (int(signals["log_var_ratio"].notna().sum()), len(signals))
        assert 0 < defined < total
    # The runs past 2019 went to the temporary repository's record, as diagnostics; the repository's is untouched.
    # Fix pass 2 (item 3): a started and a completed line per run, merged by prereg.runs_of_record.
    lines = [json.loads(line) for line in (prereg.prereg_dir(repo) / prereg.RECORDS).read_text().splitlines()]
    assert [line["event"] for line in lines] == ["started", "completed"] * len(RUNS)
    records = prereg.runs_of_record(repo)
    assert len(records) == len(RUNS) and {r["run_purpose"] for r in records} == {"diagnostic"}
    assert all(r["completed"] for r in records)
    assert repo_record_hash() == before


def test_the_budget_run_deletes_its_ledger(store, tmp_path, capsys):
    runs_root = tmp_path / "runs"
    out = smoke_m4.budget(store, runs_root, prereg.make_run_gate(temp_repo(tmp_path)), "short_strangle", window=WINDOW)
    assert out["timings"]["total_s"] > 0 and out["sessions"] > 70
    assert not any(runs_root.glob("run_id=*"))
    assert all(line.startswith(("budget: ", "run_id ", "timings ", "ledger deleted: "))
               for line in capsys.readouterr().out.splitlines() if line.strip())


def test_a_smoke_that_crashed_at_its_third_run_is_run_again_with_a_reason_and_completes(store, tmp_path,
                                                                                          monkeypatch, capsys):
    """Fix pass 5, item G1 (review F claim 5): the smoke crashes in its third run, after the gate recorded that run's
    "started" line. Run again whole without a reason, it is refused at its first run (a re-run); with --rerun-reason
    every run passes, because a health run counts per trial_hash, kind, data source and execution mode: the runs done
    become second runs, the crashed one a second run, the one never reached a first. (Fix pass 4 counted the two runs
    of one structure together and refused the second run of the re-run.)"""
    accept_the_stand_in(monkeypatch)
    runs = (("short_straddle", "optionsdx", "quote"), ("short_straddle", "optionsdx", "surface"),
            ("short_strangle", "optionsdx", "quote"), ("long_straddle", "optionsdx", "quote"))
    runs_root, repo = tmp_path / "runs", temp_repo(tmp_path)
    real, calls = smoke_m4.run_backtest, []

    def crashing(cfg, strategy, **kwargs):
        calls.append(cfg)
        if len(calls) == 3:
            def crash(t, book):
                raise RuntimeError("the third run crashed (made up)")
            kwargs["on_session_end"] = crash
        return real(cfg, strategy, **kwargs)

    monkeypatch.setattr(smoke_m4, "run_backtest", crashing)
    with pytest.raises(RuntimeError, match="crashed"):
        smoke_m4.smoke(store, runs_root, prereg.make_run_gate(repo), runs=runs, window=WINDOW)
    monkeypatch.setattr(smoke_m4, "run_backtest", real)
    assert [(r["completed"], r["rerun_reason"]) for r in prereg.runs_of_record(repo)] == [
        (True, None), (True, None), (False, None)]
    with pytest.raises(prereg.PreregError, match="needs a reason"):
        smoke_m4.smoke(store, runs_root, prereg.make_run_gate(repo), runs=runs, window=WINDOW)
    shares = smoke_m4.smoke(store, runs_root, prereg.make_run_gate(repo, rerun_reason="the third run crashed"),
                            runs=runs, window=WINDOW)
    assert [share[:3] for share in shares] == list(runs)
    assert not any(runs_root.glob("run_id=*"))
    records = prereg.runs_of_record(repo)
    assert [(r["completed"], r["rerun_reason"]) for r in records] == [(True, None)] * 2 + [(False, None)] + [
        (True, "the third run crashed")] * 4
    assert {r["diagnostic_kind"] for r in records} == {"smoke"}
    capsys.readouterr()


def recorder_fails(cfg, strategy, trial_hash):
    def record(run_id, config_hash):
        raise OSError("runs_of_record.jsonl not writable (made up)")
    return record


def second_check_fails():
    calls = []

    def check(store):
        calls.append(1)
        build.require_current(store)
        if len(calls) == 2:
            raise RuntimeError("the store is no longer current (made up)")
    return check


@pytest.mark.parametrize("failure", ["recorder after the rename", "store check after the write"])
def test_a_run_that_raises_after_writing_leaves_no_ledger(store, tmp_path, failure):
    """Fix pass 2, item 19 (review C claim 8, c8_leftover.py): run_backtest raises after its ledger is written (the
    folder renamed, or still .tmp); smoke() and budget() remove it before the error goes on."""
    for name, call in (("smoke", lambda root, kw: smoke_m4.smoke(store, root, runs=RUNS[:1], window=WINDOW, **kw)),
                       ("budget", lambda root, kw: smoke_m4.budget(store, root, structure="short_straddle",
                                                                   window=WINDOW, **kw))):
        runs_root = tmp_path / name
        kw = ({"run_gate": recorder_fails} if failure.startswith("recorder")
              else {"run_gate": eh.made_up_gate, "store_check": second_check_fails()})
        with pytest.raises((OSError, RuntimeError), match="made up"):
            call(runs_root, kw)
        assert runs_root.is_dir() and not list(runs_root.glob("run_id=*")), (name, list(runs_root.iterdir()))


def test_the_tools_hand_run_backtest_the_pre_registration_gate(monkeypatch, tmp_path):
    """Review B's B5 (fix pass 3, item D6): the engine trusts the gate it is handed, so the tools must hand it the
    gate prereg.make_run_gate returns. Both tools' mains run with make_run_gate and run_backtest replaced by spies
    (no store is read, nothing is run or recorded): the gate run_backtest receives is the one make_run_gate made,
    with the tool's re-run reason; the smoke's run is a "smoke" diagnostic and the budget run a "budget" one."""
    import run_backtest as tool

    made, seen = [], []

    def make_run_gate(*args, **kwargs):
        def gate(cfg, strategy, trial_hash):
            return None
        made.append((gate, kwargs))
        return gate

    class Stop(Exception):
        pass

    def spy(cfg, strategy, **kwargs):
        seen.append((cfg, kwargs["run_gate"]))
        raise Stop

    monkeypatch.setattr(prereg, "make_run_gate", make_run_gate)
    for module in (tool, smoke_m4):
        monkeypatch.setattr(module, "run_backtest", spy)
        monkeypatch.setattr(module, "source_commit", lambda: "0" * 40)
    roots = ["--store", str(tmp_path / "store"), "--runs-root", str(tmp_path / "runs")]
    with pytest.raises(Stop):
        tool.main(["--start", "2021-01-04", "--end", "2021-06-30", "--split", "validation", "--mode", "surface",
                   "--diagnostic-kind", "surface_s", "--rerun-reason", "r1", *roots])
    with pytest.raises(Stop):
        smoke_m4.main(["--rerun-reason", "r2", *roots])
    with pytest.raises(Stop):
        smoke_m4.main(["--budget", "short_straddle", *roots])
    assert len(made) == len(seen) == 3
    assert all(gate is handed for (gate, _), (_, handed) in zip(made, seen))
    assert [kwargs.get("rerun_reason") for _, kwargs in made] == ["r1", "r2", None]
    assert [cfg.diagnostic_kind for cfg, _ in seen] == ["surface_s", "smoke", "budget"]


def test_the_gate_accepts_health_runs_on_the_pairs_the_tools_run_and_on_no_other(monkeypatch, tmp_path):
    """Fix pass 6, item H4 (review G claim 1): prereg.HEALTH_PAIRS, the only (data source, execution mode) pairs the
    gate accepts for a smoke or budget run, are the pairs of the configs smoke() and budget() hand to run_backtest, for
    every smoke run and every structure's budget run. run_or_clean is replaced by a spy: nothing is run or recorded.
    Without the stand-in, the gate refuses the tests' (optionsdx, surface) smoke."""
    seen = {"smoke": set(), "budget": set()}

    class Stop(Exception):
        pass

    def spy(cfg, strategy, *args):
        seen[cfg.diagnostic_kind].add((cfg.data_source, cfg.execution_mode))
        raise Stop

    monkeypatch.setattr(smoke_m4, "run_or_clean", spy)
    for run in smoke_m4.SMOKE_RUNS:
        with pytest.raises(Stop):
            smoke_m4.smoke(None, tmp_path, None, runs=(run,))
    for structure in smoke_m4.STRUCTURES:
        with pytest.raises(Stop):
            smoke_m4.budget(None, tmp_path, None, structure)
    assert {kind: sorted(pairs) for kind, pairs in seen.items()} == \
        {kind: sorted(pairs) for kind, pairs in prereg.HEALTH_PAIRS.items()}
    assert STAND_IN not in prereg.HEALTH_PAIRS["smoke"]
    gate = prereg.make_run_gate(temp_repo(tmp_path))
    cfg = smoke_m4.smoke_config(*STAND_IN, *smoke_m4.VALIDATION)
    with pytest.raises(prereg.PreregError, match="a smoke run on optionsdx surface is refused: no tool runs one"):
        gate(cfg, smoke_m4.smoke_strategy("short_straddle", "optionsdx"), "t" * 64)
