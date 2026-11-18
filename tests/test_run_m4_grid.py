"""tools/run_m4_grid.py (milestone 4, part B2a): the RV model by the decision rule, the grid's runs and the trial log.

decided_rv_model is checked on throwaway repositories holding a MADE-UP scored forecast test (tests/m4_repo.py), and
read once on this repository's committed result (read-only). The runs use the made-up signal store (its sessions are
in 2023, so they run as validation diagnostics through a made-up gate, as tests/test_export_m4.py's do): a pool and a
single process give byte-identical ledgers, and the trial log has a line for every run and no line without a run.
Nothing here writes to the repository's trial log or ledgers. Made-up values only.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

import engine_helpers as eh
import engine_store as es
import m4_repo
import signal_store as ss
from volbt.engine.loop import EngineError
from volbt.engine.run_config import RunConfig
from volbt.strategies.grid import m4_grid
from volbt.strategies.rules import EntryRule, ExitRules
from volbt.strategies.vol import VolStrategy

import prereg  # noqa: E402  (tools/ is on sys.path through m4_repo)
import run_m4_grid as grid  # noqa: E402

ID = m4_repo.ID


def pin_of(repo: Path) -> dict:
    """The made-up result's pin: its file's SHA-256 as it is on disk (a made-up id has no PINNED_RESULTS entry)."""
    return {ID: m4_repo.sha256(prereg.prereg_dir(repo) / f"{ID}.result.json")}


def decided(repo: Path, pins: dict | None = None) -> str:
    return grid.decided_rv_model(repo, ID, pin_of(repo) if pins is None else pins)


# --- the RV model, by the decision rule ------------------------------------------------------------------------------

def test_a_committed_consistent_result_gives_its_decision(tmp_path):
    assert decided(m4_repo.scored_repo(tmp_path / "har", p=0.01, decision="har")) == "har"
    assert decided(m4_repo.scored_repo(tmp_path / "naive", p=0.3, decision="naive")) == "naive"


def test_a_result_file_edited_after_its_commit_is_refused(tmp_path):
    repo = m4_repo.scored_repo(tmp_path)
    path = prereg.prereg_dir(repo) / f"{ID}.result.json"
    path.write_text(path.read_text().replace('"p": 0.01', '"p": 0.011'))
    with pytest.raises(grid.DecisionError, match=r"result\.json is not committed"):
        decided(repo)


def test_a_result_line_with_another_hash_is_refused(tmp_path):
    repo = m4_repo.scored_repo(tmp_path, line_changes={"result_sha256": "0" * 64})
    with pytest.raises(grid.DecisionError, match="not the '0000"):
        decided(repo)


def test_a_result_that_names_another_sha256_file_is_refused(tmp_path):
    repo = m4_repo.scored_repo(tmp_path, result_changes={"prereg_sha256": "e" * 64})
    with pytest.raises(grid.DecisionError, match="is not the SHA-256"):
        decided(repo)


def test_no_result_line_or_a_second_one_in_git_is_refused(tmp_path):
    repo = m4_repo.scored_repo(tmp_path / "none")
    spent = prereg.prereg_dir(repo) / prereg.SPENT
    spent.write_text(spent.read_text().splitlines()[0] + "\n")
    m4_repo.commit(repo, "the result line removed")
    with pytest.raises(grid.DecisionError, match="holds 0 result line"):
        decided(repo)
    # A second scoring: an earlier commit's spent.jsonl held another result line for the id.
    repo = m4_repo.scored_repo(tmp_path / "two")
    spent = prereg.prereg_dir(repo) / prereg.SPENT
    kept = spent.read_text()
    lines = [json.loads(text) for text in kept.splitlines()]
    spent.write_text(kept + json.dumps({**lines[1], "date": "2026-11-18"}, sort_keys=True) + "\n")
    m4_repo.commit(repo, "a second result line")
    spent.write_text(kept)
    m4_repo.commit(repo, "the second line removed again")
    with pytest.raises(grid.DecisionError, match="a second scoring"):
        decided(repo)


def test_a_decision_that_does_not_follow_the_registered_rule_is_refused(tmp_path):
    for name, kwargs in (("high", dict(p=0.03, decision="har")), ("low", dict(p=0.01, decision="naive"))):
        with pytest.raises(grid.DecisionError, match="does not follow the rule"):
            decided(m4_repo.scored_repo(tmp_path / name, **kwargs))


def test_a_p_exactly_at_the_threshold_is_naive(tmp_path):
    """The rule is p < threshold: p = 0.025 is not below it (a `<=` would give har)."""
    assert decided(m4_repo.scored_repo(tmp_path / "naive", p=0.025, decision="naive")) == "naive"
    with pytest.raises(grid.DecisionError, match="does not follow the rule"):
        decided(m4_repo.scored_repo(tmp_path / "har", p=0.025, decision="har"))


def test_a_p_of_exactly_1_is_inside_the_range(tmp_path):
    assert decided(m4_repo.scored_repo(tmp_path, p=1.0, decision="naive")) == "naive"


def test_a_result_threshold_other_than_the_registered_one_is_refused(tmp_path):
    """p 0.01 is har at the registered 0.025 and at the result's 0.05, so only the threshold check refuses it."""
    repo = m4_repo.scored_repo(tmp_path, p=0.01, decision="har", result_changes={"threshold": 0.05})
    with pytest.raises(grid.DecisionError, match="is not the registered"):
        decided(repo)


def test_a_result_line_with_another_prereg_hash_is_refused(tmp_path):
    repo = m4_repo.scored_repo(tmp_path, line_changes={"prereg_sha256": "d" * 64})
    with pytest.raises(grid.DecisionError, match="result line's prereg_sha256"):
        decided(repo)


def test_a_pre_registration_whose_candidate_and_benchmark_are_not_har_and_naive_is_refused(tmp_path):
    repo = m4_repo.scored_repo(tmp_path, spec_changes={"benchmark": {"name": "naive2", "trial_hash": None}})
    with pytest.raises(grid.DecisionError, match=r"candidate and benchmark are \['har', 'naive2'\]"):
        decided(repo)


def test_a_side_ledger_with_a_second_result_line_is_refused(tmp_path):
    """Git history holds one result line; only the side ledger (in the git common directory) holds a second."""
    repo = m4_repo.scored_repo(tmp_path)
    lines = [json.loads(text) for text in (prereg.prereg_dir(repo) / prereg.SPENT).read_text().splitlines()]
    side = prereg.common_dir(repo) / prereg.SIDE_SPENT
    side.write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in
                            [*lines, {**lines[1], "date": "2026-11-18", "result_sha256": "1" * 64}]))
    with pytest.raises(grid.DecisionError, match="a second scoring"):
        decided(repo)


@pytest.mark.parametrize("value", [True, "0.01", None])
def test_a_p_that_is_not_a_number_is_refused(value, tmp_path):
    """p = True would read as 1, which the range allows and a naive decision follows: only the type check refuses."""
    repo = m4_repo.scored_repo(tmp_path, p=value, decision="naive")
    with pytest.raises(grid.DecisionError, match="the p .* is not a number"):
        decided(repo)


@pytest.mark.parametrize("p", [-1.0, 0.0, 1.5, float("nan"), float("inf")])
def test_a_p_outside_0_1_or_not_finite_is_refused(p, tmp_path):
    """Each would follow the rule (p below the threshold gives har; the others naive) were there no range check."""
    repo = m4_repo.scored_repo(tmp_path, p=p, decision="har" if p < 0.025 else "naive")
    with pytest.raises(grid.DecisionError, match=r"the p .* is not a finite number in \(0, 1\]"):
        decided(repo)


@pytest.mark.parametrize("threshold", [True, 0.0, 1.0, -0.1, float("nan")])
def test_a_threshold_that_is_not_a_number_in_0_1_is_refused(threshold, tmp_path):
    repo = m4_repo.scored_repo(tmp_path, threshold=threshold, p=0.01, decision="har")
    with pytest.raises(grid.DecisionError, match="the threshold .* is not"):
        decided(repo)


def test_a_result_that_is_not_the_pinned_record_is_refused(tmp_path):
    """Everything else holds (files, ledger line, git): a forged record in a fresh repository, as forge.sh's S3 and
    S4 made it, differs from the pinned SHA-256 only."""
    repo = m4_repo.scored_repo(tmp_path / "pin", p=0.03, decision="naive")
    assert decided(repo) == "naive"
    with pytest.raises(grid.DecisionError, match="not the pinned " + "9" * 64):
        decided(repo, {ID: "9" * 64})


def test_an_id_that_is_not_pinned_is_refused(tmp_path):
    repo = m4_repo.scored_repo(tmp_path)
    with pytest.raises(grid.DecisionError, match="is not pinned"):
        decided(repo, {})


def test_the_pin_names_the_scoring_commit_s_result():
    assert grid.PINNED_RESULTS == {prereg.FORECAST_ID: "66e07390c6772cd0a5c852aaff5176b5a336c2be90f0d94e2c829e2fa0c00fcc"}


def test_this_repository_s_committed_result_gives_har():
    """The forecast test scored once on 2026-11-17 (p 0.0139 < 0.025): read from the committed files, nothing run."""
    assert grid.decided_rv_model() == "har"


# --- the runs ---------------------------------------------------------------------------------------------------------

def test_the_tasks_are_the_36_grid_entries_on_the_development_split():
    tasks = grid.grid_tasks("har")
    assert [task.label for task in tasks] == [entry.label for entry in m4_grid("har")]
    assert {(t.cfg.sample_start, t.cfg.sample_end, t.cfg.split, t.cfg.run_purpose, t.cfg.data_source,
             t.cfg.execution_mode) for t in tasks} == {(date(2010, 1, 4), date(2019, 12, 31), "development", "trial",
                                                        "optionsdx", "quote")}
    assert {task.strategy.signal.rv_model for task in tasks} == {"har"}
    assert [t.label for t in grid.grid_tasks("har", only="long_straddle/always/dte")] == ["long_straddle/always/dte"]
    with pytest.raises(ValueError, match="no grid entry"):
        grid.grid_tasks("har", only="made-up")


def test_the_tool_hands_run_backtest_the_pre_registration_s_gate(tmp_path):
    """gate_of(None), what main() leads to, is prereg.make_run_gate: it refuses a diagnostic past 2019 that names no
    kind (a made-up gate passes it)."""
    cfg = RunConfig(sample_start=date(2021, 1, 4), sample_end=date(2021, 6, 30), split="validation")
    with pytest.raises(prereg.PreregError, match="names its diagnostic_kind"):
        grid.gate_of(None)(cfg, None, "f" * 64)
    assert grid.gate_of(eh.made_up_gate) is eh.made_up_gate


@pytest.mark.parametrize("error", [grid.DecisionError("made up"), prereg.PreregError("made up")])
def test_main_refuses_when_the_decision_does_not_check_and_runs_nothing(error, monkeypatch, tmp_path, capsys):
    """A DecisionError, or the PreregError a symlinked result file gives (prereg.committed): one line, exit 2."""
    def refuse(*args, **kwargs):
        raise error

    ran = []
    monkeypatch.setattr(grid, "decided_rv_model", refuse)
    monkeypatch.setattr(grid, "run_grid", lambda *a, **k: ran.append(a))
    assert grid.main(["--trial-log", str(tmp_path / "log.jsonl"), "--runs-root", str(tmp_path)]) == 2
    assert capsys.readouterr().err == "refused: made up\n" and ran == []


@pytest.mark.parametrize("workers", [0, 5, 2.0])
def test_more_than_four_workers_is_refused(workers, tmp_path):
    with pytest.raises(ValueError, match="workers must be an int in 1..4"):
        grid.run_grid([], tmp_path, tmp_path, tmp_path / "log.jsonl", workers=workers)


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return ss.signal_store(tmp_path_factory.mktemp("grid_store"))


def made_up_tasks() -> list[grid.Task]:
    """Two of the grid's kinds on the made-up store's sessions: a gated straddle with every exit, an `always` calendar."""
    out = []
    for label, structure, entry, exits in (
            ("short_straddle/above_0.0/dte+signal+pt_sl", "short_straddle", EntryRule("above", 0.0),
             ExitRules(14, 1.0, 0.5, -0.4)),
            ("straddle_calendar/always/dte", "straddle_calendar", EntryRule(), ExitRules(14))):
        cfg = eh.config(trial_group="m4_vol", hedge_mode="time", hedge_every_n=1, hedge_timing="same_close")
        out.append(grid.Task(label, cfg, VolStrategy(structure, "short", entry, exits)))
    return out


def ledger_hashes(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "run_meta.json").read_text())["files"]


def test_a_pool_and_one_process_give_the_same_ledgers_and_every_run_has_one_log_line(store, tmp_path, capsys):
    tasks = made_up_tasks()
    logs = {}
    for name, workers in (("serial", 1), ("pool", 2)):
        logs[name] = tmp_path / f"{name}.jsonl"
        done = grid.run_grid(tasks, store.root, tmp_path / name, logs[name], workers=workers, purpose="made up",
                             commit="0" * 40, gate=eh.made_up_gate, day="2026-11-17")
        assert sorted(item["label"] for item in done) == sorted(task.label for task in tasks)
    serial, pool = (grid.read_trials(logs[name]) for name in ("serial", "pool"))
    by_label = {name: {line["label"]: line for line in lines} for name, lines in (("serial", serial), ("pool", pool))}
    for label in by_label["serial"]:
        a, b = by_label["serial"][label], by_label["pool"][label]
        assert a == b                                      # same run_id, hashes and params, whatever ran it
        assert ledger_hashes(tmp_path / "serial" / f"run_id={a['run_id']}") == \
            ledger_hashes(tmp_path / "pool" / f"run_id={b['run_id']}")
    # completeness: every line names a run folder, and every run folder has a line
    for name, lines in (("serial", serial), ("pool", pool)):
        folders = {path.name.removeprefix("run_id=") for path in (tmp_path / name).glob("run_id=*")}
        assert {line["run_id"] for line in lines} == folders and len(lines) == len(tasks)
    line = serial[0]
    assert tuple(line) == grid.LINE_KEYS and line["purpose"] == "made up" and line["date"] == "2026-11-17"
    assert line["params"] == by_label["serial"][line["label"]]["params"] and "signal" in line["params"]
    out = capsys.readouterr().out
    assert "peak RSS" in out and "pnl" not in out.lower() and "nav" not in out.lower()


def test_the_trials_are_the_distinct_config_code_and_data_triples(tmp_path):
    def line(config, code="c1", data="d1", **changes):
        base = dict.fromkeys(grid.LINE_KEYS, "x")
        return {**base, "trial_group": "m4_vol", "split": "development", "config_hash": config, "code_fingerprint": code,
                "data_fingerprint": data, **changes}

    one = [line("a")]
    assert len(grid.trials(one + [line("a")])) == 1                                 # a re-run, everything equal
    # each alone adds one trial: another window or execution mode (another config_hash), code, or store
    for name, other in (("config_hash", line("b")), ("code_fingerprint", line("a", code="c2")),
                        ("data_fingerprint", line("a", data="d2"))):
        assert len(grid.trials(one + [other])) == 2, name
    lines = [line("a"), line("a"), line("b"), line("a", code="c2"), line("a", data="d2"),
             line("z", trial_group="m4_smoke"), line("y", split="validation")]
    assert grid.trials(lines) == {("a", "c1", "d1"), ("b", "c1", "d1"), ("a", "c2", "d1"), ("a", "c1", "d2")}
    assert grid.n_raw(lines) == 4 + 10
    assert grid.in_sample_label(lines) == "in-sample, 4 trials of N_raw 14, selection-biased, no claim"
    # a line with a key the log does not hold (a metric) is refused, in reading and in writing
    path = tmp_path / "log.jsonl"
    path.write_text(json.dumps({**line("a"), "pnl": 1.0}) + "\n")
    with pytest.raises(ValueError, match="holds exactly"):
        grid.read_trials(path)
    with pytest.raises(ValueError, match="holds exactly"):
        grid.append_trial(tmp_path / "other.jsonl", {**line("a"), "pnl": 1.0})
    assert not (tmp_path / "other.jsonl").exists()


def test_the_made_up_runs_log_one_trial_each_and_a_run_in_another_window_or_mode_is_another(store, tmp_path):
    """On real run folders: the same task again is the same trial; the same strategy in another window, or in another
    execution mode, is another (their trial_hash is the same: the key that undercounted)."""
    task = made_up_tasks()[1]
    log = tmp_path / "log.jsonl"
    variants = {"same": task.cfg, "window": replace(task.cfg, sample_end=date(2023, 3, 3)),
                "mode": replace(task.cfg, execution_mode="surface")}
    for name, cfg in variants.items():
        grid.run_grid([grid.Task(task.label, cfg, task.strategy)], store.root, tmp_path / "runs", log,
                      purpose=name, commit="0" * 40, gate=eh.made_up_gate, day="2026-11-17")
    grid.run_grid([task], store.root, tmp_path / "runs", log, purpose="again", commit="0" * 40, gate=eh.made_up_gate,
                  day="2026-11-17")
    lines = grid.read_trials(log)
    assert len(lines) == 4 and len({line["trial_hash"] for line in lines}) == 1
    assert len(grid.trials(lines, splits=("validation", "development"))) == 3


# --- a crash mid-grid and the lock --------------------------------------------------------------------------------------

def crash_tasks(n_after: int = 8) -> list[grid.Task]:
    """A good run, one that fails (a window with no sessions: run_backtest raises), then n_after good runs."""
    cfg = eh.config(trial_group="m4_vol", hedge_mode="time", hedge_every_n=1, hedge_timing="same_close")
    good = [grid.Task(f"ok{n}", cfg, VolStrategy("short_straddle", "short", EntryRule(), ExitRules(14 + n)))
            for n in range(n_after + 1)]
    boom = grid.Task("boom", replace(cfg, sample_start=date(1990, 1, 2), sample_end=date(1990, 2, 1)),
                     VolStrategy("short_straddle", "short", EntryRule(), ExitRules(14)))
    return [good[0], boom, *good[1:]]


def test_a_failing_task_leaves_a_log_line_for_each_completed_run_and_none_for_the_failed(store, tmp_path):
    log, runs = tmp_path / "log.jsonl", tmp_path / "runs"
    with pytest.raises(Exception):
        grid.run_grid(crash_tasks(), store.root, runs, log, workers=2, purpose="made up", commit="0" * 40,
                      gate=eh.made_up_gate, day="2026-11-17")
    lines = grid.read_trials(log)
    folders = {path.name.removeprefix("run_id=") for path in runs.glob("run_id=*")}
    assert {line["run_id"] for line in lines} == folders              # no run folder without a line, no line without one
    assert "ok0" in {line["label"] for line in lines} and "boom" not in {line["label"] for line in lines}
    assert len(lines) < 9                                             # the runs still pending were cancelled
    assert not (runs / grid.LOCK).exists() and not (tmp_path / "log.jsonl.lock").exists()


def test_the_worker_s_own_error_is_reraised(store, tmp_path):
    with pytest.raises(EngineError, match="no SPY session in"):
        grid.run_grid(crash_tasks(1), store.root, tmp_path / "runs", tmp_path / "log.jsonl", workers=2,
                      purpose="made up", commit="0" * 40, gate=eh.made_up_gate, day="2026-11-17")


def test_main_prints_which_labels_finished_and_how_to_run_the_rest(monkeypatch, tmp_path, capsys):
    tasks = grid.grid_tasks("har")
    done_label = tasks[0].label

    def crash(tasks, store_root, runs_root, trial_log, workers, purpose):
        grid.append_trial(trial_log, dict.fromkeys(grid.LINE_KEYS, "x") | {"label": done_label})
        raise RuntimeError("worker died")

    monkeypatch.setattr(grid, "decided_rv_model", lambda *a, **k: "har")
    monkeypatch.setattr(grid, "run_grid", crash)
    log = tmp_path / "log.jsonl"
    grid.append_trial(log, dict.fromkeys(grid.LINE_KEYS, "x") | {"label": "from an earlier run"})
    assert grid.main(["--store", str(tmp_path), "--runs-root", str(tmp_path / "runs"), "--trial-log", str(log)]) == 1
    err = capsys.readouterr().err
    assert "failed: RuntimeError: worker died" in err and "Traceback" not in err
    assert f"finished and logged (1): {done_label}" in err and "from an earlier run" not in err
    assert "not run or failed (35)" in err and err.count("--only '") == 35 and f"--only '{done_label}'" not in err
    assert f"--runs-root {tmp_path / 'runs'} --trial-log {log} --only '{tasks[1].label}'" in err


def test_a_second_invocation_refuses_while_the_lock_is_held_and_runs_nothing(store, tmp_path):
    runs, log = tmp_path / "runs", tmp_path / "log.jsonl"
    with grid.grid_lock(runs, log):
        with pytest.raises(grid.LockError, match="another run_m4_grid invocation"):
            grid.run_grid(made_up_tasks()[:1], store.root, runs, log, purpose="made up", commit="0" * 40,
                          gate=eh.made_up_gate, day="2026-11-17")
        assert not list(runs.glob("run_id=*")) and not log.exists()
    done = grid.run_grid(made_up_tasks()[:1], store.root, runs, log, purpose="made up", commit="0" * 40,
                         gate=eh.made_up_gate, day="2026-11-17")                # released on exit: it runs now
    assert len(done) == 1 and not (runs / grid.LOCK).exists() and not (tmp_path / "log.jsonl.lock").exists()


@pytest.mark.parametrize("held", ["runs", "log"])
def test_either_lock_alone_refuses_and_leaves_no_other_lock_behind(held, store, tmp_path):
    runs, log = tmp_path / "runs", tmp_path / "log.jsonl"
    runs.mkdir()
    lock = runs / grid.LOCK if held == "runs" else tmp_path / "log.jsonl.lock"
    other = tmp_path / "log.jsonl.lock" if held == "runs" else runs / grid.LOCK
    lock.write_text("someone else\n")
    with pytest.raises(grid.LockError):
        grid.run_grid(made_up_tasks()[:1], store.root, runs, log, purpose="made up", commit="0" * 40,
                      gate=eh.made_up_gate, day="2026-11-17")
    assert lock.read_text() == "someone else\n" and not other.exists()


def test_main_refuses_with_one_line_when_the_lock_is_held(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(grid, "decided_rv_model", lambda *a, **k: "har")
    runs, log = tmp_path / "runs", tmp_path / "log.jsonl"
    with grid.grid_lock(runs, log):
        assert grid.main(["--store", str(tmp_path), "--runs-root", str(runs), "--trial-log", str(log)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("refused: ") and "Traceback" not in err and err.count("\n") == 1
