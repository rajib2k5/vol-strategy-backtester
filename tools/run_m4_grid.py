"""Milestone 4's development grid, run once (plan section 10, task 12), and its trial log.

Run:  uv run python tools/run_m4_grid.py [--workers N] [--only LABEL] [--runs-root DIR] [--trial-log PATH]
                                          [--purpose TEXT] [--store DIR]

The RV model (task 8's last step). The grid is m4_grid(rv_model) with the RV model the forecast test chose, read by
decided_rv_model() from the committed result, never typed in: it refuses unless
  - the pre-registration loads (prereg.load: its .json and .md match its .sha256, and all three are committed);
  - the result file, the .sha256 file and spent.jsonl are committed as they are (prereg.committed);
  - the result's prereg_id is the pre-registration's id, and its prereg_sha256 is the SHA-256 of the .sha256 file;
  - spent.jsonl holds exactly one "result" line for the id, whose result_sha256 is the SHA-256 of the result file and
    whose prereg_sha256 is the result's, and no version of spent.jsonl that git or the side ledger holds
    (prereg.ledger_lines) has another result line for the id (a second line would be a second scoring);
  - the result file's SHA-256 is the one PINNED_RESULTS names for the id (an id that is not pinned is refused): the
    record the scoring commit pushed, so files and ledger lines forged together in a fresh repository are refused;
  - the p and the threshold are real numbers (not bool), p finite in (0, 1], the threshold finite in (0, 1);
  - the result's threshold is the pre-registration's, and its decision follows the registered rule ("use HAR if
    p < threshold; otherwise use naive"): "har" or "naive", the names of the candidate and the benchmark.
Default taken 2026-11-17, owner can override (LEARNING_LOG).

The runs. Each GridEntry of m4_grid(rv_model) runs as RunConfig(2010-01-04, 2019-12-31, "development",
**entry.engine) (M3's development run's dates; OptionsDX quote mode, the grid's engine fields), through run_backtest
with the store check (build.require_current), the commit (contract.source_commit) and the pre-registration's run gate
(prereg.make_run_gate: a run that ends by 2019-12-31 passes it and is not recorded). --only runs one label.
--workers runs them in at most MAX_WORKERS (4) processes (spawn); each run is byte-identical whether it runs in a
pool or alone (ADR-0001 test 3; tests/test_run_m4_grid.py checks it on a made-up store).

The trial log (docs/validation/trials/m4.jsonl; the counting rule is in docs/validation/trials/README.md). After each
run completes, one line {LINE_KEYS} is appended: no metric of any kind (no P&L, NAV, return, Sharpe, status or exit
count). Every development run of record is a trial; the trials are the distinct (config_hash, code_fingerprint,
data_fingerprint) triples of the log's development lines (trials()): config_hash holds the window, the execution mode
and the data source (trial_hash drops them, run_config.py), the run's code_fingerprint (volbt.engine.loop.
code_fingerprint: every .py file under src/volbt, the libraries and Python) puts the code back (review C N2) and the
data_fingerprint the store. A re-run with all three equal is the same trial (the same ledger, byte for byte); a
different window, execution mode, code or store is a new one. (The first key, (trial_hash, code_fingerprint),
undercounted: fix pass 1, review claim 3.) n_raw() adds the design-choice log (DESIGN_CHOICES, 10 after M4: ADR-0010's appendix rows 1-6 and plan
section 5's 7-10).

A run that fails (a worker error) cancels the runs not yet started, logs a line for every run that completed, and
re-raises; main() prints which labels finished and the --only commands for the rest. One invocation at a time per
runs root and trial log: run_grid takes a lock file beside each (O_EXCL, released in `finally`, as tools/prereg.py's
ledger lock is) and a second invocation refuses; a crashed one leaves the file, to be deleted by hand once the log and
the runs folder are checked.

Decision D19, extended (default taken 2026-11-17, owner can override): this tool prints the run ids, the timings, the
sessions and each worker's peak RSS; never a P&L, NAV, return, Sharpe, status or exit-reason count, for any date.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed, wait
from dataclasses import dataclass
from datetime import date, datetime, timezone
from multiprocessing import get_context
from pathlib import Path

import pyarrow.parquet as pq

import prereg
from volbt import build, config
from volbt.contract import source_commit
from volbt.data.store import Store
from volbt.engine.loop import run_backtest
from volbt.engine.run_config import RunConfig, trial_hash
from volbt.strategies.grid import TRIAL_GROUP, m4_grid

REPO = Path(__file__).resolve().parents[1]
TRIAL_LOG = REPO / "docs" / "validation" / "trials" / "m4.jsonl"
DEVELOPMENT = (date(2010, 1, 4), date(2019, 12, 31))       # M3's development run (tools/run_backtest.py)
SPLIT = "development"
MAX_WORKERS = 4
DESIGN_CHOICES = 10          # ADR-0010's design-choice log after M4: rows 1-6 and plan section 5's rows 7-10
RV_MODELS = ("har", "naive")
# The forecast test's result is pinned: the SHA-256 of the result file that the scoring commit a57640723e2c pushed (and
# 3dd868e keeps). Without the pin, a fresh repository holding a forged result file and a spent.jsonl line written to
# match (git history and the side ledger would then agree with the forgery) passes every other check.
PINNED_RESULTS = {"2026-11-09-forecast-har-vs-naive": "66e07390c6772cd0a5c852aaff5176b5a336c2be90f0d94e2c829e2fa0c00fcc"}
LINE_KEYS = ("date", "purpose", "label", "trial_group", "split", "sample_start", "sample_end", "config_hash",
             "trial_hash", "code_fingerprint", "data_fingerprint", "source_commit", "run_id", "params")
LOCK = ".run_m4_grid.lock"
PURPOSE = "run of record: the M4 development grid (plan section 10, task 12)"


class DecisionError(RuntimeError):
    """The forecast test's committed result does not give the RV model: the grid refuses to run."""


class LockError(RuntimeError):
    """Another invocation holds the lock of this runs root or trial log."""


# --- the RV model, by the decision rule ------------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decided_rv_model(repo: Path = REPO, prereg_id: str = prereg.FORECAST_ID, pins: dict | None = None) -> str:
    """The RV model the forecast test chose, after the checks of the module docstring; DecisionError otherwise.
    `pins` (default PINNED_RESULTS) maps a pre-registration id to its result file's SHA-256: tests on made-up
    repositories hand their own; main() never does."""
    pins = PINNED_RESULTS if pins is None else pins
    if prereg_id not in pins:
        raise DecisionError(f"the pre-registration {prereg_id} is not pinned: no result of it is on record")
    repo = Path(repo)
    directory = prereg.prereg_dir(repo)
    try:
        spec = prereg.load(prereg_id, repo)
    except prereg.PreregError as error:
        raise DecisionError(f"the pre-registration {prereg_id} does not load: {error}") from error
    result_path = directory / f"{prereg_id}.result.json"
    sha_path = directory / f"{prereg_id}.sha256"
    spent_path = directory / prereg.SPENT
    for path in (result_path, sha_path, spent_path):
        if not path.is_file():
            raise DecisionError(f"{path.name} does not exist: the forecast test is not scored")
        if not prereg.committed(path, repo):
            raise DecisionError(f"{path.name} is not committed, or differs from the committed file")
    if sha256_of(result_path) != pins[prereg_id]:
        raise DecisionError(f"{result_path.name} has SHA-256 {sha256_of(result_path)}, not the pinned {pins[prereg_id]}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("prereg_id") != prereg_id:
        raise DecisionError(f"{result_path.name} names the pre-registration "
                            f"{result.get('prereg_id') if isinstance(result, dict) else result!r}, not {prereg_id}")
    if result.get("prereg_sha256") != sha256_of(sha_path):
        raise DecisionError(f"the result's prereg_sha256 {result.get('prereg_sha256')!r} is not the SHA-256 "
                            f"{sha256_of(sha_path)} of {sha_path.name}")
    lines = [line for line in prereg.read_lines(spent_path)
             if line.get("event") == "result" and line.get("prereg_id") == prereg_id]
    if len(lines) != 1:
        raise DecisionError(f"{spent_path.name} holds {len(lines)} result line(s) for {prereg_id}, not one")
    every = [line for line in prereg.ledger_lines(prereg.SPENT, prereg.SIDE_SPENT, repo)
             if line.get("event") == "result" and line.get("prereg_id") == prereg_id]
    if any(line != lines[0] for line in every):
        raise DecisionError(f"git or the side ledger holds another result line for {prereg_id}: a second scoring")
    if lines[0].get("result_sha256") != sha256_of(result_path):
        raise DecisionError(f"{result_path.name} has SHA-256 {sha256_of(result_path)}, not the "
                            f"{lines[0].get('result_sha256')!r} of the result line in {spent_path.name}")
    if lines[0].get("prereg_sha256") != result["prereg_sha256"]:
        raise DecisionError(f"the result line's prereg_sha256 {lines[0].get('prereg_sha256')!r} is not the result's")
    threshold, p = spec.get("threshold"), result.get("p")
    for name, value in (("threshold", threshold), ("p", p)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DecisionError(f"the {name} {value!r} is not a number")
    if not 0 < threshold < 1:                       # False for NaN and infinity too
        raise DecisionError(f"the threshold {threshold!r} is not a finite number in (0, 1)")
    if not 0 < p <= 1:
        raise DecisionError(f"the p {p!r} is not a finite number in (0, 1]")
    if result.get("threshold") != threshold:
        raise DecisionError(f"the result's threshold {result.get('threshold')!r} is not the registered {threshold!r}")
    names = [c.get("name") for c in spec.get("candidates") or []] + [(spec.get("benchmark") or {}).get("name")]
    if names != list(RV_MODELS):
        raise DecisionError(f"the pre-registration's candidate and benchmark are {names}, not {list(RV_MODELS)}")
    rule = "har" if p < threshold else "naive"
    if result.get("decision") != rule:
        raise DecisionError(f"the result's decision {result.get('decision')!r} does not follow the rule: p {p} "
                            f"against the threshold {threshold} gives {rule!r}")
    return rule


# --- the runs ---------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Task:
    label: str
    cfg: RunConfig
    strategy: object


def grid_tasks(rv_model: str, window: tuple[date, date] = DEVELOPMENT, only: str | None = None) -> list[Task]:
    """The grid's 36 runs on the development split, in m4_grid's order (one label with `only`)."""
    tasks = [Task(entry.label, RunConfig(sample_start=window[0], sample_end=window[1], split=SPLIT, **entry.engine),
                  entry.strategy) for entry in m4_grid(rv_model)]
    if only is not None:
        tasks = [task for task in tasks if task.label == only]
        if not tasks:
            raise ValueError(f"no grid entry is labelled {only!r}")
    return tasks


def gate_of(gate):
    """The run gate a worker passes run_backtest: the pre-registration's (prereg.make_run_gate) unless a test hands
    its own (tests on made-up stores, whose sessions are past 2019)."""
    return prereg.make_run_gate() if gate is None else gate


def run_one(task: Task, store_root, runs_root, commit: str, gate=None) -> dict:
    """One run (a worker's job): the run's id and folder, its timings and sessions, and the worker's peak RSS."""
    result = run_backtest(task.cfg, task.strategy, store=Store(store_root), runs_root=Path(runs_root),
                          source_commit=commit, store_check=build.require_current, run_gate=gate_of(gate))
    return {"label": task.label, "run_id": result.run_id, "run_dir": str(result.run_dir), "sessions": result.sessions,
            "timings": result.timings, "trial_hash": trial_hash(task.cfg, task.strategy), "pid": os.getpid(),
            "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}


def runs_row(run_dir: Path) -> dict:
    return pq.read_table(Path(run_dir) / "runs" / "part-0.parquet").to_pylist()[0]


def log_line(done: dict, purpose: str, day: str) -> dict:
    """The trial-log line of a finished run, from its runs table: LINE_KEYS, no metric."""
    row = runs_row(Path(done["run_dir"]))
    line = {"date": day, "purpose": purpose, "label": done["label"], "trial_group": row["trial_group"],
            "split": row["split"], "sample_start": row["sample_start"].isoformat(),
            "sample_end": row["sample_end"].isoformat(), "config_hash": row["config_hash"],
            "trial_hash": done["trial_hash"], "code_fingerprint": row["code_fingerprint"],
            "data_fingerprint": row["data_fingerprint"], "source_commit": row["source_commit"],
            "run_id": done["run_id"], "params": json.loads(row["config_json"])["strategy"]["params"]}
    assert tuple(line) == LINE_KEYS
    return line


def append_trial(path: Path, line: dict) -> None:
    """Append one line to the trial log and fsync it."""
    if tuple(line) != LINE_KEYS:
        raise ValueError(f"a trial-log line holds exactly {LINE_KEYS}, not {tuple(line)}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, sort_keys=False, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())


class grid_lock:
    """One invocation at a time per runs root and trial log: a lock file beside each, created with O_EXCL (as
    tools/prereg.py's ledger_lock is) and deleted on exit. A crashed invocation leaves the files: check the trial log
    and the runs folder, then delete them by hand."""

    def __init__(self, runs_root: Path, trial_log: Path) -> None:
        self.paths = [Path(runs_root) / LOCK, Path(trial_log).with_name(Path(trial_log).name + ".lock")]
        self.held: list[Path] = []

    def __enter__(self) -> "grid_lock":
        try:
            for path in self.paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                except FileExistsError:
                    raise LockError(f"{path} exists: another run_m4_grid invocation holds this runs root or trial log "
                                    "(if none does, one crashed: check the trial log and the runs folder, then "
                                    "delete the file)") from None
                self.held.append(path)
                try:
                    os.write(fd, f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n".encode())
                finally:
                    os.close(fd)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc) -> None:
        for path in self.held:
            path.unlink(missing_ok=True)
        self.held = []


def run_grid(tasks: list[Task], store_root, runs_root, trial_log: Path, workers: int = 1, purpose: str = PURPOSE,
             commit: str | None = None, gate=None, day: str | None = None) -> list[dict]:
    """Run the tasks (in this process with workers 1, else in a spawn pool of `workers`), appending each finished
    run's line to the trial log as it completes; returns the finished runs in completion order. Under grid_lock (a
    second invocation refuses: LockError). A worker error cancels the runs not yet started, waits for those running,
    logs a line for every run that completed (a run folder with no line would be an uncounted trial) and re-raises."""
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be an int in 1..{MAX_WORKERS}, not {workers!r}")
    with grid_lock(runs_root, trial_log):
        return _run_locked(tasks, store_root, runs_root, trial_log, workers, purpose, commit, gate, day)


def _run_locked(tasks, store_root, runs_root, trial_log, workers, purpose, commit, gate, day) -> list[dict]:
    commit = commit if commit is not None else source_commit()
    day = day or datetime.now(timezone.utc).date().isoformat()
    done = []

    def finish(item: dict) -> None:
        append_trial(trial_log, log_line(item, purpose, day))
        done.append(item)
        print(f"{item['label']}: run_id {item['run_id']} sessions {item['sessions']} timings "
              f"{json.dumps(item['timings'], sort_keys=True)} worker {item['pid']} peak RSS {item['peak_rss_mib']} MiB",
              flush=True)

    if workers == 1:
        for task in tasks:
            finish(run_one(task, store_root, runs_root, commit, gate))
        return done
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        futures = [pool.submit(run_one, task, store_root, runs_root, commit, gate) for task in tasks]
        logged, failure = set(), None
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception as error:
                failure = error
                break
            logged.add(future)
            finish(item)
        if failure is not None:
            for future in futures:
                future.cancel()
            wait([future for future in futures if not future.cancelled()])
            for future in futures:
                if future not in logged and not future.cancelled() and future.exception() is None:
                    finish(future.result())
            raise failure
    return done


# --- the trial log ----------------------------------------------------------------------------------------------------

def read_trials(path: Path = TRIAL_LOG) -> list[dict]:
    """The trial log's lines; ValueError for a line whose keys are not LINE_KEYS (a metric has no place in it)."""
    lines = [json.loads(text) for text in Path(path).read_text(encoding="utf-8").splitlines() if text.strip()]
    for number, line in enumerate(lines, 1):
        if not isinstance(line, dict) or tuple(line) != LINE_KEYS:
            raise ValueError(f"{path}:{number}: a trial-log line holds exactly {LINE_KEYS}")
    return lines


def trials(lines: list[dict], trial_group: str = TRIAL_GROUP,
           splits: tuple[str, ...] = (SPLIT,)) -> set[tuple[str, str, str]]:
    """The trials of the group: the distinct (config_hash, code_fingerprint, data_fingerprint) of its development
    lines (tests on made-up stores widen `splits`). config_hash holds the window, execution mode and data source that
    trial_hash drops, so a line for another window or mode is another trial, as are another code or another store."""
    return {(line["config_hash"], line["code_fingerprint"], line["data_fingerprint"]) for line in lines
            if line["trial_group"] == trial_group and line["split"] in splits}


def n_raw(lines: list[dict], trial_group: str = TRIAL_GROUP) -> int:
    """ADR-0010 §2's conservative N: the group's trials plus the design-choice log."""
    return len(trials(lines, trial_group)) + DESIGN_CHOICES


def latest_by_label(lines: list[dict], trial_group: str = TRIAL_GROUP) -> dict[str, dict]:
    """The last line of each label of the group, in the order the labels first appear (a later run of a label
    replaces an earlier one). Whatever its split: the readers (report_m4, the exporter) refuse a run that is not on
    the development split."""
    out = {}
    for line in lines:
        if line["trial_group"] == trial_group:
            out[line["label"]] = line
    return out


def in_sample_label(lines: list[dict], trial_group: str = TRIAL_GROUP) -> str:
    return (f"in-sample, {len(trials(lines, trial_group))} trials of N_raw {n_raw(lines, trial_group)}, "
            "selection-biased, no claim")


# --- the command line -------------------------------------------------------------------------------------------------

def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=1, help=f"processes, 1..{MAX_WORKERS}")
    parser.add_argument("--only", default=None, help="run one grid label (the measurement run)")
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument("--trial-log", type=Path, default=TRIAL_LOG)
    parser.add_argument("--purpose", default=PURPOSE, help="the trial log's purpose field for these runs")
    return parser.parse_args(argv)


def load() -> str:
    try:
        return Path("/proc/loadavg").read_text(encoding="utf-8").split()[0]
    except OSError:
        return "n/a"


def recovery(tasks: list[Task], logged: list[dict], options: str = "") -> str:
    """The steps after a failed grid: the labels that finished (they have a trial-log line) and a --only command for
    each label that did not."""
    finished = [line["label"] for line in logged]
    missing = [task.label for task in tasks if task.label not in finished]
    steps = [f"finished and logged ({len(finished)}): " + (", ".join(finished) or "none"),
             f"not run or failed ({len(missing)}): run each with:"]
    steps += [f"  uv run python tools/run_m4_grid.py{options} --only '{label}'" for label in missing]
    return "\n".join(steps)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    try:
        rv_model = decided_rv_model()
    except (DecisionError, prereg.PreregError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    tasks = grid_tasks(rv_model, only=args.only)
    store_root = Store(args.store).root
    runs_root = args.runs_root or config.work_dir() / "runs"
    before, started = load(), time.perf_counter()
    print(f"rv_model {rv_model} (the forecast test's committed decision); {len(tasks)} run(s), {args.workers} "
          f"worker(s), load average {before}", flush=True)
    before_lines = len(read_trials(args.trial_log)) if Path(args.trial_log).is_file() else 0
    try:
        done = run_grid(tasks, store_root, runs_root, args.trial_log, args.workers, args.purpose)
    except LockError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"failed: {type(error).__name__}: {error}", file=sys.stderr)
        options = "".join(f" {flag} {value}" for flag, value in (("--store", args.store), ("--runs-root", args.runs_root),
                                                                 ("--trial-log", args.trial_log if args.trial_log != TRIAL_LOG
                                                                  else None)) if value is not None)
        print(recovery(tasks, read_trials(args.trial_log)[before_lines:], options), file=sys.stderr)
        return 1
    lines = read_trials(args.trial_log)
    print(f"wall {time.perf_counter() - started:.1f} s; load average {before} before, {load()} after; max worker "
          f"peak RSS {max(item['peak_rss_mib'] for item in done)} MiB")
    print(f"trial log {args.trial_log}: {len(lines)} line(s); {in_sample_label(lines)}")
    print("P&L, NAV, returns, Sharpe and exit counts: not printed (decision D19, extended to every date before M6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
