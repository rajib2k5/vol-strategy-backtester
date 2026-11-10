"""ADR-0001 test 3: the same store, config and commit give the same ledger bytes, in this process and in others.

The fixture backtest (the reference strategy with exit_dte 0 on tests/engine_store.py's made-up store: fills,
settlements, early assignments, hedges) runs twice here and once in each of three fresh interpreters with a different
PYTHONHASHSEED, so any order taken from a set or a dict of strings would show. Every ledger parquet file and both app
JSON bodies (blotter and positions_timeline, which have no generated_at) must have the same SHA-256 in all five runs.

A change of seed (ADR-0001 test 3's second part) is a new run: its config_hash, run_id (the folder) and runs table
change, run_meta.json with them, and every other ledger file keeps its bytes. M3 draws nothing at random.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import engine_helpers as eh
from volbt.data.store import file_sha256
from volbt.engine import report
from volbt.strategies.reference import RollingShortStraddle

TESTS = Path(__file__).resolve().parent
SEEDS = ("0", "1", "12345")

# Run in a fresh interpreter: argv[1] the store, argv[2] the runs root; prints the run folder and the body hashes.
CHILD = """
import json, sys
from pathlib import Path
import engine_helpers as eh
import test_engine_determinism as d
from volbt.data.store import Store
from volbt.strategies.reference import RollingShortStraddle
result = eh.run(Store(Path(sys.argv[1])), Path(sys.argv[2]), RollingShortStraddle(exit_dte=0))
print(json.dumps({"run_dir": str(result.run_dir), "bodies": d.body_hashes(result.run_dir)}))
"""


def body_hashes(run_dir) -> dict:
    bodies = {"blotter": report.blotter_body, "positions_timeline": report.positions_timeline_body}
    return {name: hashlib.sha256(json.dumps(body(run_dir), sort_keys=True).encode("utf-8")).hexdigest()
            for name, body in bodies.items()}


def ledger_hashes(run_dir) -> dict:
    run_dir = Path(run_dir)
    return {path.relative_to(run_dir).as_posix(): file_sha256(path) for path in sorted(run_dir.rglob("*.parquet"))}


def child_run(store_root, runs_root, seed) -> subprocess.Popen:
    env = {**os.environ, "PYTHONHASHSEED": seed,
           "PYTHONPATH": os.pathsep.join([str(TESTS.parent / "src"), str(TESTS), os.environ.get("PYTHONPATH", "")])}
    return subprocess.Popen([sys.executable, "-c", CHILD, str(store_root), str(runs_root)], env=env, cwd=TESTS.parent,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_here(engine_store, root, **overrides):
    result = eh.run(engine_store, root, RollingShortStraddle(exit_dte=0), **overrides)
    run_dir = result.run_dir
    return {"folder": run_dir.name, "ledger": ledger_hashes(run_dir), "bodies": body_hashes(run_dir)}


def test_the_ledger_and_the_json_bodies_have_the_same_bytes_in_every_process(engine_store, tmp_path):
    children = {seed: child_run(engine_store.root, tmp_path / f"seed{seed}", seed) for seed in SEEDS}
    runs = {"here 1": run_here(engine_store, tmp_path / "here1"), "here 2": run_here(engine_store, tmp_path / "here2")}
    for seed, child in children.items():
        out, err = child.communicate(timeout=600)
        assert child.returncode == 0, err
        reported = json.loads(out.strip().splitlines()[-1])
        run_dir = Path(reported["run_dir"])
        assert run_dir.is_relative_to(tmp_path / f"seed{seed}")
        runs[f"PYTHONHASHSEED={seed}"] = {"folder": run_dir.name, "ledger": ledger_hashes(run_dir),
                                          "bodies": reported["bodies"]}

    first = runs["here 1"]
    assert len(first["ledger"]) == 12 and set(first["bodies"]) == {"blotter", "positions_timeline"}
    for name, run in runs.items():
        assert run["folder"] == first["folder"], name
        assert run["ledger"] == first["ledger"], name
        assert run["bodies"] == first["bodies"], name
    # The run did what it is here to check: options filled, settled, assigned early and were hedged.
    run_dir = tmp_path / "here1" / first["folder"]
    assert {"assigned", "expired_worthless", "early_assigned"} <= set(eh.table(run_dir, "expiry_events")["event_type"])
    assert len(eh.table(run_dir, "fills")) >= 8 and (eh.table(run_dir, "hedges")["shares_traded"] != 0).any()


def test_a_change_of_seed_changes_only_the_runs_table_and_the_run_id(engine_store, tmp_path):
    base = run_here(engine_store, tmp_path / "seed0")
    other = run_here(engine_store, tmp_path / "seed7", seed=7)
    assert base["folder"] != other["folder"]
    assert base["ledger"].keys() == other["ledger"].keys()
    changed = [name for name in base["ledger"] if base["ledger"][name] != other["ledger"][name]]
    assert changed == ["runs/part-0.parquet"]
    runs_0 = eh.table(tmp_path / "seed0" / base["folder"], "runs")
    runs_7 = eh.table(tmp_path / "seed7" / other["folder"], "runs")
    assert [c for c in runs_0.columns if runs_0[c].tolist() != runs_7[c].tolist()] == ["config_hash", "config_json"]
    meta_0, meta_7 = (json.loads((tmp_path / root / folder / "run_meta.json").read_text(encoding="utf-8"))
                      for root, folder in (("seed0", base["folder"]), ("seed7", other["folder"])))
    assert meta_0["run_id"] != meta_7["run_id"]
    # The app bodies differ only in their run block's run_id and config_hash.
    bodies = {}
    for root, folder in (("seed0", base["folder"]), ("seed7", other["folder"])):
        run_dir = tmp_path / root / folder
        bodies[root] = {"blotter": report.blotter_body(run_dir), "positions": report.positions_timeline_body(run_dir)}
    for name in ("blotter", "positions"):
        a, b = bodies["seed0"][name], bodies["seed7"][name]
        assert {k: v for k, v in a.items() if k != "run"} == {k: v for k, v in b.items() if k != "run"}
        assert [k for k in a["run"] if a["run"][k] != b["run"][k]] == ["run_id", "config_hash"]
