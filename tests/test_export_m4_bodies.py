"""tools/export_app_data.py m4_bodies and main()'s milestone-4 path (part B2a, task 13): the two M4 files from the
grid's logged runs, with the RV model the committed forecast test chose.

Four of the grid's own strategies (m4_grid("har"): the labels the exporter shows) run on the made-up signal store by
tools/run_m4_grid.py's run_grid into a temporary trial log, and a throwaway git repository holds a made-up scored
pre-registration (tests/m4_repo.py) that both decided_rv_model and checked_forecast_test accept. The store's sessions
are in 2023, so the positive path widens the guard (splits, last_date), as tests/test_export_m4.py does. Made-up
values only; the project's ledgers and trial log are never written.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

import engine_helpers as eh
import engine_store as es
import m4_repo
import signal_store as ss
import test_export_m4 as m4
from volbt.strategies.grid import m4_grid

import export_app_data as ex  # noqa: E402  (tools/ is on sys.path through m4_repo)
import run_m4_grid as grid  # noqa: E402

WIDE = dict(splits=("validation",), last_date=es.LAST_BAR)
CHECKED = {key: value for key, value in m4.RESULT.items() if key not in ("prereg_id", "prereg_sha256")}
SPEC = {"test": {"q": m4.RESULT["q"], "block": m4.RESULT["block"], "draws": m4.RESULT["draws"], "seed": 1},
        "size": {"worst": {"high": {"rate": m4.RESULT["worst_simulated_size"]}}},
        "effective_size": m4.RESULT["effective_size"], "fragile_band": m4.RESULT["fragile_band"]}


def repo_for(root, p=0.01, decision="har", **changes):
    """A throwaway repository whose committed made-up result passes decided_rv_model and checked_forecast_test."""
    return m4_repo.scored_repo(root, p=p, decision=decision, result_changes={**CHECKED, "p": p, "p_holm": p,
                                                                            "decision": decision, **changes},
                               spec_changes=SPEC)


def pin(repo) -> dict:
    """The made-up result's pin: its file's SHA-256 as committed (decided_rv_model refuses an id that is not pinned)."""
    return {m4_repo.ID: m4_repo.sha256(repo / "docs" / "validation" / "prereg" / f"{m4_repo.ID}.result.json")}


def tasks() -> list[grid.Task]:
    """The grid's own strategies for the exporter's labels, on the made-up store's sessions (a diagnostic config:
    a 2023 trial would need a pre-registration)."""
    wanted = set(ex.STRATEGY_LABELS.values()) | {ex.SIGNAL_LABEL}
    cfg = eh.config(trial_group="m4_vol", hedge_mode="time", hedge_every_n=1, hedge_timing="same_close")
    return [grid.Task(entry.label, cfg, entry.strategy) for entry in m4_grid("har") if entry.label in wanted]


@pytest.fixture(scope="module")
def logged(tmp_path_factory):
    store = ss.signal_store(tmp_path_factory.mktemp("bodies_store"))
    root = tmp_path_factory.mktemp("bodies_runs")
    log = root / "log.jsonl"
    grid.run_grid(tasks(), store.root, root / "runs", log, purpose="made up", commit="0" * 40, gate=eh.made_up_gate,
                  day="2026-11-17")
    return store, log, root / "runs"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    return repo_for(tmp_path_factory.mktemp("bodies_repo"))


def test_the_bodies_are_the_logged_grid_runs_with_the_decided_model_and_the_checked_result(logged, repo):
    store, log, runs_root = logged
    signals, strategy = ex.m4_bodies(store, log, runs_root, repo, prereg_id=m4_repo.ID, pins=pin(repo), **WIDE)
    latest = grid.latest_by_label(grid.read_trials(log))
    folder = {label: runs_root / f"run_id={line['run_id']}" for label, line in latest.items()}
    prereg_dir = repo / "docs" / "validation" / "prereg"
    result = json.loads((prereg_dir / f"{m4_repo.ID}.result.json").read_text())
    assert signals == ex.signals_timeline_body(folder[ex.SIGNAL_LABEL], store, "vrp_har", forecast_test=result,
                                               prereg_dir=prereg_dir, **WIDE)
    assert signals["signal"]["rv_model"] == signals["forecast_test"]["decision"] == "har"
    assert signals["forecast_test"]["prereg_sha256"] == m4_repo.sha256(prereg_dir / f"{m4_repo.ID}.sha256")
    assert strategy == ex.strategy_positions_body(
        [(folder[ex.STRATEGY_LABELS[s]], 4) for s in ex.STRATEGY_STRUCTURES],
        "4 development trials; no performance shown before M6", **WIDE)
    assert [run["run"]["run_id"] for run in strategy["runs"]] == [
        latest[ex.STRATEGY_LABELS[s]]["run_id"] for s in ex.STRATEGY_STRUCTURES]
    assert [run["strategy"] for run in strategy["runs"]] == ["VolStrategy"] * 4
    assert [run["params"]["structure"] for run in strategy["runs"]] == list(ex.STRATEGY_STRUCTURES)


def test_a_naive_decision_asks_for_the_naive_signal_which_the_har_runs_lack(logged, tmp_path):
    store, log, runs_root = logged
    naive = repo_for(tmp_path, p=0.5, decision="naive", fragile=False)
    with pytest.raises(ValueError, match="name one of the run's signals .*'vrp_naive'"):
        ex.m4_bodies(store, log, runs_root, naive, prereg_id=m4_repo.ID, pins=pin(naive), **WIDE)


def test_a_result_edited_after_its_commit_stops_the_export(logged, tmp_path):
    store, log, runs_root = logged
    edited = repo_for(tmp_path)
    path = edited / "docs" / "validation" / "prereg" / f"{m4_repo.ID}.result.json"
    path.write_text(path.read_text().replace('"p": 0.01', '"p": 0.011'))
    with pytest.raises(grid.DecisionError):
        ex.m4_bodies(store, log, runs_root, edited, prereg_id=m4_repo.ID, pins=pin(edited), **WIDE)


def test_a_missing_label_a_missing_folder_and_a_line_naming_another_run_are_refused(logged, repo, tmp_path):
    store, log, runs_root = logged
    lines = grid.read_trials(log)
    short = tmp_path / "short.jsonl"
    short.write_text("".join(json.dumps(line) + "\n" for line in lines
                             if line["label"] != ex.STRATEGY_LABELS["long_straddle"]))
    with pytest.raises(FileNotFoundError, match="has no line for long_straddle/below_0.0/dte\\+signal\\+pt_sl"):
        ex.m4_bodies(store, short, runs_root, repo, prereg_id=m4_repo.ID, pins=pin(repo), **WIDE)
    with pytest.raises(FileNotFoundError, match="is not there"):
        ex.m4_bodies(store, log, tmp_path / "elsewhere", repo, prereg_id=m4_repo.ID, pins=pin(repo), **WIDE)
    other = tmp_path / "other.jsonl"
    other.write_text("".join(json.dumps({**line, "config_hash": "0" * 64} if line["label"] == ex.SIGNAL_LABEL
                                        else line) + "\n" for line in lines))
    with pytest.raises(ValueError, match="config_hash"):
        ex.m4_bodies(store, other, runs_root, repo, prereg_id=m4_repo.ID, pins=pin(repo), **WIDE)


def test_the_default_guard_refuses_runs_off_the_development_split(logged, repo):
    store, log, runs_root = logged
    with pytest.raises(ValueError, match="decision D19"):
        ex.m4_bodies(store, log, runs_root, repo, prereg_id=m4_repo.ID, pins=pin(repo))


def test_main_hands_the_m4_bodies_to_the_writer_and_stops_on_a_refusal(monkeypatch, tmp_path, capsys):
    seen = {}
    monkeypatch.setattr(ex, "data_quality_body", lambda store: {})
    monkeypatch.setattr(ex, "surface_frames_body", lambda store, frames: {})
    monkeypatch.setattr(ex, "engine_bodies", lambda run_dir, splits: ({}, {}))
    monkeypatch.setattr(ex, "build_payloads", lambda *args, **kwargs: seen.update(kwargs) or {})
    calls = []
    monkeypatch.setattr(ex, "m4_bodies", lambda store, trial_log, runs_root: calls.append((trial_log, runs_root))
                        or ({"made": "signals"}, {"made": "strategy"}))
    args = ["--store", str(tmp_path), "--out-dir", str(tmp_path / "out"), "--run-dir", str(tmp_path)]
    assert ex.main(args + ["--trial-log", str(tmp_path / "log.jsonl"), "--runs-root", str(tmp_path / "runs")]) == 0
    assert calls == [(tmp_path / "log.jsonl", tmp_path / "runs")]
    assert seen["signals_body"] == {"made": "signals"} and seen["strategy_body"] == {"made": "strategy"}
    seen.clear()
    assert ex.main(args + ["--without-m4"]) == 0
    assert len(calls) == 1 and seen["signals_body"] is None and seen["strategy_body"] is None

    def refused(store, trial_log, runs_root):
        raise grid.DecisionError("made-up refusal")
    monkeypatch.setattr(ex, "m4_bodies", refused)
    seen.clear()
    assert ex.main(args) == 1
    assert "made-up refusal" in capsys.readouterr().err and not seen


def test_main_stops_with_one_line_on_a_prereg_error_such_as_a_symlinked_result(monkeypatch, tmp_path, capsys):
    """decided_rv_model's prereg.committed raises PreregError for a symlinked file: main() exits 1, no traceback."""
    monkeypatch.setattr(ex, "data_quality_body", lambda store: {})
    monkeypatch.setattr(ex, "surface_frames_body", lambda store, frames: {})
    monkeypatch.setattr(ex, "engine_bodies", lambda run_dir, splits: ({}, {}))
    written = []
    monkeypatch.setattr(ex, "build_payloads", lambda *args, **kwargs: written.append(kwargs) or {})

    def symlinked(store, trial_log, runs_root):
        raise m4_repo.prereg.PreregError("made-up: the result file is a symlink")
    monkeypatch.setattr(ex, "m4_bodies", symlinked)
    args = ["--store", str(tmp_path), "--out-dir", str(tmp_path / "out"), "--run-dir", str(tmp_path)]
    assert ex.main(args) == 1
    err = capsys.readouterr().err
    assert err == "error: made-up: the result file is a symlink\n" and not written
