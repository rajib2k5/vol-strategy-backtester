"""Milestone 4's smoke (plan section 6): the four structures on the validation split, health only, ledgers deleted.

Run:  uv run python tools/smoke_m4.py                  the 8 smoke runs
      uv run python tools/smoke_m4.py --budget STRUCTURE   the 60-second budget run (OptionsDX, 2010-01-04 to 2023-12-29)

The smoke runs each structure (strategies.vol.VolStrategy) with the `always` entry and the DTE exit only, so its path
does not depend on a P&L, on the validation split (2020-01-02 to 2023-12-29) in OptionsDX quote mode and in DoltHub
surface mode, as diagnostics (run_purpose "diagnostic", trial_group "m4_smoke"): 8 runs, the RV model "har" (where
HAR has no forecast it falls back to the naive one, so the s-defined share is the same for both). For each run it
prints M3's health whitelist (tools/report_m3.health) and the share of sessions with s defined, and NOTHING else:
no P&L, NAV, return, Sharpe, exit-reason count or signal value after 2019 (decision D19, ADR-0010). Then it deletes
the run's ledger. No holdout run.

The budget run is one structure, `always` + DTE, OptionsDX quote mode, 2010-01-04 to 2023-12-29 (labelled the
validation split, as M3's budget run), timed inside run_backtest (timings.total_s) with the load average before and
after; it prints the run id, the sessions, the timings and the load, and deletes the ledger.

Both pass tools/prereg.py's run gate (as tools/run_backtest.py; tested): a run past 2019 is recorded in
docs/validation/prereg/runs_of_record.jsonl with its purpose and its diagnostic_kind, "smoke" or "budget" (a "started"
line when the gate passes it, a "completed" line after its folder is in place), which is intended; the tool prints
the lines it added. The gate counts a health run (smoke, budget) per trial_hash, kind, data source and execution
mode, the run and two re-runs, and apart from the ADR-0009/ADR-0010 diagnostics of the same trial_hash (fix pass 5,
item G1; review F claim 5). Running one of them again needs --rerun-reason (fix pass 3, item D6): a smoke that crashed
part way is run again whole with --rerun-reason (each run already done is then a re-run, each run not yet done a first
run). A structure's smoke and budget runs share the trial_hash of the grid's "<structure>/always/dte" entry, and leave
its ADR-0009 §4 run S and its volume cap their own limits. The gate accepts a health run only on the pairs this tool
uses: MODES for the smoke, BUDGET_MODE for the budget run (prereg.HEALTH_PAIRS; fix pass 6, item H4, tested). Its
spent check reads only a run's dates after 2019-12-31, so a scored forecast window (2010-2019) does not refuse the
budget run or its re-runs (fix pass 6, item H5).

When run_backtest raises (the gate's recorder after the rename, the store check after the write, an interrupt), every
run_id=* folder it created under the runs root, final or .tmp, is removed before the error goes on: no ledger with
rows after 2019 is left behind (fix pass 2, review C claim 8).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

import prereg
import report_m3
from volbt import build, config
from volbt.contract import source_commit
from volbt.data.store import Store
from volbt.engine.loop import run_backtest
from volbt.engine.run_config import RunConfig
from volbt.strategies.rules import EXIT_DTE, EntryRule, ExitRules
from volbt.strategies.sizing import FixedPackages
from volbt.strategies.structures import SIDES, STRUCTURES
from volbt.strategies.vol import VolStrategy

VALIDATION = (date(2020, 1, 2), date(2023, 12, 29))
BUDGET = (date(2010, 1, 4), date(2023, 12, 29))
MODES = (("optionsdx", "quote"), ("dolthub", "surface"))
BUDGET_MODE = ("optionsdx", "quote")
SMOKE_RUNS = tuple((structure, source, mode) for structure in STRUCTURES for source, mode in MODES)
TRIAL_GROUP = "m4_smoke"
RV_MODEL = "har"


def smoke_strategy(structure: str, source: str) -> VolStrategy:
    """`always` with the DTE exit only: the path depends on no P&L."""
    return VolStrategy(structure, SIDES[structure], EntryRule(), ExitRules(EXIT_DTE), FixedPackages(), RV_MODEL, source)


def smoke_config(source: str, mode: str, start: date, end: date, split: str = "validation",
                 kind: str = "smoke") -> RunConfig:
    """A smoke run's config, or the budget run's with kind "budget" (RunConfig.diagnostic_kind; fix pass 3)."""
    return RunConfig(sample_start=start, sample_end=end, split=split, data_source=source, execution_mode=mode,
                     run_purpose="diagnostic", trial_group=TRIAL_GROUP, fill_timing="next_close", cap_mode="hard_only",
                     hedge_mode="time", hedge_every_n=1, hedge_timing="same_close", diagnostic_kind=kind)


def s_defined(run_dir: Path) -> tuple[int, int]:
    """(sessions with s defined, sessions) from the run's `signals` table: a count, not a value."""
    signals = report_m3.table(run_dir, "signals")
    return int(signals["log_var_ratio"].notna().sum()), len(signals)


def delete(run_dir: Path) -> None:
    shutil.rmtree(run_dir)
    if run_dir.exists():
        raise RuntimeError(f"the ledger {run_dir} is still there")
    print(f"ledger deleted: {run_dir.name}")


def folders(runs_root: Path) -> set[tuple[str, int]]:
    """(name, inode) of every run_id=* folder under runs_root: a folder run_backtest replaced has a new inode."""
    root = Path(runs_root)
    return {(path.name, path.stat().st_ino) for path in root.glob("run_id=*")} if root.is_dir() else set()


def run_or_clean(cfg, strategy, store, runs_root: Path, commit: str, store_check, run_gate):
    """run_backtest; when it raises, the run_id=* folders it created or replaced under runs_root (final and .tmp) are
    removed, then the error goes on (module docstring)."""
    before = folders(runs_root)
    try:
        return run_backtest(cfg, strategy, store=store, runs_root=runs_root, source_commit=commit,
                            store_check=store_check, run_gate=run_gate)
    except BaseException:
        for name, _ in folders(runs_root) - before:
            shutil.rmtree(Path(runs_root) / name, ignore_errors=True)
            if (Path(runs_root) / name).exists():
                print(f"ledger NOT deleted: {name}", file=sys.stderr)
        raise


def smoke(store, runs_root: Path, run_gate, store_check=None, runs=SMOKE_RUNS, window=VALIDATION,
          commit: str = "smoke") -> list[tuple[str, str, str, int, int]]:
    """The smoke runs (module docstring); returns (structure, source, mode, sessions with s, sessions) per run."""
    shares = []
    for structure, source, mode in runs:
        cfg = smoke_config(source, mode, *window)
        result = run_or_clean(cfg, smoke_strategy(structure, source), store, runs_root, commit, store_check, run_gate)
        try:
            print(f"\n## smoke: {structure}, {source} {mode}, always + DTE {EXIT_DTE}")
            report_m3.health(result.run_dir)
            defined, total = s_defined(result.run_dir)
            print(f"s defined on {defined} of {total} sessions ({defined / total:.4f})")
            shares.append((structure, source, mode, defined, total))
        finally:
            delete(result.run_dir)
    return shares


def load() -> str:
    try:
        return Path("/proc/loadavg").read_text(encoding="utf-8").split()[0]
    except OSError:
        return "n/a"


def budget(store, runs_root: Path, run_gate, structure: str, store_check=None, window=BUDGET,
           commit: str = "budget") -> dict:
    cfg = smoke_config(*BUDGET_MODE, *window, kind="budget")
    before = load()
    result = run_or_clean(cfg, smoke_strategy(structure, BUDGET_MODE[0]), store, runs_root, commit, store_check,
                          run_gate)
    after = load()
    try:
        print(f"budget: {structure}, optionsdx quote, always + DTE {EXIT_DTE}, {window[0]} to {window[1]}")
        print(f"run_id {result.run_id}  status {result.status}  sessions {result.sessions}")
        print(f"timings {result.timings}  load average {before} before, {after} after")
    finally:
        delete(result.run_dir)
    return {"timings": result.timings, "load": (before, after), "sessions": result.sessions}


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--budget", choices=STRUCTURES, default=None, help="the 60-second budget run of one structure")
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument("--rerun-reason", default=None,
                        help="why the smoke or the budget run is run again (the gate's record; it refuses a re-run "
                             "without one, and the third re-run)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    store = Store(args.store)
    runs_root = args.runs_root or config.work_dir() / "runs"
    record = prereg.prereg_dir(prereg.REPO) / prereg.RECORDS
    before = record.read_text(encoding="utf-8").splitlines() if record.exists() else []
    gate = prereg.make_run_gate(rerun_reason=args.rerun_reason)
    if args.budget:
        budget(store, runs_root, gate, args.budget, build.require_current, commit=source_commit())
    else:
        smoke(store, runs_root, gate, build.require_current, commit=source_commit())
    after = record.read_text(encoding="utf-8").splitlines() if record.exists() else []
    print(f"\nruns_of_record.jsonl: {len(after) - len(before)} line(s) added")
    for line in after[len(before):]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
