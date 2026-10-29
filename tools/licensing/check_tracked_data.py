"""Fail when a raw vendor file is about to be committed, or when a data file is too big to commit.

    uv run python tools/licensing/check_tracked_data.py             # this repo
    uv run python tools/licensing/check_tracked_data.py --root DIR  # another git work tree (the tests plant files in one)

The files it looks at are those of ``git ls-files -co --exclude-standard``: everything git tracks plus
every untracked file that .gitignore does not hide, so exactly what the next ``git add .`` would take.
A file that .gitignore hides never shows up here; a force-added one does.

The policy (owner, 2026-10-29): small derived data, the app JSON and real values in docs are fine, and
`DATA.md` gives each source's terms. The downloaded vendor files themselves are never committed. FAIL when a
listed file is:

* a ``*.duckdb`` database;
* a ``*.parquet`` file outside ``tests/fixtures/``: the OptionsDX/Kaggle chains, a DoltHub export or a built store
  (``tests/fixtures/`` holds the tiny synthetic fixtures the schema-pin tests read);
* under ``data/raw/``: the raw CSV (and other) downloads of the reference series and the vendors;
* a dolt clone file: inside a ``.dolt``, ``.doltcfg``, ``dolt_root`` or ``dolt_mirror`` folder, or a ``*.darc`` archive;
* inside a Kaggle download folder: a folder called ``kaggle`` or ``spy-eod-2010-2023``;
* a data-like file (see DATA_EXTENSIONS) of more than 50 MiB.

WARN (exit code stays 0) when a data-like file is more than 10 MiB: say why it is needed, or shrink it.

Exit code: 0 clean (warnings allowed), 1 at least one FAIL, 2 the folder is not a git work tree.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]

WARN_BYTES = 10 * 1024 * 1024
FAIL_BYTES = 50 * 1024 * 1024

# Files that hold data, whatever their name: the size limits apply to these. Images, notebooks and source
# code are not in the list.
DATA_EXTENSIONS = frozenset({
    ".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson", ".parquet", ".feather", ".arrow", ".orc", ".avro",
    ".duckdb", ".db", ".sqlite", ".sqlite3", ".xlsx", ".xls", ".zip", ".gz", ".bz2", ".xz", ".7z", ".tar",
    ".npy", ".npz", ".pkl", ".pickle", ".h5", ".hdf5", ".dat", ".darc",
})
DOLT_DIRS = frozenset({".dolt", ".doltcfg", "dolt_root", "dolt_mirror"})
KAGGLE_DIRS = frozenset({"kaggle", "spy-eod-2010-2023"})


def listed_files(root: Path) -> list[str]:
    """The paths (relative, "/" separated) that `git ls-files -co --exclude-standard` lists in `root`."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        raise SystemExit("error: git is not installed")
    if done.returncode != 0:
        message = done.stderr.decode(errors="replace").strip()
        print(f"error: {root} is not a git work tree ({message})", file=sys.stderr)
        raise SystemExit(2)
    return sorted({p.decode("utf-8", errors="replace") for p in done.stdout.split(b"\0") if p})


def raw_vendor_reason(path: str) -> str | None:
    """Why this path is a raw vendor file, or None. Matching is on the path alone, in lower case."""
    parts = [p.lower() for p in PurePosixPath(path).parts]
    name, folders = parts[-1], parts[:-1]
    if name.endswith(".duckdb"):
        return "DuckDB database"
    if name.endswith(".parquet") and folders[:2] != ["tests", "fixtures"]:
        return "Parquet file outside tests/fixtures/ (vendor chains, an export or a built store)"
    if any(a == "data" and b == "raw" for a, b in zip(parts, parts[1:])):
        return "raw download under data/raw/"
    if name.endswith(".darc") or any(p in DOLT_DIRS for p in folders):
        return "dolt clone file"
    if any(p in KAGGLE_DIRS for p in folders):
        return "Kaggle download folder"
    return None


def check(root: Path) -> tuple[list[str], list[str], int]:
    """(failures, warnings, files looked at) for the files git lists in `root`."""
    failures: list[str] = []
    warnings: list[str] = []
    files = listed_files(root)
    for path in files:
        reason = raw_vendor_reason(path)
        if reason:
            failures.append(f"{path}: {reason}")
        file = root / path
        if PurePosixPath(path).suffix.lower() not in DATA_EXTENSIONS or not file.is_file():
            continue  # not data, or listed but deleted from the work tree
        size = file.stat().st_size
        if size > FAIL_BYTES:
            failures.append(f"{path}: data file of {size / 2**20:.1f} MiB, over the {FAIL_BYTES // 2**20} MiB limit")
        elif size > WARN_BYTES:
            warnings.append(f"{path}: data file of {size / 2**20:.1f} MiB, over {WARN_BYTES // 2**20} MiB: keep it only if the app or a doc needs it")
    return failures, warnings, len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="the git work tree to check (default: this repo)")
    args = parser.parse_args(argv)
    failures, warnings, count = check(args.root)
    for line in warnings:
        print(f"warn: {line}")
    for line in failures:
        print(f"FAIL: {line}")
    if failures:
        print(f"{len(failures)} problem(s) in {count} files git would commit")
        return 1
    print(f"clean: 0 raw vendor files in {count} files git would commit ({len(warnings)} size warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
