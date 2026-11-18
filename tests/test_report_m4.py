"""tools/report_m4.py (milestone 4, part B2a): development diagnostics per run, no P&L.

Two runs on the made-up signal store, made and logged by tools/run_m4_grid.py's run_grid into a temporary trial log.
Their sessions are in 2023, so the positive path widens the guard (splits, last_date), as tests/test_export_m4.py
does; with the defaults the report refuses them. Made-up values only.
"""

from __future__ import annotations

from collections import Counter

import pytest

import engine_helpers as eh
import engine_store as es
import signal_store as ss
import test_run_m4_grid as made
from volbt.signals.base import RV_FALLBACK

import report_m4  # noqa: E402  (tools/ is on sys.path through test_run_m4_grid's m4_repo)
import run_m4_grid as grid  # noqa: E402

WIDE = dict(splits=("validation",), last_date=es.LAST_BAR)
# M3's health whitelist (tests/test_smoke_m4.py) and the blocks report_m4 adds
WHITELIST = ("== health:", "run_id ", "timings ", "cash = initial", "marks per open lot", "mark sources",
             "mark flags", "DEGRADED days", "orders: ", "option fills", "hedge rows", "event ",
             "P&L, NAV levels and returns: not printed", "## m4: ", "in-sample, ", "positions ", "exit reasons: ",
             "s defined on ")


@pytest.fixture(scope="module")
def logged(tmp_path_factory):
    store = ss.signal_store(tmp_path_factory.mktemp("report_store"))
    root = tmp_path_factory.mktemp("report_runs")
    log = root / "log.jsonl"
    grid.run_grid(made.made_up_tasks(), store.root, root / "runs", log, purpose="made up", commit="0" * 40,
                  gate=eh.made_up_gate, day="2026-11-17")
    return grid.read_trials(log), root / "runs"


def test_the_report_prints_the_whitelist_the_counts_and_the_label_and_no_result(logged, capsys):
    lines, runs_root = logged
    assert report_m4.report(lines, runs_root, **WIDE) == 2
    out = capsys.readouterr().out
    printed = [line for line in out.splitlines() if line.strip()]
    assert printed and all(line.startswith(WHITELIST) for line in printed), \
        [line for line in printed if not line.startswith(WHITELIST)]
    assert sum(line.startswith("== health:") for line in printed) == sum(line.startswith("## m4: ") for line in printed)
    # the made-up runs are validation diagnostics: no development trial, so N_raw is the design-choice log's 10
    assert printed.count("in-sample, 0 trials of N_raw 10, selection-biased, no claim") == 2
    for line in lines:
        run_dir = runs_root / f"run_id={line['run_id']}"
        positions, signals = eh.table(run_dir, "positions"), eh.table(run_dir, "signals")
        closed = positions[positions.closed_date.notna()]
        reasons = ", ".join(f"{k} {v}" for k, v in sorted(Counter(closed.exit_reason).items())) or "none"
        assert f"exit reasons: {reasons}" in printed
        assert (f"positions {len(positions)}; entries (opened) {int(positions.opened_date.notna().sum())}; closed "
                f"{len(closed)}; still open {int((positions.status == 'open').sum())}") in printed
        defined, fallback = int(signals.log_var_ratio.notna().sum()), int(((signals["flags"] & RV_FALLBACK) > 0).sum())
        assert any(p.startswith(f"s defined on {defined} of {len(signals)} sessions") and
                   p.endswith(f"HAR fallback (RV_FALLBACK) on {fallback} sessions") for p in printed)
    shown = "\n".join(line for line in printed if "not printed" not in line).lower()
    assert "pnl" not in shown and "p&l" not in shown and "sharpe" not in shown and "return" not in shown


def test_a_run_off_the_development_split_or_past_2019_is_refused(logged, capsys):
    lines, runs_root = logged
    with pytest.raises(ValueError, match="decision D19"):
        report_m4.report(lines, runs_root)
    with pytest.raises(ValueError, match="decision D19"):
        report_m4.report(lines, runs_root, splits=("validation",))
    capsys.readouterr()
