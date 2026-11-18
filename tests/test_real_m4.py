"""Milestone 4's trial log against the runs of record (marked real_data): docs/validation/trials/m4.jsonl and the
run folders under work_dir()/runs (plan section 10, task 12; the counting rule is docs/validation/trials/README.md).

  - every line names a run folder whose ledger checks and whose runs table the line copies;
  - every development run of trial group m4_vol in work_dir()/runs has a line;
  - the grid ran on the RV model the forecast test chose: the last line of each label is that grid entry (its
    trial_hash), the labels are the 36 of m4_grid(<model>), and the trials and N_raw are what the log holds.
Nothing here reads a P&L, a NAV, a return or an exit; the runs are read for their runs table only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from volbt import config
from volbt.engine import report
from volbt.engine.run_config import trial_hash
from volbt.strategies.grid import TRIAL_GROUP, m4_grid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import run_m4_grid as grid  # noqa: E402

pytestmark = pytest.mark.real_data


@pytest.fixture(scope="module")
def lines():
    if not grid.TRIAL_LOG.is_file():
        pytest.skip("no trial log: run uv run python tools/run_m4_grid.py --workers 4")
    return grid.read_trials()


def runs_root() -> Path:
    return config.work_dir() / "runs"


def test_every_line_names_a_run_folder_whose_runs_table_it_copies(lines):
    assert lines
    for line in lines:
        folder = runs_root() / f"run_id={line['run_id']}"
        assert folder.is_dir(), f"{line['label']}: no {folder}"
        report.check_ledger(folder)          # the files' hashes and the run_id's derivation
        row = report.table(folder, "runs")[0]
        for key in ("trial_group", "split", "config_hash", "code_fingerprint", "data_fingerprint", "source_commit"):
            assert row[key] == line[key], (line["label"], key)
        assert (row["sample_start"].isoformat(), row["sample_end"].isoformat()) == (
            line["sample_start"], line["sample_end"])
        assert json.loads(row["config_json"])["strategy"]["params"] == line["params"]


def test_every_development_run_of_the_group_in_the_runs_folder_has_a_line(lines):
    logged = {line["run_id"] for line in lines}
    found = set()
    for folder in sorted(runs_root().glob("run_id=*")):
        row = report.table(folder, "runs")[0]
        if row["trial_group"] == TRIAL_GROUP and row["split"] == "development":
            found.add(folder.name.removeprefix("run_id="))
    assert found, f"no development run of {TRIAL_GROUP} under {runs_root()}"
    assert sorted(found - logged) == []


def test_the_grid_ran_on_the_decided_model_and_the_log_counts_its_trials(lines):
    rv_model = grid.decided_rv_model()
    latest = grid.latest_by_label(lines)
    expected = {task.label: trial_hash(task.cfg, task.strategy) for task in grid.grid_tasks(rv_model)}
    assert len(expected) == 36 and set(expected) == {entry.label for entry in m4_grid(rv_model)}
    assert {label: line["trial_hash"] for label, line in latest.items()} == expected
    assert all(line["split"] == "development" and line["sample_end"] <= "2019-12-31" for line in lines)
    triples = {(line["config_hash"], line["code_fingerprint"], line["data_fingerprint"]) for line in lines}
    assert grid.trials(lines) == triples and grid.n_raw(lines) == len(triples) + grid.DESIGN_CHOICES
    assert len(triples) == len(expected)          # the measurement run repeats its label's config, code and data
