"""Fail when a raw vendor file is about to be committed, or when a data file is too big to commit.

    uv run python tools/licensing/check_tracked_data.py             # this repo
    uv run python tools/licensing/check_tracked_data.py --repo DIR  # another git work tree (the tests plant files in one)

What it reads is what git would commit, never the folder as it lies on disk:

* the paths of ``git ls-files -co --exclude-standard`` (everything git tracks plus every untracked file that
  .gitignore does not hide, so exactly what the next ``git add .`` would take) and of
  ``git diff --cached --name-only --diff-filter=ACMR`` (what is staged);
* the staged content of each path, read from the index (``git ls-files -s``, ``git cat-file``), so a file that is
  staged and then deleted or changed on disk is judged by what was staged;
* the work-tree file as well, when there is one: ``git add .`` or ``git commit -a`` would take it.

A file that .gitignore hides never shows up; a force-added one does.

The policy (owner, 2026-10-29): small derived data, the app JSON and real values in docs are fine, and
`DATA.md` gives each source's terms. The downloaded vendor files themselves are never committed. FAIL when a
listed file is:

* a ``*.duckdb`` database;
* a ``*.parquet`` file outside ``tests/fixtures/``: the OptionsDX/Kaggle chains, a DoltHub export or a built store
  (``tests/fixtures/`` holds the tiny synthetic fixtures the schema-pin tests read);
* under ``data/raw/``: the raw CSV (and other) downloads of the reference series and the vendors;
* a dolt clone file: inside a ``.dolt``, ``.doltcfg``, ``dolt_root`` or ``dolt_mirror`` folder, or a ``*.darc`` archive;
* inside a Kaggle download folder: a folder called ``kaggle`` or ``spy-eod-2010-2023``;
* a data-like file (see DATA_EXTENSIONS) of more than 50 MiB;
* a byte-for-byte copy of a raw vendor file under any name: its SHA-256 equals that of a file under
  ``config.raw_dir()`` (the Cboe, FRED and yfinance downloads and the DoltHub export) or of a ``*.parquet`` file in
  ``config.kaggle_dir()/spy-eod-2010-2023`` (OptionsDX). Only a candidate of the same size as some raw file is
  hashed, and the raw hashes are cached in ``<work_dir>/cache/raw_hashes.json`` (git-ignored), keyed by path, size
  and mtime. With no raw file on this machine (CI) this check is skipped, loudly; the others still run.

WARN (exit code stays 0) when a data-like file is more than 10 MiB: say why it is needed, or shrink it.

Exit code: 0 clean (warnings allowed), 1 at least one FAIL, 2 the folder is not a git work tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]

WARN_BYTES = 10 * 1024 * 1024
FAIL_BYTES = 50 * 1024 * 1024
CHUNK = 1024 * 1024

# Files that hold data, whatever their name: the size limits apply to these. Images, notebooks and source
# code are not in the list.
DATA_EXTENSIONS = frozenset({
    ".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson", ".parquet", ".feather", ".arrow", ".orc", ".avro",
    ".duckdb", ".db", ".sqlite", ".sqlite3", ".xlsx", ".xls", ".zip", ".gz", ".bz2", ".xz", ".7z", ".tar",
    ".npy", ".npz", ".pkl", ".pickle", ".h5", ".hdf5", ".dat", ".darc",
})
DOLT_DIRS = frozenset({".dolt", ".doltcfg", "dolt_root", "dolt_mirror"})
KAGGLE_DIRS = frozenset({"kaggle", "spy-eod-2010-2023"})

KAGGLE_DATASET_DIR = "spy-eod-2010-2023"      # volbt.data.optionsdx.DATASET_DIR, under config.kaggle_dir()
SIDECAR_SUFFIXES = (".meta.json", ".export.json")  # our own provenance notes beside a download, not vendor data
CACHE_NAME = "raw_hashes.json"
GITLINK_MODE = b"160000"                      # a submodule: the index holds a commit, not a blob


class Content(NamedTuple):
    """One version of a file that git could commit: the staged blob (`blob` is its id) or the work-tree file."""

    where: str
    size: int
    blob: str | None


def git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, check=False)
    except FileNotFoundError:
        raise SystemExit("error: git is not installed")
    if done.returncode != 0:
        message = done.stderr.decode(errors="replace").strip()
        print(f"error: git {args[0]} failed in {repo} ({message})", file=sys.stderr)
        raise SystemExit(2)
    return done.stdout


def require_work_tree(repo: Path) -> None:
    try:
        done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
                              capture_output=True, check=False)
    except FileNotFoundError:
        raise SystemExit("error: git is not installed")
    if done.returncode != 0 or done.stdout.strip() != b"true":
        message = done.stderr.decode(errors="replace").strip()
        print(f"error: {repo} is not a git work tree ({message})", file=sys.stderr)
        raise SystemExit(2)


def paths_of(output: bytes) -> set[str]:
    return {p.decode("utf-8", errors="replace") for p in output.split(b"\0") if p}


def listed_files(repo: Path) -> list[str]:
    """The paths (relative, "/" separated) that `git ls-files -co --exclude-standard` lists in `repo`."""
    return sorted(paths_of(git(repo, "ls-files", "-co", "--exclude-standard", "-z")))


def staged_files(repo: Path) -> list[str]:
    """The paths that `git diff --cached --name-only --diff-filter=ACMR` lists: added, copied, modified or renamed."""
    return sorted(paths_of(git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--relative", "-z")))


def index_blobs(repo: Path) -> dict[str, list[str]]:
    """Path -> ids of the blobs the index holds for it (one per stage; submodules have none)."""
    blobs: dict[str, list[str]] = {}
    for record in git(repo, "ls-files", "-s", "-z").split(b"\0"):
        meta, _, name = record.partition(b"\t")
        fields = meta.split()
        if len(fields) != 3 or fields[0] == GITLINK_MODE:
            continue
        blobs.setdefault(name.decode("utf-8", errors="replace"), []).append(fields[1].decode())
    return blobs


def blob_sizes(repo: Path, blobs: Iterable[str]) -> dict[str, int]:
    """Blob id -> size in bytes, for each id that is a blob."""
    ids = sorted(set(blobs))
    if not ids:
        return {}
    out = git(repo, "cat-file", "--batch-check", stdin=("\n".join(ids) + "\n").encode())
    sizes = {}
    for line in out.decode(errors="replace").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1] == "blob":
            sizes[fields[0]] = int(fields[2])
    return sizes


def sha256_chunks(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return sha256_chunks(iter(lambda: handle.read(CHUNK), b""))


def sha256_blob(repo: Path, blob: str) -> str:
    """SHA-256 of a staged blob, streamed from `git cat-file blob` (the files are tens of MB)."""
    with subprocess.Popen(["git", "-C", str(repo), "cat-file", "blob", blob],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        digest = sha256_chunks(iter(lambda: proc.stdout.read(CHUNK), b""))
    if proc.returncode != 0:
        print(f"error: git cat-file blob {blob} failed in {repo}", file=sys.stderr)
        raise SystemExit(2)
    return digest


def read_cache(cache_path: Path | None) -> dict:
    if cache_path is None:
        return {}
    try:
        files = json.loads(Path(cache_path).read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError, AttributeError):
        return {}
    return files if isinstance(files, dict) else {}


def write_cache(cache_path: Path, files: dict) -> None:
    """Best effort: the cache only saves time, so a folder we cannot write to is not an error."""
    cache_path = Path(cache_path)
    scratch = cache_path.with_name(cache_path.name + f".{os.getpid()}.tmp")
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        scratch.write_text(json.dumps({"version": 1, "files": files}, indent=1, sort_keys=True), encoding="utf-8")
        scratch.replace(cache_path)
    except OSError:
        scratch.unlink(missing_ok=True)


def raw_digests(raw_files: Iterable[Path], cache_path: Path | None) -> tuple[dict[int, dict[str, Path]], int, int]:
    """({size: {sha256: raw file}}, raw files read, raw files hashed on this run (the rest came from the cache)).

    A cache entry is used only while the file's size and mtime are the ones it was made with. Empty files are
    left out: every empty file would match them.
    """
    cached = read_cache(cache_path)
    fresh: dict[str, dict] = {}
    by_size: dict[int, dict[str, Path]] = {}
    hashed = 0
    for file in sorted({Path(f) for f in raw_files}):
        try:
            info = file.stat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            continue
        entry = cached.get(str(file))
        if (isinstance(entry, dict) and entry.get("size") == info.st_size
                and entry.get("mtime_ns") == info.st_mtime_ns and isinstance(entry.get("sha256"), str)):
            digest = entry["sha256"]
        else:
            digest = sha256_file(file)
            hashed += 1
        fresh[str(file)] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": digest}
        by_size.setdefault(info.st_size, {})[digest] = file
    if cache_path is not None and fresh != cached:
        write_cache(cache_path, fresh)
    return by_size, len(fresh), hashed


def default_raw_files() -> list[Path]:
    """The raw vendor files on this machine: everything under raw_dir() and the OptionsDX parquet files."""
    config = volbt_config()
    files = [p for p in sorted(config.raw_dir().rglob("*")) if p.is_file() and not p.name.endswith(SIDECAR_SUFFIXES)]
    files += sorted((config.kaggle_dir() / KAGGLE_DATASET_DIR).glob("*.parquet"))
    return files


def default_cache_path() -> Path:
    return volbt_config().work_dir() / "cache" / CACHE_NAME


def volbt_config():
    try:
        from volbt import config
    except ImportError:  # a bare `python` run: the package sits in src/
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from volbt import config
    return config


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


def contents_of(path: str, repo: Path, blobs: dict[str, list[str]], sizes: dict[str, int]) -> list[Content]:
    """Every version of `path` git could commit: the staged blob(s), then the work-tree file if it is there."""
    found = [Content("the staged file", sizes[b], b) for b in blobs.get(path, ()) if b in sizes]
    file = repo / path
    if file.is_file():  # a tracked file deleted from the work tree has only its staged version
        found.append(Content("the work-tree file", file.stat().st_size, None))
    return found


def check(repo: Path, raw_files: Sequence[Path] = (), cache_path: Path | None = None) -> tuple[list[str], list[str], list[str], int]:
    """(failures, warnings, notes, files looked at) for what git would commit in `repo`.

    `raw_files` are the raw vendor files a candidate is compared with by SHA-256 (main() passes the ones on this
    machine); `cache_path` is where their hashes are kept between runs (None: no cache).
    """
    require_work_tree(repo)
    failures: list[str] = []
    warnings: list[str] = []
    files = sorted(set(listed_files(repo)) | set(staged_files(repo)))
    blobs = index_blobs(repo)
    sizes = blob_sizes(repo, (b for ids in blobs.values() for b in ids))
    by_size, raw_count, raw_hashed = raw_digests(raw_files, cache_path)
    compared = 0
    for path in files:
        reason = raw_vendor_reason(path)
        if reason:
            failures.append(f"{path}: {reason}")
        contents = contents_of(path, repo, blobs, sizes)
        for content in contents:
            same_size = by_size.get(content.size)
            if not same_size:
                continue
            compared += 1
            digest = sha256_blob(repo, content.blob) if content.blob else sha256_file(repo / path)
            if digest in same_size:
                failures.append(f"{path}: {content.where} is a byte-for-byte copy of the raw vendor file {same_size[digest]}")
                break
        if PurePosixPath(path).suffix.lower() not in DATA_EXTENSIONS or not contents:
            continue  # not data, or neither staged nor in the work tree
        size = max(c.size for c in contents)
        if size > FAIL_BYTES:
            failures.append(f"{path}: data file of {size / 2**20:.1f} MiB, over the {FAIL_BYTES // 2**20} MiB limit")
        elif size > WARN_BYTES:
            warnings.append(f"{path}: data file of {size / 2**20:.1f} MiB, over {WARN_BYTES // 2**20} MiB: keep it only if the app or a doc needs it")
    if raw_count:
        notes = [f"note: SHA-256 check against {raw_count} raw vendor file(s): {raw_hashed} hashed this run, "
                 f"{raw_count - raw_hashed} from the cache; {compared} same-size candidate version(s) hashed"]
    else:
        notes = ["note: SHA-256 check skipped: no raw vendor files on this machine (none under raw_dir() or in the Kaggle "
                 "folder), so a renamed copy is not caught here; the name and size rules still ran"]
    return failures, warnings, notes, len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", "--root", dest="repo", type=Path, default=REPO_ROOT,
                        help="the git work tree to check (default: this repo); the raw vendor files are always this machine's")
    args = parser.parse_args(argv)
    try:
        raw_files, cache_path = default_raw_files(), default_cache_path()
    except ValueError as error:  # config.SharedCloneError: VOLBT_WORK_DIR points into the shared DoltHub clone
        print(f"error: {error}", file=sys.stderr)
        return 2
    failures, warnings, notes, count = check(args.repo, raw_files, cache_path)
    for line in warnings:
        print(f"warn: {line}")
    for line in failures:
        print(f"FAIL: {line}")
    if failures:
        print(f"{len(failures)} problem(s) in {count} files git would commit")
    else:
        print(f"clean: 0 raw vendor files in {count} files git would commit ({len(warnings)} size warning(s))")
    for line in notes:
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
