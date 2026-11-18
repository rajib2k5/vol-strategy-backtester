"""A throwaway git repository holding a MADE-UP scored forecast test (not a test file: pytest does not collect it).

    scored_repo(root, p=0.01, decision="har", ...)   prereg files (<id>.json, .md, .sha256 by prereg.write), the
                                                     result file and spent.jsonl (a spent line and a result line),
                                                     committed once

What tools/run_m4_grid.py decided_rv_model reads. git writes go to the throwaway repository only; the project's
repository is read, never written. Made-up values only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import prereg  # noqa: E402

ID = "2026-11-09-made-up"
GIT_ENV = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def g(repo: Path, *args: str) -> str:
    """git in a throwaway repository (never the project's)."""
    assert Path(repo).resolve() != REPO
    out = subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c",
                          "commit.gpgsign=false", "-C", str(repo), *args], capture_output=True, text=True,
                         env=GIT_ENV)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def commit(repo: Path, message: str = "made up") -> None:
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", message)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def spent_lines(prereg_sha256: str, result_sha256: str) -> list[dict]:
    return [{"candidates": ["har"], "date": "2026-11-17", "event": "spent", "prereg_id": ID,
             "prereg_sha256": prereg_sha256, "window": {"end": "2019-11-29", "name": "made-up",
                                                        "split": "development", "start": "2010-01-04"}},
            {"date": "2026-11-17", "event": "result", "prereg_id": ID, "prereg_sha256": prereg_sha256,
             "result_sha256": result_sha256}]


def scored_repo(root: Path, p: float = 0.01, decision: str = "har", threshold: float = 0.025,
                result_changes: dict | None = None, line_changes: dict | None = None,
                spec_changes: dict | None = None) -> Path:
    """A committed throwaway repository with a made-up scored pre-registration (module docstring). result_changes
    edit the result file's keys; line_changes the spent.jsonl result line's; spec_changes add to the pre-registration's
    .json (the exporter's checked_forecast_test reads its test, size, effective_size and fragile_band)."""
    repo = Path(root) / "repo"
    directory = prereg.prereg_dir(repo)
    spec = {"id": ID, "kind": "forecast_test", "k": 1, "threshold": threshold,
            "candidates": [{"name": "har", "trial_hash": None}], "benchmark": {"name": "naive", "trial_hash": None},
            "decision_rule": f"use HAR if p < threshold ({threshold}); otherwise use naive (made up)",
            **(spec_changes or {})}
    prereg.write(spec, "# made up\n", directory)
    prereg_sha = sha256(directory / f"{ID}.sha256")
    result = {"prereg_id": ID, "prereg_sha256": prereg_sha, "p": p, "threshold": threshold, "alpha": threshold,
              "decision": decision, "label": "proxy: made up", **(result_changes or {})}
    result_path = directory / f"{ID}.result.json"
    write_json(result_path, result)
    lines = spent_lines(prereg_sha, sha256(result_path))
    lines[1].update(line_changes or {})
    (directory / prereg.SPENT).write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines),
                                          encoding="utf-8")
    g(repo, "init", "-q")
    commit(repo, "made-up scored pre-registration")
    return repo
