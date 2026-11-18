"""Print milestone 4's development diagnostics, one block per run of the trial log (plan section 10, task 12).

Run:  uv run python tools/report_m4.py [--trial-log PATH] [--runs-root DIR]

For each run the log names (the last line of each label, in the log's order), from its ledger:
  - the in-sample label: "in-sample, <trials> trials of N_raw <n>, selection-biased, no claim" (run_m4_grid.trials
    and n_raw: the distinct (trial_hash, code_fingerprint) of the log plus the design-choice log);
  - M3's health whitelist (tools/report_m3.health);
  - the positions: how many, how many opened (entries), closed and still open, and the count of each exit reason;
  - the sessions with s defined (the signals table's log_var_ratio is a number) and the HAR fallback count (the
    RV_FALLBACK bit of its flags).
Decision D19, extended to every date before M6 (default taken 2026-11-17, owner can override): no P&L, NAV, return or
Sharpe is printed, for any run. A run that is not on the development split, or whose sample ends after 2019-12-31, is
refused (ValueError): its exit counts would depend on P&L after 2019.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import report_m3
import run_m4_grid
from volbt import config
from volbt.signals.base import RV_FALLBACK

LAST_DEVELOPMENT_DAY = date(2019, 12, 31)


def checked_run(run_dir: Path, splits: tuple[str, ...], last_date: date):
    run = report_m3.table(run_dir, "runs").iloc[0]
    if run.split not in splits or run.sample_end > last_date:
        raise ValueError(f"{run_dir}: report_m4 reads development runs ending by {last_date} only, not a {run.split} "
                         f"run to {run.sample_end} (decision D19)")
    return run


def positions_block(run_dir: Path) -> None:
    positions = report_m3.table(run_dir, "positions")
    opened = positions[positions.opened_date.notna()]
    closed = positions[positions.closed_date.notna()]
    print(f"positions {len(positions)}; entries (opened) {len(opened)}; closed {len(closed)}; still open "
          f"{int((positions.status == 'open').sum())}")
    reasons = Counter(reason for reason in closed.exit_reason if reason is not None)
    print("exit reasons: " + (", ".join(f"{k} {v}" for k, v in sorted(reasons.items())) or "none"))


def signal_block(run_dir: Path) -> None:
    signals = report_m3.table(run_dir, "signals")
    defined = int(signals.log_var_ratio.notna().sum())
    fallback = int(((signals["flags"] & RV_FALLBACK) > 0).sum())
    print(f"s defined on {defined} of {len(signals)} sessions ({defined / len(signals):.4f}); HAR fallback "
          f"(RV_FALLBACK) on {fallback} sessions")


def report(lines: list[dict], runs_root: Path, splits: tuple[str, ...] = ("development",),
           last_date: date = LAST_DEVELOPMENT_DAY) -> int:
    """Print the blocks of the module docstring; returns the number of runs reported."""
    label = run_m4_grid.in_sample_label(lines)
    latest = run_m4_grid.latest_by_label(lines)
    for name, line in latest.items():
        run_dir = Path(runs_root) / f"run_id={line['run_id']}"
        checked_run(run_dir, splits, last_date)
        print(f"\n## m4: {name}")
        print(label)
        report_m3.health(run_dir)
        positions_block(run_dir)
        signal_block(run_dir)
    return len(latest)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trial-log", type=Path, default=run_m4_grid.TRIAL_LOG)
    parser.add_argument("--runs-root", type=Path, default=None)
    args = parser.parse_args(argv)
    lines = run_m4_grid.read_trials(args.trial_log)
    count = report(lines, args.runs_root or config.work_dir() / "runs")
    print(f"\n{count} run(s) reported; P&L, NAV, returns and Sharpe: not printed (decision D19, before M6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
