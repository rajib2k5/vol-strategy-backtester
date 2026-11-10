"""Run one backtest of the milestone-3 reference strategy and write its ledger.

Run:  uv run python tools/run_backtest.py --start 2010-01-04 --end 2019-12-31 --split development [--for-app]

The ledger goes to work_dir()/runs/run_id=<id>/ (git-ignored), one parquet file per table, and
run_meta.json beside it with the stage timings (timed inside run_backtest) and the files' SHA-256.

Provenance (milestone 3). The engine may not import volbt.build or volbt.contract (ADR-0001 §4), so this
tool passes them in: build.require_current runs before and after the run (the pricing tables must come from
the current code over the current inputs, ADR-0001 amendment 2), and contract.source_commit names the code.
The run_id is SHA-256(config_hash, data_fingerprint, commit, code_fingerprint), the last part a hash of every
.py file under src/volbt/ and the library versions (decision B17): the same inputs, config, commit and code give the
same folder and the same bytes.

The split protocol (decision D19). A run whose sample ends after 2019-12-31 reports health metrics only:
this tool never prints a P&L, a NAV or a return for any run, and tools/report_m3.py prints them for no run
past the development split. --for-app records the run as the one tools/export_app_data.py exports
(work_dir()/runs/app_run.json); only a development-split run may be recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from volbt import build, config
from volbt.contract import source_commit
from volbt.data.store import Store
from volbt.engine.loop import run_backtest
from volbt.engine.run_config import RunConfig
from volbt.strategies.reference import RollingShortStraddle

APP_RUN_FILE = "app_run.json"


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--split", choices=("development", "validation", "holdout"), required=True)
    parser.add_argument("--source", choices=("optionsdx", "dolthub"), default="optionsdx")
    parser.add_argument("--mode", choices=("quote", "surface"), default="quote")
    parser.add_argument("--fill-timing", choices=("next_close", "same_close"), default="next_close")
    parser.add_argument("--cap-mode", choices=("hard_only", "volume"), default="hard_only")
    parser.add_argument("--hedge-mode", choices=("time", "band", "never"), default="time")
    parser.add_argument("--exit-dte", type=int, default=7)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument("--for-app", action="store_true", help="record this run for tools/export_app_data.py")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    if args.for_app and args.split != "development":
        print("error: only a development-split run may feed the app (decision D19)", file=sys.stderr)
        return 2
    cfg = RunConfig(sample_start=args.start, sample_end=args.end, split=args.split, data_source=args.source,
                    execution_mode=args.mode, fill_timing=args.fill_timing, cap_mode=args.cap_mode,
                    hedge_mode=args.hedge_mode, seed=args.seed)
    store = Store(args.store)
    runs_root = args.runs_root or config.work_dir() / "runs"
    result = run_backtest(cfg, RollingShortStraddle(exit_dte=args.exit_dte), store=store, runs_root=runs_root,
                          source_commit=source_commit(), store_check=build.require_current)
    meta_path = result.run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta_path.write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"run_id {result.run_id}")
    print(f"status {result.status}, sessions {result.sessions}, last {result.last_session}")
    print(f"timings {json.dumps(result.timings, sort_keys=True)}")
    print(f"ledger {result.run_dir}")
    print("P&L: not printed by this tool (decision D19; tools/report_m3.py reports health metrics)")
    if args.for_app:
        (runs_root / APP_RUN_FILE).write_text(json.dumps({"run_dir": str(result.run_dir)}, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")
        print(f"recorded for the app: {runs_root / APP_RUN_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
