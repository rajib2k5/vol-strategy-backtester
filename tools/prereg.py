"""Pre-registration: the frozen files, the one-shot ledgers and the run gate (milestone 4, plan section 6).

Run:  uv run python tools/prereg.py dependence --out DEPENDENCE.json
      the centred summaries of the 2002-2009 d-series (the input of tools/forecast_size.py match)
      uv run python tools/prereg.py forecast --size BATTERY.json --match MATCH.json --variants VARIANTS.json
          --conditional CONDITIONAL.json --conditional-earlier EARLIER.json --combinations COMBINATIONS.json
      measure them again and write the forecast test's three files; the six inputs are the outputs of
      tools/forecast_size.py battery, match, variants, conditional (the main draw and an earlier one) and
      combinations, copied into the file's "size", "matched", "variants", "conditional" and "combinations" sections;
      the .md is rationale_for() of the .json as written

The files of one pre-registration, in docs/validation/prereg/ (the one folder the tools read and write):

    <id>.json     the claim, candidates (by trial_hash), benchmark and k; the metric and its proxy label; the paired
                  difference and its side; the windows (dates, n, the SHA-256 of the date list); the dependence
                  summary of the calibration window; the test (function, draws, seed), its simulated size on the
                  battery and on the matched nulls, and the decision threshold; the correction; the PSR/DSR spec; the
                  decision rule; the scoring command, the scorer's files and SHA-256 and the library and Python
                  versions; the store tables' SHA-256
    <id>.md       the rationale
    <id>.sha256   the `sha256sum` lines of both

and two append-only ledgers beside them, each with a side ledger in the git common directory
(`git rev-parse --git-common-dir`), which a stash, checkout, clean, reset or branch switch never touches:

    spent.jsonl            (side: volbt-prereg-spent.jsonl) a "spent" line per window of a scored pre-registration
                           {event, window, prereg id and hash, candidates, date}, written before the result is
                           computed, then a "result" line {event, prereg id and hash, result hash, date}. A spent line
                           spends its window for every candidate: a window that shares a date with it is spent,
                           whatever its split label (the run gate compares only a run's dates after 2019-12-31;
                           fix pass 6, item H5)
    runs_of_record.jsonl   (side: volbt-prereg-runs.jsonl) per run past 2019, trial or diagnostic, a "started" line
                           {event, record_id, date, trial_hash, prereg_id, split, run_purpose, diagnostic_kind,
                           data_source, execution_mode, start, end, rerun_of, rerun_reason} written by the gate before
                           the run reads anything, and a "completed" line (the same and run_id, config_hash) after its
                           folder is in place. The nine lines written before fix pass 2 have no "event": each is a run
                           that started and completed. A diagnostic line with no "diagnostic_kind" (those nine) reads
                           by LEGACY_KIND_RULE (fix pass 3): "budget" when its window starts by 2019-12-31 (the M4
                           budget run, 2010-01-04 to 2023-12-29), else "smoke" (the eight M4 smoke runs, 2020-01-02 to
                           2023-12-29); the file is read, never rewritten. The nine count toward no current limit
                           (fix pass 4): their trial_hash has the old formula, which no current configuration gives

A ledger is read from its working file, its side ledger and every version of the file git can reach (the index and
every commit reachable from a ref or a reflog entry: `git rev-list --all --reflog`); a shallow repository is refused.
Appends happen under a lock file in the git common directory (O_EXCL).

    load(prereg_id)           the spec, after checking the .sha256 lines and that all three files are committed
    make_run_gate(...)        the run_gate tools pass to run_backtest (plan section 6, ADR-0010 tests 4b and 8)
    spent_by(window)          the spent line whose window shares a date with `window` (spent_lines)
    runs_of_record()          the runs past 2019, started and completed
    scorer_closure()          the repository files the scorer imports, computed from their source (ast)
    scorer_sha256()           SHA-256 of those files
    check_loaded()            every closure module this process loaded comes from the repository (its __file__ and
                              __spec__.origin), and no sitecustomize or usercustomize from outside the standard library
    library_versions()        the versions of the third-party packages those files import, and Python's

Committed means: no component of the path, from the repository root down, is a symlink (lstat), the repository's
.git is a directory, `git rev-parse HEAD:<path>` names a blob, and the git blob hash of the working file equals it.
git runs read-only, with every GIT_* variable of the caller removed, no system or global config, no replace objects
(--no-replace-objects and GIT_NO_REPLACE_OBJECTS=1), no grafts (GIT_GRAFT_FILE=/dev/null; fix pass 4, review E
claim 5) and no commit-graph file (-c core.commitGraph=false; fix pass 5, review F claim 6), so neither GIT_DIR,
GIT_INDEX_FILE, a replace ref, a .git/info/grafts line nor a forged commit-graph can make another file look
committed, or hide a commit that holds a spent line from `git rev-list --all --reflog`. A file outside the repository
is never committed. Nothing here writes to git; the side ledgers and the lock are plain files in its directory.

These checks are tripwires against accidents and shortcuts (an edited file, a second scoring after a stash, checkout,
clean, reset, revert or branch switch, a relabelled window, a symlink, a git environment that points elsewhere, a
graft or a replace ref, a module loaded from another checkout), not a sandbox: they do not stop code written to defeat
them (check_loaded). A scoring leaves its spent lines in this clone's side ledger and in every commit or stash that
holds spent.jsonl. A clone has no side ledger, so these also defeat them (fix pass 3, review D claim 4; revised after
the seventh review: "what still defeats them is" read as a complete list):
  - any clone whose refs do not reach a commit holding the spent line: a clone made before the scoring was committed,
    a single-branch clone of a branch that does not hold it, a clone made after a reset or a history rewrite dropped
    it (whatever the original's reflog still holds), a clone of a remote that never received it, and `python -m`
    run from another checkout's tools/ (it reads that checkout's ledgers);
  - deleting the side ledger together with every ref and reflog entry that reaches the line;
  - any copy of the code and data outside this repository.
The holdout-once record (runs_of_record.jsonl and its side ledger, make_run_gate) has the same limits (review D N2).
A linked worktree (`git worktree add`) is refused: its .git is a file. The remedy is to commit the result, spent.jsonl
and runs_of_record.jsonl and push at once: the pushed history is then the record.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import math
import os
import platform
import re
import stat
import subprocess
import sys
import sysconfig
import textwrap
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREREG_REL = "docs/validation/prereg"
PREREG_DIR = REPO / PREREG_REL
SPENT, RECORDS = "spent.jsonl", "runs_of_record.jsonl"
SIDE_SPENT, SIDE_RECORDS = "volbt-prereg-spent.jsonl", "volbt-prereg-runs.jsonl"    # in the git common directory
LOCK, LOCK_WAIT_S = "volbt-prereg.lock", 10.0
DEVELOPMENT_END = date(2019, 12, 31)
LEGACY_KIND_RULE = ('a diagnostic line with no "diagnostic_kind" (written before fix pass 3) reads as "budget" when '
                    'its window starts by 2019-12-31, else as "smoke"')
# Plan section 6's health runs (the smoke and the budget runs). They never run on a configuration a pre-registration
# lists (fix pass 4, item F6d), and they are counted apart from ADR-0010 §1's and ADR-0009 §4's diagnostics (the volume
# cap, runs S, M and M'): the health runs per trial_hash, kind, data source and execution mode, the ADR diagnostics per
# trial_hash and kind, neither toward the other's limit (fix pass 5, item G1)
HEALTH_KINDS = ("smoke", "budget")
UNLISTED_ONLY_KINDS = HEALTH_KINDS
# The (data source, execution mode) pairs a health run may use: the ones tools/smoke_m4.py uses (MODES for the smoke,
# BUDGET_MODE for the budget run). A health run on another pair is refused: no tool runs one, and each would be one
# more run of the configuration on validation dates (fix pass 6, item H4; review G claim 1)
HEALTH_PAIRS = {"smoke": (("optionsdx", "quote"), ("dolthub", "surface")), "budget": (("optionsdx", "quote"),)}
SCORER = "tools/score_prereg.py"
SOURCE_ROOTS = ("tools", "src")
MAX_VALIDATION_RUNS = 3     # the run of record and two re-runs (ADR-0010 test 8)


class PreregError(RuntimeError):
    """A pre-registration check failed: the scorer or the run gate refuses."""


def prereg_dir(repo: Path = REPO) -> Path:
    return Path(repo) / PREREG_REL


# --- hashes and git (read-only) ------------------------------------------------------------------------------------

def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    """The object id git gives a file with these bytes."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def git(repo: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """git in `repo`, read-only: no GIT_* variable of the caller, no system or global config, no replace objects and
    no grafts (GIT_GRAFT_FILE names the null device, so .git/info/grafts is never read; fix pass 4, item F7), and no
    commit-graph file (-c core.commitGraph=false: a forged .git/objects/info/commit-graph can drop a commit's parent,
    as a graft does; fix pass 5, item G6, review F claim 6), so parents are read from the commit objects."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.run(["git", "--no-replace-objects", "-c", "core.commitGraph=false", "-C", str(repo), *args],
                          capture_output=True, env=env, input=None if stdin is None else stdin.encode("utf-8"))


def relative(path: Path, repo: Path = REPO) -> str:
    """`path` relative to the repository, as git names it. PreregError when the repository's .git is not a directory
    or any component of the path, from the repository root down, is a symlink (lstat, nothing resolved); ValueError
    when the path is outside the repository; FileNotFoundError when a component does not exist."""
    root = Path(os.path.abspath(repo))
    rel = Path(os.path.abspath(path)).relative_to(root)
    if not stat.S_ISDIR(os.lstat(root / ".git").st_mode):
        raise PreregError(f"{root / '.git'} is not a directory (a symlink or a gitdir file): refused")
    current = root
    for part in rel.parts:
        current = current / part
        if stat.S_ISLNK(os.lstat(current).st_mode):
            raise PreregError(f"{current} is a symlink: a checked path has none")
    return rel.as_posix()


def committed(path: Path, repo: Path = REPO) -> bool:
    """True when `path` is a regular file in HEAD and the working file has HEAD's bytes (module docstring).
    PreregError on a symlink; False outside the repository or for a missing file."""
    try:
        rel = relative(path, repo)
    except (ValueError, FileNotFoundError):
        return False
    if not stat.S_ISREG(os.lstat(path).st_mode):
        return False
    out = git(repo, "rev-parse", "--verify", "--quiet", f"HEAD:{rel}")
    return out.returncode == 0 and out.stdout.decode().strip() == git_blob_sha1(Path(path).read_bytes())


def dates_sha256(days) -> str:
    """SHA-256 of the ISO dates, one per line."""
    return hashlib.sha256(("\n".join(d.isoformat() for d in days) + "\n").encode("utf-8")).hexdigest()


# --- the scorer's code and libraries ---------------------------------------------------------------------------------

def module_files(name: str, repo: Path = REPO) -> list[Path]:
    """The repository files that `import name` loads: the module and the __init__.py of each package on its way,
    under tools/ or src/. [] for a module the repository does not hold (the standard library, a third party)."""
    parts = name.split(".")
    for root in SOURCE_ROOTS:
        out, base = [], Path(repo) / root
        for part in parts:
            base = base / part
            if (base / "__init__.py").is_file():
                out.append(base / "__init__.py")
            elif base.with_suffix(".py").is_file():
                out.append(base.with_suffix(".py"))
                break                                   # what follows is a name inside the module
            else:
                break
        if out:
            return out
    return []


def package_of(path: Path, repo: Path) -> list[str]:
    """The package a file under src/ belongs to, as a list of names (for a relative import); [] under tools/."""
    src = Path(repo) / "src"
    if not Path(path).is_relative_to(src):
        return []
    parts = list(Path(path).relative_to(src).with_suffix("").parts)
    return parts[:-1]                   # a module's package; for an __init__.py, the package itself


def imported_names(path: Path, repo: Path) -> list[str]:
    """Every module name an import statement of the file names, at any depth (function-level imports included);
    for `from a import b`, both a and a.b (b may be a submodule)."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = package_of(path, repo)
                base = ".".join(package[:len(package) - node.level + 1] + ([node.module] if node.module else []))
            else:
                base = node.module
            names += [base] + [f"{base}.{alias.name}" for alias in node.names]
    return names


def scorer_closure(repo: Path = REPO) -> list[str]:
    """The repository files the scorer can load: tools/score_prereg.py and, transitively, every module of tools/ or
    src/ an import in them names, with each package's __init__.py, sorted (paths relative to the repository).
    Computed from the source, not listed by hand, so an import added anywhere joins the hash."""
    todo, seen = [Path(repo) / SCORER], set()
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        for name in imported_names(path, repo):
            todo += module_files(name, repo)
    return sorted(p.relative_to(repo).as_posix() for p in seen)


def libraries(repo: Path = REPO) -> list[str]:
    """The third-party top-level packages the closure's files import (not the standard library, not the repo's)."""
    out = set()
    for rel in scorer_closure(repo):
        for name in imported_names(Path(repo) / rel, repo):
            top = name.split(".")[0]
            if top and top != "__future__" and top not in sys.stdlib_module_names and not module_files(top, repo):
                out.add(top)
    return sorted(out)


def library_versions(repo: Path = REPO) -> dict[str, str]:
    """{package: __version__} for libraries(), and "python": the interpreter's version (platform.python_version;
    fix pass 2, review B N1): the scorer refuses another version of any (numpy, pandas and pyarrow among them)."""
    versions = {name: str(importlib.import_module(name).__version__) for name in libraries(repo)}
    return {**versions, "python": platform.python_version()}


def module_name(rel: str) -> str:
    """The import name of a closure file: tools/x.py -> x, src/a/b.py -> a.b, src/a/__init__.py -> a."""
    parts = list(Path(rel).with_suffix("").parts[1:])
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def check_loaded(repo: Path = REPO, modules_root: Path | None = None) -> None:
    """PreregError unless every module of scorer_closure(), imported in this process, was loaded from
    <modules_root>/<rel> (the repository by default), and a scorer run as a script is
    <modules_root>/tools/score_prereg.py: a PYTHONPATH or sys.path entry that puts another checkout first is refused
    (fix pass 2, review B claim 2). Both the module's __file__ and its __spec__.origin (where the import system found
    its code) must be that file, and a sitecustomize or usercustomize module loaded from anywhere but the top folder
    of the interpreter's standard library is refused: it runs before the scorer and can put another module in place
    (fix pass 3, review D claim 5). tools/score_prereg.py runs the scorer's other checks of its process: name_clashes
    before `import prereg` (fix pass 7, item I1), check_process before any third-party import (fix pass 4, item F5;
    fix pass 5, item G5; fix pass 6, item H1), and check_tools_modules again under the ledgers' lock; its module
    docstring says what each refuses and when (revised after the seventh review: this docstring listed them).
    `python -I` cannot run the scorer: it leaves the script's folder off sys.path, so `import prereg` fails (review E
    N1; kept so).

    The checks trust module metadata (sys.modules and the modules' attributes) and the process's own code. They catch
    mistakes and the routes they name; they do not stop code written to defeat them. Any code that runs in the
    scorer's process before or between the checks can defeat them: a file put on the import path, a .pth file in
    site-packages, an edited library or standard library file, a forged bytecode file (a tools/__pycache__/*.pyc, or
    a src/ one, whose header carries the source's mtime and size runs in place of the source, and __pycache__/ is
    git-ignored; review F claim 4), a module that removes itself from sys.modules (review H L1), or an edited copy of
    the scorer that removes these checks. These are examples, not a complete list. Tests that score a throwaway copy
    of the closure pass the project's root (the copy's files are byte copies, checked byte for byte by
    score_prereg.check; the hash and commit checks then read the copy)."""
    root = Path(modules_root if modules_root is not None else repo).resolve()
    main = getattr(sys.modules.get("__main__"), "__file__", None)
    if main is not None and Path(main).name == Path(SCORER).name and Path(main).resolve() != root / SCORER:
        raise PreregError(f"the scorer runs from {main}, not {root / SCORER}")
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for hook in ("sitecustomize", "usercustomize"):
        module = sys.modules.get(hook)
        if module is None:
            continue
        origin = getattr(getattr(module, "__spec__", None), "origin", None)
        if origin is None or Path(origin).resolve().parent != stdlib:
            raise PreregError(f"a {hook} module is loaded from {origin}, not from the standard library ({stdlib}): "
                              "it runs before the scorer and can put another module in place")
    for rel in scorer_closure(repo):
        name = module_name(rel)
        module = importlib.import_module(name)
        for what, loaded in (("__file__", getattr(module, "__file__", None)),
                             ("__spec__.origin", getattr(getattr(module, "__spec__", None), "origin", None))):
            if loaded is None or Path(loaded).resolve() != root / rel:
                raise PreregError(f"the module {name} is loaded from {loaded} ({what}), not {root / rel}: a "
                                  "PYTHONPATH or sys.path entry, or code run before the scorer, puts another file "
                                  "in place")


def scorer_sha256(repo: Path = REPO) -> str:
    """SHA-256 of the lines "<path>\\t<sha256>" of scorer_closure()."""
    lines = [f"{name}\t{file_sha256(Path(repo) / name)}" for name in scorer_closure(repo)]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


# --- the files -----------------------------------------------------------------------------------------------------

def paths(prereg_id: str, directory: Path = PREREG_DIR) -> dict[str, Path]:
    return {ext: Path(directory) / f"{prereg_id}.{ext}" for ext in ("json", "md", "sha256")}


def result_paths(prereg_id: str, directory: Path = PREREG_DIR) -> list[Path]:
    return [Path(directory) / f"{prereg_id}.result.json", Path(directory) / f"{prereg_id}.sessions.csv"]


def canonical(spec: dict) -> str:
    return json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def write(spec: dict, rationale: str, directory: Path = PREREG_DIR) -> dict[str, str]:
    """Write <id>.json, <id>.md and <id>.sha256; refuses to overwrite (an amendment is a new id)."""
    files = paths(spec["id"], directory)
    if any(os.path.lexists(p) for p in files.values()):
        raise PreregError(f"{spec['id']}: files exist; an amendment is a new dated file that names the old hash")
    Path(directory).mkdir(parents=True, exist_ok=True)
    files["json"].write_text(canonical(spec), encoding="utf-8", newline="\n")
    files["md"].write_text(rationale, encoding="utf-8", newline="\n")
    sums = {ext: file_sha256(files[ext]) for ext in ("json", "md")}
    files["sha256"].write_text("".join(f"{sums[ext]}  {files[ext].name}\n" for ext in ("json", "md")),
                               encoding="utf-8", newline="\n")
    return {**sums, "sha256": file_sha256(files["sha256"])}


def load(prereg_id: str, repo: Path = REPO, is_committed=None) -> dict:
    """The spec of a frozen pre-registration in the repository's prereg folder; PreregError unless the hashes hold
    and every file is committed. `is_committed` replaces the git check (only tests/test_prereg_files.py, before the
    files can be committed, passes one)."""
    directory = prereg_dir(repo)
    files = paths(prereg_id, directory)
    is_committed = is_committed or (lambda path: committed(path, repo))
    for ext, path in files.items():
        if not path.is_file():
            raise PreregError(f"{prereg_id}: no {path.name}")
    expected = {}
    for line in files["sha256"].read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        expected[name] = digest
    for ext in ("json", "md"):
        if expected.get(files[ext].name) != file_sha256(files[ext]):
            raise PreregError(f"{prereg_id}: {files[ext].name} does not match {files['sha256'].name}")
    for path in files.values():
        if not is_committed(path):
            raise PreregError(f"{prereg_id}: {path.name} is not committed, or differs from the committed file")
    spec = json.loads(files["json"].read_text(encoding="utf-8"))
    if spec.get("id") != prereg_id:
        raise PreregError(f"{prereg_id}: the file's id is {spec.get('id')!r}")
    return spec


def prereg_hash(prereg_id: str, directory: Path = PREREG_DIR) -> str:
    """The SHA-256 of the .sha256 file: one hash for the pre-registration (an amendment names it)."""
    return file_sha256(paths(prereg_id, directory)["sha256"])


# --- the ledgers ---------------------------------------------------------------------------------------------------

def parse_lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def read_lines(path: Path) -> list[dict]:
    if not Path(path).is_file():
        return []
    return parse_lines(Path(path).read_text(encoding="utf-8"))


def append_line(path: Path, entry: dict) -> None:
    """Append one JSON line and fsync the file; when this call creates the file, fsync its folder too, so the new
    name is as durable as the line (fix pass 3, item D7). The folder is the resolved path's: for a symlinked ledger,
    the folder where the file is created, not the link's (fix pass 4, item F7)."""
    path = Path(path)
    created = not path.exists()
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    if created:
        fd = os.open(path.resolve().parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def overlaps(a: dict, b: dict) -> bool:
    """Two windows {start, end} (ISO dates) share a date, whatever their split labels."""
    return a["start"] <= b["end"] and b["start"] <= a["end"]


def common_dir(repo: Path = REPO) -> Path:
    """The repository's git common directory (`git rev-parse --git-common-dir`; shared by its worktrees), where the
    side ledgers and the lock live: a stash, checkout, clean, reset or branch switch never touches it."""
    out = git(repo, "rev-parse", "--git-common-dir")
    if out.returncode != 0:
        raise PreregError(f"git cannot name the common directory of {repo}: {out.stderr.decode().strip()}")
    path = Path(out.stdout.decode().strip())
    return path if path.is_absolute() else Path(repo) / path


def require_full_history(repo: Path = REPO) -> None:
    """PreregError for a shallow repository: its history can hide a spent line (review B, A8)."""
    out = git(repo, "rev-parse", "--is-shallow-repository")
    if out.returncode != 0 or out.stdout.decode().strip() != "false":
        raise PreregError(f"{repo} is a shallow repository (or git cannot tell): its history may hide a spent "
                          "window; use a full clone")


def history_lines(rel: str, repo: Path = REPO) -> list[dict]:
    """The lines of every version of the file `rel` that git can reach: in the index and in every commit reachable
    from a ref or a reflog entry (`git rev-list --all --reflog`: every branch and tag, the stash and its reflog, the
    commits a reset, an amend or a branch switch left behind). A line a later commit removed still counts."""
    require_full_history(repo)
    commits = git(repo, "rev-list", "--all", "--reflog")
    if commits.returncode != 0:
        raise PreregError(f"git cannot list the commits of {repo}: {commits.stderr.decode().strip()}")
    names = [f":{rel}"] + [f"{commit}:{rel}" for commit in commits.stdout.decode().split()]
    out = git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype)", stdin="".join(n + "\n" for n in names))
    if out.returncode != 0:
        raise PreregError(f"git cannot look up the versions of {rel}: {out.stderr.decode().strip()}")
    blobs = []
    for line in out.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "blob" and parts[0] not in blobs:
            blobs.append(parts[0])
    entries = []
    for blob in blobs:
        out = git(repo, "cat-file", "blob", blob)
        if out.returncode != 0:
            raise PreregError(f"git cannot read {rel} at blob {blob}")
        entries += parse_lines(out.stdout.decode("utf-8"))
    return entries


def ledger_lines(name: str, side: str, repo: Path = REPO) -> list[dict]:
    """Every line of a ledger, each distinct line once, in this order: the working file, its side ledger in the git
    common directory, then every version of the file in git (history_lines)."""
    seen, out = set(), []
    for entry in (read_lines(prereg_dir(repo) / name) + read_lines(common_dir(repo) / side)
                  + history_lines(f"{PREREG_REL}/{name}", repo)):
        key = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            out.append(entry)
    return out


def append_both(name: str, side: str, entry: dict, repo: Path = REPO) -> None:
    """Append a line to the side ledger in the git common directory, then to the working file."""
    append_line(common_dir(repo) / side, entry)
    append_line(prereg_dir(repo) / name, entry)


class ledger_lock:
    """The ledgers' lock: a file in the git common directory created with O_EXCL. Whoever holds it reads the ledgers
    and appends to them; another process waits up to `wait_s` seconds, then refuses (a crashed holder leaves the file:
    check the ledgers, then delete it by hand)."""

    def __init__(self, repo: Path = REPO, wait_s: float = LOCK_WAIT_S) -> None:
        self.path, self.wait_s = common_dir(repo) / LOCK, wait_s

    def __enter__(self) -> "ledger_lock":
        deadline = time.monotonic() + self.wait_s
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise PreregError(f"{self.path} exists: another scoring or run gate holds the ledgers' lock "
                                      "(if no process does, one crashed: check the ledgers, then delete the file)")
                time.sleep(0.05)
        try:
            os.write(fd, f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n".encode())
        finally:
            os.close(fd)
        return self

    def __exit__(self, *exc) -> None:
        os.unlink(self.path)


def spent_lines(repo: Path = REPO) -> list[dict]:
    """The lines of spent.jsonl that spend a window, from the working file, the side ledger and git (ledger_lines)."""
    return [entry for entry in ledger_lines(SPENT, SIDE_SPENT, repo) if "window" in entry]


def spent_by(window: dict, repo: Path = REPO) -> dict | None:
    """The spent line whose window shares a date with `window` (spent_lines), or None."""
    for entry in spent_lines(repo):
        if overlaps(window, entry["window"]):
            return entry
    return None


def legacy_kind(line: dict) -> str | None:
    """The diagnostic_kind of a record: its own (every line the gate writes since fix pass 3 has the key), or for a
    diagnostic line without the key, LEGACY_KIND_RULE (the nine lines of the M4 smoke and budget runs; fix pass 3,
    item D6); None for a trial."""
    if line.get("run_purpose") != "diagnostic" or "diagnostic_kind" in line:
        return line.get("diagnostic_kind")
    return "budget" if line["start"] <= DEVELOPMENT_END.isoformat() else "smoke"


def runs_of_record(repo: Path = REPO) -> list[dict]:
    """The runs past 2019, one dict per run, from the working runs_of_record.jsonl, its side ledger and git
    (ledger_lines): a "started" line, merged with its "completed" line (same record_id) when the run finished, with
    "completed" True or False. A line with no "event" (the nine written before fix pass 2, by the M4 smoke and budget
    runs) is a run that started and completed; a "completed" line whose "started" line is lost counts on its own.
    Each run carries its "diagnostic_kind" (legacy_kind: a diagnostic written before fix pass 3 by LEGACY_KIND_RULE).

    The nine legacy lines count toward no current limit (fix pass 4, review E claim 4): their trial_hash was computed
    by the formula before fix pass 2 (with the split's data source and execution mode inside it), which no current
    configuration gives, and they have no data_source or execution_mode. They were the M4 smoke and budget runs, whose
    output was the engine's health only, and whose ledgers the smoke tool deleted; they are kept on the record as
    they are, not rewritten to the current formula."""
    lines = ledger_lines(RECORDS, SIDE_RECORDS, repo)
    out, by_id = [], {}
    for line in lines:
        if line.get("event") is None:
            out.append({**line, "completed": True})
        elif line["event"] == "started":
            by_id[line["record_id"]] = run = {**line, "completed": False}
            out.append(run)
    for line in lines:
        if line.get("event") == "completed":
            run = by_id.get(line["record_id"])
            if run is None:
                by_id[line["record_id"]] = run = {**line}
                out.append(run)
            run.update(run_id=line["run_id"], config_hash=line["config_hash"], completed=True)
    for run in out:
        run["diagnostic_kind"] = legacy_kind(run)
    return out


# --- the run gate --------------------------------------------------------------------------------------------------

def listed_trial_hashes(repo: Path = REPO) -> set[str]:
    """The trial_hash of every candidate and benchmark of every pre-registration in the repository's prereg folder
    (each <id>.json but a scorer's <id>.result.json; fix pass 4, item F6d). PreregError for a file that is not a JSON
    object: an unreadable pre-registration could list anything."""
    out = set()
    for path in sorted(prereg_dir(repo).glob("*.json")):
        if path.name.endswith(".result.json"):
            continue
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PreregError(f"{path.name} cannot be read as a pre-registration: {error}") from error
        if not isinstance(spec, dict):
            raise PreregError(f"{path.name} is not a pre-registration (not a JSON object)")
        for entry in [*(spec.get("candidates") or []), spec.get("benchmark") or {}]:
            if isinstance(entry, dict) and entry.get("trial_hash"):
                out.add(entry["trial_hash"])
    return out


def make_run_gate(repo: Path = REPO, rerun_reason: str | None = None, rerun_of: str | None = None,
                  today: date | None = None):
    """The run_gate for run_backtest: gate(cfg, strategy, trial_hash) raises to refuse a run, and returns None or a
    recorder, record(run_id, config_hash), that run_backtest calls once the run's folder is in place.

    - A run that ends by 2019-12-31 passes, unrecorded.
    - Every run past 2019, trial or diagnostic: refused when a spent window shares a date after 2019-12-31 with its
      own (fix pass 6, item H5; revised after the sixth review: the run's development dates are free (ADR-0010), so a
      scored forecast window, 2010-01-04 to 2019-11-29, does not refuse the budget run, 2010-01-04 to 2023-12-29, or
      its re-runs; the scorer's own spent check still compares whole windows). Otherwise
      the gate reserves before anything is read: under the ledgers' lock it appends a "started" line {event,
      record_id, date, trial_hash, prereg_id, split, run_purpose, diagnostic_kind, data_source, execution_mode, start,
      end, rerun_of, rerun_reason} to the side ledger in the git common directory and to runs_of_record.jsonl; the
      recorder appends the "completed" line (the same fields and run_id, config_hash) after the rename. A run
      interrupted in between, or whose recorder fails, keeps its "started" line, and a started run counts toward
      every limit below (fix pass 2, review B claim 3).
    - A trial past 2019 must also lie within its split's dates (volbt.view.SPLITS; fix pass 7, item I6, review H
      claim 4: a holdout trial whose pre-registered "holdout" window held validation dates was accepted), and name a
      pre-registration that loads (hashes hold, files committed) and has a window with the run's split, start and
      end, listing the run's trial_hash among its candidates or benchmark; on the
      holdout, find a completed validation trial of its trial_hash (ADR-0010 test 4b) and no holdout run of it,
      started or completed (the holdout runs once per frozen configuration; default taken 2026-11-09, owner can
      override); on validation, be the run of record or one of its two re-runs (ADR-0010 test 8: a fourth
      validation trial, the third re-run, is refused), a re-run with a reason.
    - A diagnostic past 2019 must name its diagnostic_kind (RunConfig.diagnostic_kind: ADR-0010 §1's volume cap and
      ADR-0009 §4's runs S, M and M', or plan section 6's smoke and budget runs; RunConfig checks the kind fits the
      config), and the volume cap runs as "volume_cap" and only it. A smoke or budget diagnostic of a trial_hash that
      a pre-registration in the prereg folder lists among its candidates or benchmark is refused (fix pass 4, item
      F6d). The two classes of diagnostic are counted apart (fix pass 5, item G1; review F claim 5), each as the run
      and two re-runs, started or completed, a re-run with a reason (fix pass 3, item D6), the fourth refused:
        - ADR diagnostics (volume_cap, surface_s, masked_m, masked_m_prime): per trial_hash and kind, whatever the
          data source and execution mode;
        - health runs (HEALTH_KINDS: smoke, budget): per trial_hash, kind, data source and execution mode, and only
          on the pairs of HEALTH_PAIRS, the ones tools/smoke_m4.py runs: (optionsdx, quote) and (dolthub, surface)
          for the smoke, (optionsdx, quote) for the budget run; a health run on another pair is refused (fix pass 6,
          item H4; review G claim 1).
      Neither class counts toward the other's limit. So a structure's smoke on both sources and its budget run, which
      share the trial_hash of a grid configuration, leave that configuration's ADR-0009 §4 run S its own three, and a
      smoke that crashed can be run again with a reason (default taken 2026-11-10, owner can override).
    The most runs of one trial_hash on validation dates (fix pass 6, item H4; measured on a made-up repository by
    tests/test_prereg.py::test_one_configuration_runs_at_most_15_times_on_validation_dates) are 15: 3 validation
    trials, 3 runs S, 6 smoke runs (2 pairs) and 3 budget runs (1 pair), the health runs made before a
    pre-registration lists the configuration. The volume cap adds 3 under its own trial_hash (cap_mode enters it).
    Runs M and M' add 3 each once built (RunConfig refuses them today; chain_mask enters the trial_hash, so each
    counts under its own). A holdout trial runs on holdout dates: the gate refuses a trial whose dates lie outside
    its split (fix pass 7, item I6). Re-measured in fix pass 7 with review H's holdout trial on validation dates added
    to the test: refused, and the maximum stays 15.
    The trial_hash (volbt.engine.run_config.trial_hash) leaves out the split, the dates, run_purpose, prereg_id,
    diagnostic_kind, the data source, the execution mode (both set by the split for a trial) and the trial_group (a
    label; fix pass 4, item F6a), so a configuration's validation run and its holdout run share it. RunConfig refuses a
    seed other than 0 for a trial or a named diagnostic past 2019, every run this gate accepts there (no code draws
    from the seed; fix pass 4, item F6b).

    Trust boundary (fix pass 4, item F6f). The limits count per trial_hash. A change to any field that defines a
    configuration is a new trial_hash, so the limits bind an honest workflow and every run past 2019 stays on the
    record; they are not a barrier against deliberate changes (a parameter changed only to get a new trial_hash runs,
    and is recorded as the new configuration it is). Some fields enter the hash without acting on the run (fix pass 5,
    item G1; review F claim 5): hedge_band_pct_nav under time hedging, and participation_rate under the hard_only cap,
    change nothing in the run but give a new trial_hash, so a smoke of a listed configuration with one of them changed
    passes the listed-configuration refusal. Such a run is on the record as the configuration it names. The gate's
    records are as strong as the ledgers' (module docstring): a clone whose refs do not reach a commit holding a
    holdout run's started line can run the holdout again. It is also only as strong as the caller: the engine runs
    whatever gate it is handed, so a tool that passes a gate that refuses nothing defeats all of this (review B's B5;
    tools/run_backtest.py and tools/smoke_m4.py pass this one, tested).
    """
    def gate(cfg, strategy, trial_hash: str):
        if cfg.sample_end <= DEVELOPMENT_END:
            return None
        kind = getattr(cfg, "diagnostic_kind", None)
        if cfg.run_purpose == "diagnostic":
            if kind is None:
                raise PreregError("a diagnostic past 2019 names its diagnostic_kind: the volume cap or a masked run "
                                  "of ADR-0010 §1, or the smoke or budget run of plan section 6")
            if (cfg.cap_mode == "volume") != (kind == "volume_cap"):
                raise PreregError(f"the volume cap runs as diagnostic_kind 'volume_cap', and only it (cap_mode "
                                  f"{cfg.cap_mode!r}, diagnostic_kind {kind!r})")
        mine = {"split": cfg.split, "start": cfg.sample_start.isoformat(), "end": cfg.sample_end.isoformat()}
        # fix pass 6, item H5: only the run's dates after 2019-12-31 meet the spent windows; development dates are free
        after = {**mine, "start": max(mine["start"], (DEVELOPMENT_END + timedelta(days=1)).isoformat())}
        day = (today or datetime.now(timezone.utc).date()).isoformat()
        with ledger_lock(repo):
            spent = spent_by(after, repo)
            if spent is not None:
                raise PreregError(f"the window {mine} shares dates after {DEVELOPMENT_END} with one spent by "
                                  f"{spent['prereg_id']} on {spent['date']}: after scoring, a fail is final")
            if cfg.run_purpose == "trial":
                check_trial(cfg, trial_hash, mine)
            else:
                check_diagnostic(cfg, kind, trial_hash)
            started = {"event": "started", "record_id": uuid.uuid4().hex, "date": day, "trial_hash": trial_hash,
                       "prereg_id": cfg.prereg_id, "split": cfg.split, "run_purpose": cfg.run_purpose,
                       "diagnostic_kind": kind, "data_source": cfg.data_source,
                       "execution_mode": cfg.execution_mode, "start": mine["start"], "end": mine["end"],
                       "rerun_of": rerun_of, "rerun_reason": rerun_reason}
            append_both(RECORDS, SIDE_RECORDS, started, repo)

        def record(run_id: str, config_hash: str) -> dict:
            entry = {**started, "event": "completed", "run_id": run_id, "config_hash": config_hash,
                     "date": (today or datetime.now(timezone.utc).date()).isoformat()}
            with ledger_lock(repo):
                append_both(RECORDS, SIDE_RECORDS, entry, repo)
            return entry

        return record

    def check_diagnostic(cfg, kind: str, trial_hash: str) -> None:
        if kind in UNLISTED_ONLY_KINDS and trial_hash in listed_trial_hashes(repo):
            raise PreregError(f"{trial_hash} is listed by a pre-registration: a {kind} diagnostic of it is refused "
                              "(it would run a listed configuration on validation data outside its run of record)")
        # fix pass 5, item G1: a health run counts per kind, source and mode; an ADR diagnostic per kind
        same = [r for r in runs_of_record(repo) if r.get("run_purpose") == "diagnostic"
                and r.get("trial_hash") == trial_hash and r.get("diagnostic_kind") == kind]
        if kind in HEALTH_KINDS:
            if (cfg.data_source, cfg.execution_mode) not in HEALTH_PAIRS[kind]:
                raise PreregError(f"a {kind} run on {cfg.data_source} {cfg.execution_mode} is refused: no tool runs "
                                  f"one (the {kind} runs on {' and '.join(' '.join(p) for p in HEALTH_PAIRS[kind])})")
            same = [r for r in same if r.get("data_source") == cfg.data_source
                    and r.get("execution_mode") == cfg.execution_mode]
            what = f"the {kind} run on {cfg.data_source} {cfg.execution_mode}"
        else:
            what = f"the {kind} diagnostic"
        if len(same) >= MAX_VALIDATION_RUNS:
            raise PreregError(f"{trial_hash}: a third re-run of {what} is refused (the run and two re-runs, started or "
                              "completed)")
        if same and not rerun_reason:
            raise PreregError(f"{trial_hash}: a re-run of {what} needs a reason (rerun_reason)")

    def check_trial(cfg, trial_hash: str, mine: dict) -> None:
        from volbt.view import SPLITS

        if not cfg.prereg_id:
            raise PreregError("a trial past 2019 needs a prereg_id")
        first, last = SPLITS[cfg.split]
        if cfg.sample_start < first or cfg.sample_end > last:
            # fix pass 7, item I6 (review H claim 4): a holdout trial on validation dates was accepted
            raise PreregError(f"a {cfg.split} trial runs on {cfg.split} dates ({first} to {last}), not on "
                              f"{mine['start']} to {mine['end']}")
        spec = load(cfg.prereg_id, repo)
        if not [w for w in spec.get("windows", []) if {k: w.get(k) for k in mine} == mine]:
            raise PreregError(f"{cfg.prereg_id} has no window {mine}")
        listed = {c.get("trial_hash") for c in [*spec.get("candidates", []), spec.get("benchmark") or {}]}
        if trial_hash not in listed:
            raise PreregError(f"trial_hash {trial_hash} is unlisted in {cfg.prereg_id}")
        runs = [r for r in runs_of_record(repo)
                if r.get("trial_hash") == trial_hash and r.get("run_purpose") == "trial"]
        if cfg.split == "holdout":
            if not any(r["split"] == "validation" and r["completed"] for r in runs):
                raise PreregError(f"a holdout run of {trial_hash} needs its completed validation run of record "
                                  "first (ADR-0010 test 4b)")
            if any(r["split"] == "holdout" for r in runs):
                raise PreregError(f"{trial_hash} has had its holdout run (started or completed)")
        elif cfg.split == "validation":
            earlier = sum(r["split"] == "validation" for r in runs)
            if earlier >= MAX_VALIDATION_RUNS:
                raise PreregError(f"{trial_hash}: a third validation re-run is refused (the run of record and two "
                                  "re-runs, started or completed; ADR-0010 test 8)")
            if earlier and not rerun_reason:
                raise PreregError(f"{trial_hash}: a validation re-run needs a reason (rerun_reason)")

    return gate


# --- the forecast test's pre-registration (task 8; revised in the fix pass) -----------------------------------------

FORECAST_ID = "2026-11-09-forecast-har-vs-naive"
CALIBRATION_FIRST, CALIBRATION_LAST_TARGET = date(2002, 1, 2), date(2009, 12, 31)
CALIBRATION_LABEL = "pre-development (2002-2009)"
WINDOW_START, WINDOW_LAST_TARGET = date(2010, 1, 4), DEVELOPMENT_END
TEST_SEED, DRAWS, EWC_Q, BOOT_BLOCK, LEVEL = 20261109, 9_999, 4, 21, 0.95
NOMINAL = 0.05               # the battery's nominal level; the decision uses the matched threshold
INFERENCE, SIZE_SCRIPT = "src/volbt/analytics/inference.py", "tools/forecast_size.py"
ACF_LAGS = 63
FIRST_REVISION_POWER_FLOOR = 0.9    # the first revision's rule: power of at least 0.9 at falsifier (c)
# How p < 0.025 was reached (fix pass 3, review D claim 1). Review A's figures were re-measured on 2026-11-10 by
# running its saved analysis scripts on its saved simulations (no new simulation): seed 6001 gave 0.0529 and seed
# 7001 gave 0.0512, each from 1,000 runs per matched null-side of review A's own match (300 paths per null).
THRESHOLD_HISTORY = {
    "named_by": "review A, the second review of milestone 4 part A, before the matched rule was coded",
    "threshold": 0.025,
    "review_a_abc_size": [{"seed": 6001, "rate": 0.0529, "runs_per_null_side": 1000},
                          {"seed": 7001, "rate": 0.0512, "runs_per_null_side": 1000}],
    "size_cap": 0.055,
    "note": "the second fix pass's item list opened with \"Decision threshold p < 0.025\" and quoted review A's "
            "ABC-weighted sizes at 0.025; the rule (tools/forecast_size.py match) was coded after that, and its "
            "size cap 0.055 (the level plus 10%) was set with those sizes in view. The rule picks 0.025 on this "
            "battery; with the cap at 0.05 it picks 0.02 (the variant table)"}
# Review D's run of the conditional check (the third review; its seed was not recorded): its figures at p < 0.025,
# re-measured on 2026-11-10 by running its saved analysis script on its saved simulations (3,000 paths per null); the
# output was identical to review D's. Typed here: it is not reproducible from this repository.
CONDITIONAL_THIRD_REVIEW = {
    "threshold": 0.025, "paths_per_null": 3000,
    "by_accept": [{"accept": 0.0025, "accepted_paths": 0.0511, "se": 0.0104, "side_average": 0.0465},
                  {"accept": 0.005, "accepted_paths": 0.0511, "se": 0.0073, "side_average": 0.0473},
                  {"accept": 0.01, "accepted_paths": 0.0556, "se": 0.0054, "side_average": 0.0481},
                  {"accept": 0.02, "accepted_paths": 0.0481, "se": 0.0036, "side_average": 0.0477},
                  {"accept": 0.05, "accepted_paths": 0.0497, "se": 0.0023, "side_average": 0.0459}],
    "note": "review D's draw (the third review), re-analysed from its saved simulation with identical output; seed "
            "not recorded; not reproducible from this repository; printed to 4 decimals"}
# The tools/forecast_size.py scripts that ran the simulations before fix pass 5: fix pass 3's ran the battery, the
# match, the variants and the 3,000-path conditional draw; fix pass 4's ran the combinations and the 10,000-path draw.
# Fix pass 5 (item G3, review F claim 2) ran every one of them again with the current script, so every output the
# .json carries names the current script's file SHA-256; no AST hash links the earlier runs to it any more.
SIZE_SCRIPTS_EARLIER = {
    "fix_pass_3": "b243edc2d8cf863c40247fba7ab77e8ff81d86d2a7bdcb06a3567b0c880bf385",
    "fix_pass_4": "2a7d70e793e20f300a4d6ec13340f16c5ae889a0b3aac4d6e0972bb91987c5d4"}


def store_tables(store) -> dict[str, str]:
    return {name: file_sha256(store.checked_table_file(name)) for name in ("spy_bars", "dividends")}


def measure_dependence(store) -> dict:
    """The dependence summary of the 2002-2009 d-series (labelled "pre-development"; the reads use the development
    split's view, whose bound is 2019-12-31): its ACF to lag 63, the moving-block SE swept over {21, 42, 84, 168}
    (analytics.inference.block_sweep), its centred moments (skewness, excess kurtosis) and the twelve centred
    summaries the size battery's nulls are matched on (analytics.inference.dependence_summaries, 6 significant
    digits; fix pass 2, item 9). Nothing that reveals the mean of d or its sign is returned, printed or kept."""
    import forecast_test as ft
    import numpy as np
    from volbt.analytics.inference import acf, block_sweep, dependence_summaries

    days = ft.block_window(store, CALIBRATION_FIRST, CALIBRATION_LAST_TARGET)
    series = ft.paired(ft.forecasts(store, days), ft.realised(store, days))
    d = series.pop("d")
    series.clear()
    sweep = block_sweep(d)
    rho = acf(d, ACF_LAGS)
    z = (d - d.mean()) / d.std()
    summaries = dependence_summaries(d)
    del d
    return {"window": {"label": CALIBRATION_LABEL, "start": days[0].isoformat(), "end": days[-1].isoformat(),
                       "last_target_end": CALIBRATION_LAST_TARGET.isoformat(), "n": len(days),
                       "dates_sha256": dates_sha256(days)},
            "acf": [round(float(x), 4) for x in rho],
            "se": {str(b): float(f"{se:.6g}") for b, se in sweep["se"].items()},
            "ratios": {str(b): round(r, 4) for b, r in sweep["ratios"].items()},
            "sweep_block": sweep["block"], "sweep_converged": sweep["converged"], "sweep_rule": sweep["rule"],
            "skewness": round(float(np.mean(z ** 3)), 3), "excess_kurtosis": round(float(np.mean(z ** 4) - 3), 3),
            "summaries": {key: float(f"{value:.6g}") for key, value in summaries.items()}}


def key(threshold: float) -> str:
    """A threshold as the battery's and the match's JSON keys name it ("0.05", "0.025")."""
    return str(threshold)


def size_section(size: dict, threshold: float) -> dict:
    """The pre-registration's "size": tools/forecast_size.py battery's output, every null on +d and -d at nominal
    0.05 and at the registered threshold, and every threshold's worst sizes and power (fix pass 2, items 9 and 13)."""
    t, by = key(threshold), size["by_threshold"]
    rates05, rates_t = by[key(NOMINAL)]["rates"], by[t]["rates"]
    nulls = [name for name in rates05 if not name.startswith("power")]       # the power cells are not nulls
    band = size["band"]
    return {"script": "tools/forecast_size.py battery", "script_sha256": size["script_sha256"],
            "inference_sha256": size["inference_sha256"], "battery_sha256": size["sha256"], "runs": size["runs"],
            "T": size["T"], "simulated_test": size["test"], "simulated_q": size["q"], "simulated_block": size["block"],
            "simulated_draws": size["draws"], "power_rho": size["power_rho"], "data_seed": size["data_seed"],
            "bootstrap_seed": size["bootstrap_seed"], "band": band, "mc_se_at_0.05": size["mc_se_at_0.05"],
            "requirement": f"rejection rate in [{band[0]}, {band[1]}] at nominal {NOMINAL} on every null, on +d "
                           "and on -d",
            "met": by[key(NOMINAL)]["in_band"] == f"{2 * len(nulls)}/{2 * len(nulls)}",
            "threshold": threshold, "worst": by[t]["worst"], "in_band": by[t]["in_band"],
            "worst_at_0.05": by[key(NOMINAL)]["worst"], "in_band_at_0.05": by[key(NOMINAL)]["in_band"],
            "nulls": [{"name": name, "plus_d": rates_t[name][0], "minus_d": rates_t[name][1],
                       "plus_d_at_0.05": rates05[name][0], "minus_d_at_0.05": rates05[name][1]} for name in nulls],
            "by_threshold": by,
            "power_note": f"unit-variance Gaussian AR(1), rho {size['power_rho']}, mean delta "
                          "sqrt((1 + rho)/(1 - rho)/T): a long-run t of delta; delta = 4 is falsifier (c) of "
                          "tests/test_inference.py"}


def size_inputs_checks(dependence: dict, size: dict, match: dict, variants: dict, conditional: dict,
                       earlier: dict, combinations: dict) -> dict:
    """Each check the size inputs must pass before they are frozen: every output names the battery, the match, the
    script and the inference module it ran, and the real d's summaries it was matched on (fix pass 3: the variants
    and the conditional check too). Fix pass 5 (item G3): every output ran the current tools/forecast_size.py, by its
    file SHA-256; the combinations reproduce the match's weights and the variants' picks, and count every combination
    and every distinct rule."""
    inference, script = file_sha256(REPO / INFERENCE), file_sha256(REPO / SIZE_SCRIPT)
    threshold = match["threshold"]
    registered = next((v for v in variants["variants"] if v["name"] == "registered"), None)
    row = next((r for r in match["table"] if r["threshold"] == threshold), None)
    runs = (size, match, variants, earlier, conditional, combinations)
    return {
        "the match ran on this battery": match["battery_sha256"] == size["sha256"],
        "the match's real-d summaries are the calibration window's": match["real"] == dependence["summaries"],
        "every output ran this inference module": all(r["inference_sha256"] == inference for r in runs),
        "every output ran the current script (fix pass 5, item G3)": all(r["script_sha256"] == script for r in runs),
        "the threshold is one the battery measured": key(threshold) in size["by_threshold"],
        "the variants ran on this battery and match": variants["battery_sha256"] == size["sha256"]
            and variants["match_sha256"] == match["sha256"],
        "the combinations ran on this battery, match and variants": combinations["battery_sha256"] == size["sha256"]
            and combinations["match_sha256"] == match["sha256"] and combinations["variants_sha256"] == variants["sha256"],
        "the variants, the combinations and both conditional draws used the calibration window's summaries":
            variants["real"] == conditional["real"] == earlier["real"] == combinations["real"]
            == dependence["summaries"]
            and conditional["n_calibration"] == earlier["n_calibration"] == dependence["window"]["n"],
        "both conditional draws ran the battery's test": (conditional["T"], conditional["draws"])
            == (earlier["T"], earlier["draws"]) == (size["T"], size["draws"]),
        "the main conditional draw is larger than the earlier one and on another seed":
            conditional["paths_per_null"] > earlier["paths_per_null"] and conditional["seed"] != earlier["seed"],
        "the variants reproduce the match": all(variants["reproduction"][k] == 0
                                                for k in ("weights", "second_seed_size", "power")),
        "the combinations reproduce the match's weights and the variants' picks":
            combinations["reproduction"]["weights"] == 0 and combinations["reproduction"]["one_at_a_time_mismatch"] == [],
        "the combinations count every combination and every distinct rule (fix pass 5, item G2)":
            all(sum(part["picks"].values()) == part["n"] for part in (
                combinations["one_at_a_time"], combinations["two_at_a_time"], combinations["two_at_a_time"]["distinct"],
                combinations["full_grid"], combinations["full_grid"]["distinct_rules"]))
            and combinations["full_grid"]["distinct_rules"]["n"] <= combinations["full_grid"]["n"],
        "the band covers every pick of the variants and the other summary seeds":
            all(combinations["band"][0] <= x <= combinations["band"][1] for x in
                [r["threshold"] for r in variants["variants"]] + [r["threshold"] for r in variants["summary_seeds"]["rows"]]
                if x is not None),
        "the registered variant is the match's rule": registered is not None and row is not None
            and registered["threshold"] == threshold and registered["sides"] == len(match["matched"])
            and abs(registered["size"]["battery"][key(threshold)] - row["abc_size_battery_seed"]) < 1e-12
            and abs(registered["size"]["second"][key(threshold)] - row["abc_size_second_seed"]) < 1e-12}


def spread(matched: list[dict], seed: str, threshold: float) -> dict:
    """The lowest and the highest size at `threshold` among the matched null-sides, on one seed's runs."""
    rates = sorted(((side[f"size_{seed}_seed"][key(threshold)], side["null_side"]) for side in matched))
    return {"lowest": {"rate": rates[0][0], "null_side": rates[0][1]},
            "highest": {"rate": rates[-1][0], "null_side": rates[-1][1]}}


def forecast_spec(store, dependence: dict, size: dict, match: dict, variants: dict, conditional: dict,
                  earlier: dict, combinations: dict) -> dict:
    import forecast_test as ft
    from volbt.data.store import session_calendar

    threshold = match["threshold"]
    checks = size_inputs_checks(dependence, size, match, variants, conditional, earlier, combinations)
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise PreregError(f"the size inputs disagree: {failed}")
    days = ft.window(session_calendar(store), WINDOW_START, WINDOW_LAST_TARGET)
    window = {"name": "forecast-2010-2019", "split": "development", "start": days[0].isoformat(),
              "end": days[-1].isoformat(), "last_target_end": WINDOW_LAST_TARGET.isoformat(), "n": len(days),
              "dates_sha256": dates_sha256(days)}
    row = next(r for r in match["table"] if r["threshold"] == threshold)
    sized = size_section(size, threshold)
    effective = {"threshold": threshold, "abc_size_battery_seed": row["abc_size_battery_seed"],
                 "abc_size_second_seed": row["abc_size_second_seed"],
                 "worst_matched_battery_seed": row["worst_matched_size_battery_seed"],
                 "worst_matched_second_seed": row["worst_matched_size_second_seed"],
                 "lowest_matched_battery_seed": spread(match["matched"], "battery", threshold)["lowest"],
                 "lowest_matched_second_seed": spread(match["matched"], "second", threshold)["lowest"],
                 "worst_battery": sized["worst"]["high"],
                 "note": "the rejection rate of p < threshold on mean-0 nulls: ABC-weighted over the null-sides "
                         "nearest the 2002-2009 d-series in its twelve centred summaries (matched), and the "
                         "lowest and the worst matched and the worst battery null-side; a rejection is evidence at "
                         "this size, not at a nominal 0.05. Nearest in those summaries is not alike in what drives "
                         "size: the matched null-sides' sizes spread from the lowest to the worst"}
    return {
        "id": FORECAST_ID, "date": "2026-11-09", "kind": "forecast_test", "amends": None,
        "revised": ["2026-11-09, before any commit or scoring, after the milestone 4 part A review: the block sign "
                    "flip at block 168 was replaced (the screen in the .md and the .json has its sizes)",
                    f"2026-11-09, before any commit or scoring, after the second review: review A named p < "
                    f"{threshold:g} first, and the rule, coded after it, picks it on the null-sides nearest the "
                    "2002-2009 d-series (matched; threshold_history); every figure comes from tools/forecast_size.py's "
                    "saved output, the spend survives git",
                    "2026-11-10, before any commit or scoring, after the third review: disclosed that review A named "
                    "p < 0.025 before the rule was coded and that the size cap was set with its sizes in view "
                    "(threshold_history); listed the move of the power requirement from falsifier (c) power (the "
                    "first revision) to the ABC-weighted power on the matched null-sides (the second); added the "
                    "variant table (variants), the conditional check (conditional) and the spread of size across "
                    "the matched null-sides; the threshold is not re-chosen",
                    "2026-11-10, before any commit or scoring, after the fourth review: the threshold's fragility is "
                    "stated from every combination of the variant table's choices and two power-requirement rows "
                    "(combinations; the band in fragile_band, which the scorer's result carries); a declared "
                    "10,000-path conditional draw is the main conditional figure and the two 3,000-path draws are "
                    "kept as earlier draws; the wording that implied the threshold was chosen blind is gone; the "
                    "threshold and the decision rule are not re-chosen",
                    "2026-11-10, before any commit or scoring, after the fifth review: the combinations are counted "
                    "by combination and by distinct rule (combinations.full_grid.distinct_rules, "
                    "combinations.two_at_a_time.distinct); the menu of thresholds and why the combinations that "
                    "pick none pick none (combinations.full_grid.none_at_lowest) are stated; the three conditional "
                    "draws are compared two at a time; the battery, the match, the variants, the combinations and "
                    "both conditional draws were run again with the final tools/forecast_size.py and gave the same "
                    "values (size_scripts); the .md states what the scorer's hash covers; the threshold and the "
                    "decision rule are not re-chosen",
                    "2026-11-10, before any commit or scoring, after the sixth review: the scorer refuses a tools/ "
                    "entry named after a module found on another sys.path entry and a tools/ entry that is not "
                    "committed as it is, and checks the modules loaded from tools/ again under the ledgers' lock "
                    "just before the spend (scorer_sha256 changes with its files); the .md states when the checks "
                    "run and what they do not stop, and names the six simulations the fifth revision ran again "
                    "(review D's draw was not run again); no simulation was run; the threshold and the decision "
                    "rule are not re-chosen",
                    "2026-11-10, before any commit or scoring, after the seventh review: run as a script, the scorer "
                    "refuses an entry of tools/ that takes the name of one of its modules (a tools/prereg/ package ran "
                    "in place of tools/prereg.py) or that shares a module name with another entry, before it imports "
                    "tools/prereg.py, and its checks of tools/ leave out entries an import statement cannot name "
                    "(scorer_sha256 changes with its files); the .md says the checks catch mistakes and the routes "
                    "they name, not code written to defeat them, names a module that removes itself from "
                    "sys.modules, and says to commit tools/ in full before scoring; no simulation was run; the "
                    "threshold and the decision rule are not re-chosen",
                    "2026-11-10, before any commit or scoring, after the eighth review: the scorer's checks of tools/ "
                    "read every folder and every file with an import suffix, by module name (a file's name less its "
                    "longest import suffix, a folder's name); they leave out an entry whose module name holds a dot "
                    "and tools/__pycache__ (Python's bytecode cache, which git ignores); a name with a "
                    "hyphen is read, and the name check runs before sysconfig imports its data module "
                    "(scorer_sha256 changes with its files); the .md states which entries the checks read; no "
                    "simulation was run; the threshold and the decision rule are not re-chosen",
                    "2026-11-10, before any commit or scoring, after the ninth review: the .md said that a folder in "
                    "tools/ must be committed as it is; it now says what the commit check reads: an entry of tools/ "
                    "(a file with an import suffix, or a folder) is refused when HEAD does not hold it as committed; "
                    "for a folder, HEAD must hold it as a folder and every file with an import suffix directly in it "
                    "must be committed as it is; files deeper down, and files without an import suffix, are not "
                    "checked; the scorer refuses _PYTHON_SYSCONFIGDATA_NAME, which names the module sysconfig "
                    "imports, as it refuses PYTHONPATH, PYTHONHOME and PYTHONUSERBASE, and the .md lists the four "
                    "(scorer_sha256 changes with its files); no simulation was run; the threshold and the decision "
                    "rule are not re-chosen"],
        "threshold_history": THRESHOLD_HISTORY,
        "claim": "At the 21-session horizon, the HAR-RV forecast (with its naive fallback) has a lower expected QLIKE "
                 "loss than the naive RV22 forecast.",
        "k": 1,
        "candidates": [{"name": "har", "trial_hash": None, "model": {
            "module": "volbt.signals.har", "v": "r_i^2, r_i = ln((C_i + D_i) / C_{i-1}) (volbt.signals.realised)",
            "regressors": "[1, v_i, mean v_{i-4..i}, mean v_{i-21..i}]", "target": "mean v_{i+1..i+21}",
            "fit": "OLS (numpy.linalg.lstsq, rcond=None) on the pairs whose target ends by the fit date, at least "
                   "504; refit on the first session of each calendar month",
            "fallback": "a forecast <= 0 or not finite is replaced by the naive one (RV_FALLBACK)"}}],
        "benchmark": {"name": "naive", "trial_hash": None, "model": {"forecast": "mean v_{t-21..t} (RV22)"}},
        "metric": {"name": "QLIKE", "formula": "y/yhat - ln(y/yhat) - 1", "y": "mean r^2 over the 21 sessions after t",
                   "proxy": True, "label": "proxy: realised variance from daily closes stands in for the true "
                                           "variance (Patton 2011: QLIKE ranks forecasts correctly under it)"},
        "paired_difference": {"d": "QLIKE(naive)_t - QLIKE(HAR)_t", "favours_candidate": "d > 0",
                              "sides": "one-sided", "null": "mean(d) <= 0", "alternative": "mean(d) > 0"},
        "pseudo_out_of_sample": "every forecast at t from the view of t only (tools/forecast_test.py)",
        "windows": [window],
        "calibration": {**dependence, "use": "centred summaries only (nothing that shows the mean of d or its "
                                             f"sign). The lag-1 ACF {dependence['acf'][1]:g} set the battery's AR(1) "
                                             "nulls and falsifier (c), on whose power the first revision chose "
                                             f"q = {EWC_Q} and the EWC bootstrap-t; the twelve summaries set the "
                                             "matched null-sides that check the threshold"},
        "test": {"function": "volbt.analytics.inference.ewc_bootstrap", "q": EWC_Q, "block": BOOT_BLOCK,
                 "draws": DRAWS, "seed": TEST_SEED, "level": LEVEL, "alternative": "greater",
                 "statistic": "the equal-weighted cosine t of mean(d) with q = 4 (Mueller 2007; Lazarus, Lewis, Stock "
                              "and Watson 2018)",
                 "p": "one-sided moving-block bootstrap-t: blocks of 21 sessions (the targets' overlap), resamples "
                      "centred at the mean of the block means, p = (1 + #{t* >= t}) / (1 + draws)",
                 "ci": "the bootstrap-t interval of mean(d) from the same draws",
                 "d_identically_0": "p = 1, decision naive (the null control of plan section 7)"},
        "size": sized,
        "screen": {"runs": size["runs"], "seeds": size["screen_seeds"], "candidates": size["screen"],
                   "order": list(size["screen"]),
                   "first_revision_rule": {"power_floor": FIRST_REVISION_POWER_FLOOR,
                                           "rule": "the smallest worst-case size at nominal 0.05 among the candidates "
                                                   "with power of at least power_floor at falsifier (c)"},
                   "note": f"every candidate on the battery's data (the same {size['runs']:,} paths per null-side), "
                           f"at nominal {NOMINAL}; power is the battery's AR(1) power cell"},
        "matched": {**match, "sha256": match["sha256"]},
        "variants": {**variants, "sha256": variants["sha256"],
                     "note": "the registered rule with one modelling choice changed at a time (tools/forecast_size.py "
                             "variants; the row \"drop spec4_20 and kurt\" drops two summaries at once): which "
                             "threshold each picks"},
        "combinations": {**combinations, "sha256": combinations["sha256"],
                         "note": "the registered rule on every combination of the variant table's choices, and two "
                                 "power-requirement rows (tools/forecast_size.py combinations, from the saved tables; "
                                 "no new test run): a p in [band[0], band[1]) is decided by these choices, not by "
                                 "the data"},
        "fragile_band": combinations["band"],
        "conditional": {**conditional, "sha256": conditional["sha256"],
                        "earlier": {"fix_pass_3": {**earlier, "sha256": earlier["sha256"]},
                                    "review_d": CONDITIONAL_THIRD_REVIEW},
                        "note": "the test's size on simulated paths whose calibration segment's summaries are nearest "
                                "the real d's (tools/forecast_size.py conditional): the main draw, declared before it "
                                "ran, and two earlier 3,000-path draws"},
        "size_scripts": {"current": file_sha256(REPO / SIZE_SCRIPT), "earlier": dict(SIZE_SCRIPTS_EARLIER),
                         "note": "fix pass 5 (item G3) ran the battery, the match, the variants, the combinations "
                                 "and both of fix pass 3's and fix pass 4's conditional draws again with the current "
                                 "script, at the same seeds and run counts: every value equals the earlier outputs' "
                                 "but the seconds, the script and the input-file hashes, and the counts fix pass 5 "
                                 "added. Every output above names the current script"},
        "threshold": threshold,
        "threshold_rule": match["rule"] + " (fix pass 2, item 9; default taken 2026-11-09, owner can override)",
        "effective_size": effective,
        "correction": {"method": "max-statistic", "cross_check": "Holm",
                       "note": "k = 1: both leave the one p-value as it is"},
        "psr_dsr": {"applies": False, "reason": "a forecast test has no return series; ADR-0010 §2's PSR/DSR "
                    "(per-period SR, N_raw and N_eff, dsr = min(dsr_raw, dsr_eff)) applies to M6's strategy tests"},
        "decision_rule": f"use HAR if p < threshold ({threshold}); otherwise use naive. One window, one shot: after "
                         "scoring, a fail is final",
        "scoring_command": f"uv run python tools/score_prereg.py {FORECAST_ID}",
        "scorer_sha256": scorer_sha256(), "scorer_files": scorer_closure(), "libraries": library_versions(),
        "data": store_tables(store),
    }


RATIONALE = """# Forecast test: HAR-RV against the naive RV22 ({id})

Pre-registered 2026-11-09 (milestone 4, plan section 6). Status: **written, not committed, not scored.** The plan
requires these three files to be committed before any scoring; no commit can be made until the history rewrite of
the repositories ends, so scoring waits for it.

## Revisions before commit
- First, after the milestone 4 part A review: the block sign flip (block 168) was replaced by an EWC bootstrap-t,
  chosen by the rule of the first revision: the smallest worst-case size among the candidates with power of at least
  {floor1} at falsifier (c) (the battery's Gaussian AR(1), a long-run t of 4).
- Second, after the second review: review A named p < {threshold} first (below), and the rule, coded after it, picks
  it on the simulated null-sides nearest the 2002-2009 d-series. Every figure below became the saved output of
  `tools/forecast_size.py` that the .json carries ("size", "screen", "matched"). The power requirement moved from the falsifier (c) power to the
  ABC-weighted power on the matched null-sides, shifted by {shift} SD of the run mean. At p < {threshold} the falsifier
  (c) power is {fc_t}, below the first revision's {floor1}; the ABC-weighted power is {abc_power}.
- How p < {threshold} was reached: review A, the second review, named p < {h_th} before the rule was coded. Its
  ABC-weighted sizes at p < {h_th} were {h_sizes}. The second fix pass's item list opened with "Decision threshold p <
  {h_th}". The rule's size cap, {h_cap}, was set with those sizes in view. With the cap at {cap05}, the rule picks p <
  {cap05_pick} (the table under "How fragile the threshold is").
- Third, after the third review: the threshold's history above, the variant table, the conditional check and the
  spread of size across the matched null-sides were added. The threshold was not chosen again.
- Fourth, after the fourth review: the threshold's fragility is stated from every combination of the variant table's
  choices and from two power-requirement rows; a larger conditional draw, declared before it ran, is the main
  conditional figure, and the two earlier draws are kept; wording that implied the threshold was chosen blind was
  removed. The threshold and the decision rule were not chosen again.
- Fifth, after the fifth review: the combinations are counted by combination and by distinct rule; the menu of
  thresholds, and why the combinations that pick none pick none, are stated; the three conditional draws are compared
  two at a time; six simulations were run again with the final `tools/forecast_size.py` and gave the same values:
  the battery, the match, the variants, the combinations, the main conditional draw and the third fix pass's draw.
  Review D's draw was not run again: its seed was not recorded. The text states what the scorer's hash covers. The
  threshold and the decision rule were not chosen again. (Corrected after the sixth review: this item said that
  every simulation was run again.)
- Sixth, after the sixth review: the scorer's checks of tools/ were widened, and the text states when they run and
  what they do not stop (under "The data looked at"); the fifth item now names the six simulations that were run
  again. No simulation was run, and the threshold and the decision rule were not chosen again.
- Seventh, after the seventh review: run as a script, the scorer refuses an entry of tools/ that takes the name of
  one of its modules, or that shares a module name with another entry, before it imports tools/prereg.py. Its checks
  of tools/ left out entries whose module name was not an identifier (the eighth revision replaced this rule). The
  text under "The data looked at" now says the checks catch mistakes and the routes they name, not code written to
  defeat them, and names a module that removes itself. The scoring steps say to commit tools/ in full. No simulation
  was run, and the threshold and the decision rule were not chosen again.
- Eighth, after the eighth review: the checks of tools/ now read an entry whose module name has a hyphen, and leave
  out an entry whose module name holds a dot. A file's module name is its name less the longest import suffix. The
  scorer's name check now runs before sysconfig imports its data module. The text under "The data looked at" and
  the scoring steps state which entries the checks read, and that tools/__pycache__ is left out. No simulation was
  run, and the threshold and the decision rule were not chosen again.
- Ninth, after the ninth review: the text said that a folder in tools/ must be committed as it is, but the commit
  check reads less. The scoring steps and the text under "The data looked at" now say what it reads. For a folder,
  HEAD must hold it as a folder, and every file with an import suffix directly in it must be committed as it is. The
  commit check does not read files deeper down, or files without an import suffix. The scorer now also refuses
  _PYTHON_SYSCONFIGDATA_NAME, which names the module sysconfig imports, and the text lists the variables it refuses.
  No simulation was run, and the threshold and the decision rule were not chosen again.

## Why this test
ADR-0010 asks for an out-of-sample test of the 21-day HAR before the signal uses it. The signal's RV model (design
choice 9 of the log) is the one thing this test decides: HAR if the test rejects, else naive.

## What is fixed here
- One candidate (k = 1), one benchmark, one window: {start} to {end}, n = {n}, every target ending by {last}.
  The window is development data; it has been looked at for other reasons (M3's engine runs), never for this loss.
- QLIKE, labelled proxy: realised variance from daily closes is a noisy stand-in for the true variance. QLIKE ranks
  forecasts the same under such a proxy (Patton 2011), which is why it, not MSE, is the metric. It is asymmetric: it
  punishes an under-forecast more than an over-forecast of the same size.
- d_t = QLIKE(naive)_t - QLIKE(HAR)_t, one-sided: H0 mean(d) <= 0 against mean(d) > 0.
- The test: `{function}(d, q={q}, block={block}, draws={draws}, seed={seed})`. The EWC t estimates the long-run
  variance of d from its {q} lowest cosine frequencies; its p-value is a moving-block bootstrap-t (blocks of {block}
  sessions, the targets' overlap), which carries the skew of d into the reference law. The CI of mean(d) comes from
  the same draws. **Decision: HAR if p < {threshold}, else naive.** d identically 0 gives p = 1. The scorer's result
  carries the threshold and the effective size below next to the p-value. It also carries the fragile band of "How
  fragile the threshold is" and a flag that says whether p lies in it.

## How the threshold was checked
- The battery (`tools/forecast_size.py battery`, {runs} runs per null-side, {sim_draws} bootstrap draws per run where
  the scorer takes {draws_c}, seeds in the .json): {nulls} mean-0 nulls on +d and on -d, {sides} null-sides (the
  review's stochastic-volatility nulls S1-S3 and long-memory family S4, the orchestrator's skewed AR(1) at the
  2002-2009 lag-1 ACF of {rho} and its long-memory variant). At nominal {nominal} the rejection rate lies in [{b0},
  {b1}] on {in_band_05} null-sides: worst {w05}, lowest {l05}. At p < {threshold}: {in_band_t} in that band, worst
  {wt}, lowest {lt}. Outside the band at {nominal} (+d / -d): {outside}.
- The 2002-2009 d-series (n = {cn}) has the centred summaries: ACF at lags 1, 5, 21, 63, 126 and 252 of {acfs};
  moving-block SE ratios r21, r42, r84 of {ratios}; sample skewness {skew}; excess kurtosis {kurt}; spec4_20 {spec}.
  Of {paths_per_null:,} simulated paths per null-side (n = {mn:,}), at most {joint_max} of one null-side's
  ({joint_null}) meet a joint rule on {nj} of the {ns} summaries: "{joint_rule}".
- The matched null-sides: each path's twelve summaries are scaled by their pooled robust SD (IQR / 1.349; the
  kurtosis as log(kurt + 3)); the nearest {accept_pct} of the {paths:,} paths by Euclidean distance to the real d's
  ({accepted} paths) are accepted, and a null-side's weight is its share of them (ABC model choice, uniform prior over
  the {sides} null-sides). {k} null-sides carry weight: {weights}.
- The rule (default taken 2026-11-09, owner can override): {rule}. The sizes on the battery's seeds are the
  battery's own runs. Each matched null-side was run again on a second seed ({mruns:,} runs) and, shifted by {shift}
  SD of its run mean, on the power seed ({mruns:,} runs). The rule picks p < {threshold}, the threshold named before it
  was coded. Per threshold (the size rule is the cap {cap} on both seeds and an ABC-weighted power of at least
  {floor}):

{table}

- Worst sizes, labelled. On the whole battery: {wo05} at {nominal} and {wot} at {threshold} ({wo_null}, path-median
  sample skewness {wo_skew}, {wo_sign} the real d's). On a null-side whose skewness has the real d's sign ({sign}):
  {ws05} at {nominal} and {wst} at {threshold} ({ws_null}, median skewness {ws_skew}). Sample skewness at n = {cn}
  (path medians): the orchestrator's AR(1) nulls {orch_ar1}, its long-memory nulls {orch_long}; the real d {skew}.
- So a rejection at p < {threshold} is evidence at an ABC-weighted size of {abc_b} (battery seed) or {abc_s}
  (second seed) on the null-sides nearest the real d, whose own sizes run from {lo_b} to {hi_b} (battery seed) and
  from {lo_s} to {hi_s} (second seed); and at {wt} if d is as persistent and as skewed as the battery's worst
  null-side.
- Power on the battery's Gaussian AR(1) at rho {rho} shifted to a long-run t of delta (delta 0 is its size, delta 4
  falsifier (c)): at {nominal} {power05}; at {threshold} {power_t}.

## How fragile the threshold is
- The same rule with one modelling choice changed at a time (`tools/forecast_size.py variants`; the row without
  spec4_20 and the kurtosis changes two summaries at once): the battery's runs, and {vruns:,} runs per null-side on
  the second seed ({second}) and on a third seed ({third}) for all {sides} null-sides, so a variant's matched
  null-sides need no new run; the ABC-weighted power on the power seed ({pseed}). Each size is ABC-weighted on the
  variant's matched null-sides, on the battery seed / the second seed unless the variant names other seeds. The last
  {npower} rows change the power requirement, on the registered weights (`tools/forecast_size.py combinations`):

{variants}

- The power-requirement rows. {power_rows}
- The {nseeds} other seeds of the twelve summaries ({seed0} to {seed1}, in place of the match's {seedm}): the rule picks
  {seed_picks}. The size at p < {threshold} runs from {sb_lo} to {sb_hi} (battery seed) and from {ss_lo} to {ss_hi}
  (second seed); the size at p < {next_up} is never below {s_up_min}.
- Monte Carlo error: the binomial SE of the registered ABC-weighted size at p < {threshold} is {se_b} (battery seed)
  and {se_s} (second seed). The cap {cap} is {z_b} and {z_s} SE above the sizes {abc_b} and {abc_s}.
- Every combination of the table's choices (`tools/forecast_size.py combinations`: the saved per-null-side tables
  and the match's summaries drawn again; no new test run): {choices}. One choice at a time gives the table's {n1}
  rows above the power rows; two at a time, {n2} combinations; all of them, {n3:,} combinations.
- **Stated before scoring:** one modelling choice at a time (the {n1} variant rows and the {nseeds} other summary
  seeds) picks p < {lo1} to p < {hi1}, and {none1}. Two at a time pick p < {lo2} to p < {hi2} ({counts2}), and
  {none2}. Every combination of the table's choices picks p < {lo3} to p < {hi3} ({counts3}), and {none3}. {power_picks}.
  With the kurtosis dropped, logging it is no choice, so the {n3:,} combinations are {nd3:,} distinct rules ({nrep:,}
  combinations repeat a rule). Counted by distinct rule: {countsd3}, and {noned3}. The most common pick is p < {mode3}
  by combination and p < {moded3} by distinct rule. Of the {n2} combinations two at a time, {nd2} are rules of their
  own (not a one-at-a-time rule and not counted before): {countsd2}, and {noned2}.
- The picks come from the table's menu: {menu}. {ntop:,} combinations ({ntop_d:,} distinct rules) pick its top, p <
  {top}, so the saved tables cannot say what a threshold above {top} would do.
- The {nnone} combinations that pick none, and both power-requirement rows, fail at p < {lowest} on power, not on
  size. The {nnone} combinations: ABC-weighted power {none_power} against the floor {none_floor}; size at most
  {none_size} against the cap {none_cap}. {power_fail}. So a p below {lowest} is a rejection at a size within the cap
  under every combination and both power rows.
- A p in [{blo}, {bhi}) is decided by these modelling choices, not by the data. A p below {blo} rejects under every
  combination that picks a threshold; a p of {bhi} or more rejects under none, which is true of this menu only. The
  decision stays HAR if p <
  {threshold}: the registered threshold is not chosen again. The scorer's result carries this band as "fragile_band"
  ([{blo}, {bhi}]) and "fragile": true when {blo} <= p < {bhi}.

## What the matched null-sides show
- Nearest in the twelve summaries is not alike in what drives size. The {n_s4} S4 null-sides carry {w_s4} of the
  weight. Their path medians: sample skewness {sk_lo} to {sk_hi} (the real d {skew}), excess kurtosis {ku_lo} to
  {ku_hi} (the real d {kurt}), spec4_20 {sp_lo} to {sp_hi} (the real d {spec}). At most {js4} of one S4 null-side's
  paths meet the joint rule. Only the sign of the skewness matches at the median; the paths accepted from these
  null-sides are the few whose summaries lie near the real d's.
- The other matched null-sides (weight; path-median sample skewness, excess kurtosis and spec4_20; size at p <
  {threshold}, battery seed / second seed): {others}.
- Across the {k} matched null-sides the size at p < {threshold} runs from {lo_b} ({lo_b_null}) to {hi_b} ({hi_b_null})
  on the battery seed, and from {lo_s} ({lo_s_null}) to {hi_s} ({hi_s_null}) on the second seed. The ABC-weighted
  size is a weighted mean of these, so it depends on how the battery was composed. A prior uniform over the three
  families (S1-S3, S4 and the orchestrator's nulls) in place of the {sides} null-sides gives {pf_b} / {pf_s} at p <
  {threshold} and picks p < {pf_pick}.
- The conditional check (`tools/forecast_size.py conditional`): each path has a {cn}-session calibration segment, a
  {gap}-session gap and a {cT:,}-session test segment. The paths whose calibration summaries are nearest the real d's
  (the match's scaling and distance over all of a draw's paths) are accepted, and the test ({cdraws} draws) runs on
  their test segment. The main draw, declared before it ran: {cpaths:,} paths per null ({cside_paths:,} in all), seed
  {cseed}. At p < {threshold}, per share accepted, the accepted paths' size (its binomial SE) against the same
  null-sides' weighted average over all their paths: {cond_rows}. So the accepted paths' size runs from {c_lo} to
  {c_hi}, from {d_lo} to {d_hi} above the side average, at most {zmax} SE from it.
- Two earlier draws of the same check, {e_paths:,} paths per null each. The third fix pass's (seed {e_seed}) gave
  {e_lo} to {e_hi} against side averages of {e_avg_lo} to {e_avg_hi}: {e_d_lo} to {e_d_hi} above them, at most
  {e_zmax} SE. Review D's draw was re-analysed from its saved simulation with identical output; its seed was not
  recorded, and it is not reproducible from this repository. It gave {r_lo} to {r_hi} against {r_avg_lo} to
  {r_avg_hi}: {r_d_lo} to {r_d_hi} above them, at most {r_zmax} SE (from its 4-decimal figures).
- The three draws two at a time: the difference of the accepted paths' size at p < {threshold}, over both draws'
  SEs combined, at the shares {shares}, in that order. The main draw minus the third fix pass's: {g_mf} SE. The main draw minus review D's: {g_mr}
  SE. The third fix pass's minus review D's: {g_fr} SE. {n_over} of these {n_all} differences are larger than 2 SE.
  The binomial SE is conditional on the accepted set: it counts the test's rejections on the paths a draw accepted,
  not which paths it accepts, so it understates the spread between draws.
- Above the cap: {above_cap}. Each is above the rule's size cap {cap} and above the registered ABC-weighted size
  {abc_b} (battery seed) and {abc_s} (second seed).
- Within each null-side whose share of the main draw's nearest 1% is at least {heavy} (its acceptance share in this
  draw, not its registered weight), the tenth of its paths nearest the real d rejects at p < {threshold} at:
  {within}.

## Tests evaluated and rejected (the screen: the battery's {runs} runs per null-side, nominal {nominal})
{screen}
- The rule of the first revision: the smallest worst-case size among the candidates with power of at least {floor1}
  at falsifier (c). It picks the EWC bootstrap-t at q = {q} (worst {w05}, power {p4}); the candidates with that power:
  {powered}.

## The data looked at
- The 2002-2009 d-series ({cstart} to {cend}, n = {cn}, labelled "pre-development") was used only for summaries that
  do not reveal its mean or sign: the ACF (lag 1 {acf1}), the moving-block SE sweep (it did not settle: se(168)/se(84)
  = {r84}), its centred moments (skewness {skew_pop} and excess kurtosis {kurt_pop}, moments of (d - mean) / sd with
  ddof 0: the same sample estimators as the twelve summaries, to 3 decimals) and the twelve summaries above. The
  lag-1 ACF {acf1} set the battery's AR(1) nulls and falsifier (c), on whose power the first revision chose q = {q}
  and the EWC bootstrap-t. The twelve summaries set the matched null-sides that check the threshold.
- Disclosed: milestone 4 part A's IV30 probe (a scratch script outside the repository) printed VrpSignal("har") and
  VrpSignal("naive") values on 5 sessions of 2015. Each embeds that session's HAR or naive RV forecast. No target,
  loss or d was computed from them.
- The scorer's SHA-256 covers the {nfiles} files of its closure: the repository files it imports, found from the
  source. Other code outside the closure is not hashed. The scorer's checks catch mistakes and the routes they name.
  They do not stop code written to defeat them. Any code that runs in the scorer's process before or between the
  checks can defeat them: a file put on the import path, a .pth file, an edited library or standard library, a
  forged .pyc, or a module that removes itself. The routes named here are examples, not a complete list.
- The checks of tools/ read every folder in tools/ and every file there whose name ends with an import suffix (.py,
  .pyc or an extension module's suffix). A file's module name is its name less the longest import suffix; a
  folder's module name is its name. The checks leave out an entry whose module name holds a dot, such as
  tools/prereg.old.py: no import loads it under any name. They also leave out tools/__pycache__, Python's bytecode
  cache. Python writes it when the scorer imports its modules, git ignores it, and the standard library also has a
  folder of that name, so the commit check and the name check would refuse every run. `import __pycache__` can load
  it, and no check reads what it holds. The checks read a name with a hyphen: the standard library's sysconfig
  imports its data module by such a name (here _sysconfigdata__linux_aarch64-linux-gnu).
- Run as a script, before it imports tools/prereg.py, the scorer refuses to run when an entry of tools/ that the
  checks read takes the name of one of the scorer's modules there and is not that module's .py file (a tools/prereg/
  package would run in place of tools/prereg.py), or when two entries of tools/ that the checks read share a module
  name. Before it imports any third-party module, it refuses when PYTHONPATH, PYTHONHOME, PYTHONUSERBASE or
  _PYTHON_SYSCONFIGDATA_NAME is set, when an entry of tools/ that the checks read has the name of a standard-library
  module or of a module found on another entry of sys.path, when HEAD does not hold such an entry as committed, or
  when sys.modules holds a module loaded from tools/ that is not a closure file. Under the ledgers' lock, just before
  it writes the first spent line, the scorer refuses again when sys.modules holds such a module. The first three
  variables can put other code before the scorer's. _PYTHON_SYSCONFIGDATA_NAME names the module sysconfig imports,
  and the scorer refuses it before that import. The name check also runs before that import, so a tools/ file named
  after sysconfig's data module is refused before it runs. The commit check reads the same entries as the name
  check: a file with an import suffix, or a folder. A file must be in HEAD with the same bytes. For a folder, HEAD
  must hold it as a folder, and every file with an import suffix directly in it must be committed as it is. The
  commit check does not read files deeper down, or files without an import suffix.
- Some routes run before the check that refuses them, or are not refused. A tools/ file named after a
  standard-library module that the scorer imports first (tools/gettext.py) runs before the check that refuses it. A
  committed tools/ file that a library imports when it exists (tools/numexpr.py, which pandas imports) runs before
  the check under the lock. If its import raises ImportError, Python removes it from sys.modules and pandas carries
  on: no check refuses it, and the scorer scores. A committed tools/ file that is first imported after the spend is
  not refused.
- The pre-registration names the versions of {libs}. {amend}
- The store's spy_bars and dividends files are named by SHA-256: scoring on other data refuses.

## What happens next
1. Commit the whole tree first, tools/ in full, with the three files and an empty spent.jsonl (after the history
   rewrite). The scorer's checks read each file with an import suffix and each folder in tools/, other than
   tools/__pycache__ and an entry whose module name holds a dot. The scorer refuses to run while HEAD does not hold
   such an entry as committed. A file must be in HEAD with the same bytes. For a folder, HEAD must hold it as a
   folder, and every file with an import suffix directly in it must be committed as it is. The commit check does not
   read files deeper down, or files without an import suffix (tools/score_prereg.py uncommitted_entries says which).
2. `uv run python tools/score_prereg.py {id}`, once. It spends the window (spent.jsonl and its side ledger in the
   git common directory) before it computes the result.
3. Commit the result and spent.jsonl and push at once: the pushed history is then the record. Until then, a clone
   whose refs do not reach that commit does not see the spend (tools/prereg.py names other ways to defeat the
   tripwire). Then set the signal's rv_model by the decision rule.
"""


def wrap(text: str, width: int = 118) -> str:
    """Each paragraph, bullet or numbered item re-flowed to `width` at spaces (a bullet's continuation indented by
    two, a numbered item's by three); headings, table lines and blank lines kept as they are."""
    out: list[str] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            indent = "  " if para[0].startswith("- ") else "   " if para[0][:1].isdigit() else ""
            out.append(textwrap.fill(" ".join(line.strip() for line in para), width, subsequent_indent=indent,
                                     break_on_hyphens=False, break_long_words=False))
            para.clear()

    for line in text.splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("|"):
            flush()
            out.append(line)
        else:
            if line.startswith("- ") or line[:1].isdigit():
                flush()
            para.append(line)
    flush()
    return "\n".join(out) + "\n"


def rate(worst: dict) -> str:
    return f"{worst['rate']:g} ({worst['null']}, {worst['side']})"


def critical(candidate: dict) -> str:
    return "" if candidate.get("cv") is None else f" (critical value {candidate['cv']:g})"


def f4(x: float) -> str:
    return f"{x:.4f}"


def pick(threshold) -> str:
    return "none" if threshold is None else f"{threshold:g}"


def threshold_table(spec: dict) -> str:
    """The matched rule's table: per threshold, the ABC-weighted size on both seeds, the worst matched null-side's,
    the ABC-weighted power, the battery's falsifier (c) power (marked when below the first revision's floor) and the
    size rule's mark (fix pass 3, item D3d)."""
    m, floor1 = spec["matched"], spec["screen"]["first_revision_rule"]["power_floor"]
    lines = ["| p < | ABC size, battery / second seed | Worst matched, battery / second seed | ABC power | "
             "Falsifier (c) power | Size rule |", "|---|---|---|---|---|---|"]
    for r in m["table"]:
        fc = f"{r['falsifier_c_power']:g}" + (f" (below the first revision's {floor1:g})"
                                              if r["falsifier_c_power"] < floor1 else "")
        lines.append(f"| {r['threshold']:g} | {f4(r['abc_size_battery_seed'])} / {f4(r['abc_size_second_seed'])} | "
                     f"{r['worst_matched_size_battery_seed']['rate']:g} / "
                     f"{r['worst_matched_size_second_seed']['rate']:g} | {f4(r['abc_power'])} | {fc} | "
                     f"{'passes' if r['passes'] else 'fails'} |")
    return "\n".join(lines)


def variant_table(spec: dict) -> str:
    """The variants' table: each variant's description, matched null-sides, pick, sizes at the three thresholds
    nearest the registered one (on the seeds it names) and its ABC-weighted power at the registered threshold; then
    the combinations' power-requirement rows (fix pass 4, item F1)."""
    v, t = spec["variants"], spec["threshold"]
    order = [key(r["threshold"]) for r in spec["matched"]["table"]]
    i = order.index(key(t))
    shown = order[max(i - 1, 0):i + 2]
    lines = ["| Variant | Matched null-sides | Picks p < | "
             + " | ".join(f"Size at p < {a}" for a in shown) + f" | ABC power at p < {t:g} |",
             "|---|---|---|" + "---|" * len(shown) + "---|"]
    for row in v["variants"] + spec["combinations"]["power_rows"]:
        seeds = [name for name in ("battery", "second", "third") if name in row["size"]]
        cells = [" / ".join(f4(row["size"][name][a]) for name in seeds) for a in shown]
        lines.append(f"| {row['description']} | {row['sides']} | {pick(row['threshold'])} | " + " | ".join(cells)
                     + f" | {f4(row['power'][key(t)])} |")
    return "\n".join(lines)


def picks(spec: dict) -> list[float | None]:
    """The threshold each variant and each other summary seed picks, None for one that picks none (fix pass 4, review
    E N3: the .md counts them)."""
    v = spec["variants"]
    return [r["threshold"] for r in v["variants"]] + [r["threshold"] for r in v["summary_seeds"]["rows"]]


def counted(counts: dict) -> tuple[str, str, str, str]:
    """From {threshold: count, "none": count}: the lowest and the highest threshold picked, the counts in ascending
    order ("p < 0.02 on 7, ...") and the words for the ones that pick none."""
    picked = sorted((float(a), n) for a, n in counts.items() if a != "none" and n)
    return (f"{picked[0][0]:g}", f"{picked[-1][0]:g}", ", ".join(f"p < {a:g} on {n:,}" for a, n in picked),
            none_words(counts.get("none", 0)))


def none_words(n: int) -> str:
    return "each picks a threshold" if n == 0 else f"{n:,} pick{'s' if n == 1 else ''} no threshold"


def mode(counts: dict) -> str:
    """The threshold picked most often in {threshold: count, "none": count} (fix pass 5, item G2)."""
    best = max(n for a, n in counts.items() if a != "none")
    modes = [a for a, n in counts.items() if a != "none" and n == best]
    if len(modes) != 1:
        raise PreregError(f"no single most common pick in {counts}")
    return f"{float(modes[0]):g}"


def none_at_lowest_text(comb: dict, lowest: str) -> tuple[str, str, str, str, str]:
    """Why the full grid's combinations that pick none pick none: at the lowest threshold of the menu each fails on
    power only (fix pass 5, item G2, review F N1). Their ABC-weighted powers (with how many combinations have each),
    the floor, the largest size and the cap; and the power-requirement rows at that threshold. A combination or a row
    that fails on size there, or passes, is an error: the .md says a p below it is a size-controlled rejection."""
    rows = comb["full_grid"]["none_at_lowest"]
    if len(rows) != comb["full_grid"]["picks"].get("none", 0):
        raise PreregError(f"{len(rows)} none_at_lowest rows for {comb['full_grid']['picks'].get('none', 0)} "
                          "combinations that pick none")
    if any(key(r["threshold"]) != lowest or r["fails"] != ["power"] for r in rows):
        raise PreregError(f"a combination that picks none does not fail on power alone at p < {lowest}: {rows}")
    floors, caps = {r["floor"] for r in rows}, {r["cap"] for r in rows}
    if len(floors) != 1 or len(caps) != 1:
        raise PreregError(f"the combinations that pick none have floors {floors} and caps {caps}")
    powers: dict[str, int] = {}
    for r in sorted(rows, key=lambda r: -r["power"]):
        powers[f4(r["power"])] = powers.get(f4(r["power"]), 0) + 1
    power_words = " and ".join(f"{a} on {n}" for a, n in powers.items())
    texts = []
    for r in comb["power_rows"]:
        power = r["power"] if r["requirement"] == "abc_power" else r["falsifier_c_power"]
        size = max(r["size"][seed][lowest] for seed in r["size"])
        if power[lowest] >= r["floor"] or size > r["cap"]:
            raise PreregError(f"the power row {r['name']!r} does not fail on power alone at p < {lowest}")
        what = "ABC-weighted power" if r["requirement"] == "abc_power" else "falsifier (c) power"
        texts.append(f"\"{r['name']}\": {what} {power[lowest]:.4g} against {r['floor']:g}, size at most {f4(size)} "
                     f"against the cap {r['cap']:g}")
    return (power_words, f"{floors.pop():g}", f4(max(max(r["size"]) for r in rows)), f"{caps.pop():g}",
            "The power rows at p < " + lowest + ": " + "; ".join(texts))


def draws_compared(cond: dict, threshold: float, cap: float, registered: tuple[float, float]) -> dict:
    """The three conditional draws two at a time at each share: (a - b) / hypot(se_a, se_b) at p < threshold; how
    many of them exceed 2 SE; and the accepted-path sizes above the rule's cap (fix pass 5, item G4, review F
    claim 3)."""
    t = key(threshold)
    def at(rows: list[dict]) -> list[dict]:
        return [{"accept": r["accept"], **r["by_threshold"][t]} for r in rows]

    draws = {"main": at(cond["by_accept"]), "fix_pass_3": at(cond["earlier"]["fix_pass_3"]["by_accept"]),
             "review_d": cond["earlier"]["review_d"]["by_accept"]}
    shares = [r["accept"] for r in draws["main"]]
    if any([r["accept"] for r in rows] != shares for rows in draws.values()):
        raise PreregError("the three conditional draws do not have the same acceptance shares")
    names = {"main": "the main draw's", "fix_pass_3": "the third fix pass's", "review_d": "review D's"}
    out, zs = {}, []
    for label, (a, b) in {"g_mf": ("main", "fix_pass_3"), "g_mr": ("main", "review_d"),
                          "g_fr": ("fix_pass_3", "review_d")}.items():
        z = [(x["accepted_paths"] - y["accepted_paths"]) / math.hypot(x["se"], y["se"])
             for x, y in zip(draws[a], draws[b])]
        zs += z
        out[label] = ", ".join(f"{v:+.2f}" for v in z)
    above = [(names[name], r) for name, rows in draws.items() for r in rows if r["accepted_paths"] > cap]
    if not above or any(r["accepted_paths"] <= max(registered) for _, r in above):
        raise PreregError(f"the accepted-path sizes above the cap {cap}: {above}")
    out.update(shares=", ".join(f"{a:.2%}" for a in shares), n_over=sum(abs(v) > 2 for v in zs), n_all=len(zs),
               above_cap=", ".join(f"{name} {f4(r['accepted_paths'])} at {r['accept']:.2%}" for name, r in above))
    return out


def thresholds_text(values: list[str]) -> str:
    """["0.05", "0.04", "0.03"] -> "p < 0.05, 0.04 and 0.03"; [] -> "no threshold"."""
    if not values:
        return "no threshold"
    words = [f"{float(a):g}" for a in values]
    return "p < " + (words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1])


def power_row_text(row: dict, order: list[str]) -> str:
    """Where a power-requirement row's power requirement and its size cap hold, and what it picks."""
    power = row["power"] if row["requirement"] == "abc_power" else row["falsifier_c_power"]
    what = "the ABC-weighted power" if row["requirement"] == "abc_power" else "the falsifier (c) power"
    met = [a for a in order if power[a] >= row["floor"]]
    capped = [a for a in order if max(row["size"][s][a] for s in row["size"]) <= row["cap"]]
    values = ", ".join(f"{power[a]:.4g}" for a in order)
    pick_words = "no threshold meets both, so it picks none" if row["threshold"] is None else \
        f"it picks p < {row['threshold']:g}"
    name = row["description"][:1].upper() + row["description"][1:]
    return (f"{name}: {what} is {values} at p < {', '.join(f'{float(a):g}' for a in order)}; it "
            f"reaches {row['floor']:g} at {thresholds_text(met)}, and the size is at most the cap {row['cap']:g} at "
            f"{thresholds_text(capped)}: {pick_words}.")


def rationale_for(spec: dict) -> str:
    """The .md from the spec: every figure is a value of the .json (fix pass 2, item 13), and the .md written by main
    is rationale_for of the .json as written (fix pass 3, item D3a: tests/test_prereg_files.py)."""
    w, c, s, m, scr = spec["windows"][0], spec["calibration"], spec["size"], spec["matched"], spec["screen"]
    v, cond, test, hist = spec["variants"], spec["conditional"], spec["test"], spec["threshold_history"]
    threshold = spec["threshold"]
    t, t05 = key(threshold), key(NOMINAL)
    by, real = s["by_threshold"], m["real"]
    band = s["band"]
    floor1 = scr["first_revision_rule"]["power_floor"]
    outside = "; ".join(f"{x['name']} {x['plus_d_at_0.05']:g} / {x['minus_d_at_0.05']:g}" for x in s["nulls"]
                        if not all(band[0] <= x[k] <= band[1] for k in ("plus_d_at_0.05", "minus_d_at_0.05")))
    weights = ", ".join(f"{x['null_side']} {x['weight']:.4f}" for x in sorted(m["matched"], key=lambda x: -x["weight"]))
    sides = {x["null_side"]: x for x in m["null_sides"]}
    medians = {name: x["median"] for name, x in sides.items()}
    orch = {kind: " and ".join(f"{medians[f'orch {kind} s={sv} +d']['skew']:.2f} (s = {sv})" for sv in ("1.0", "1.5"))
            for kind in ("ar1", "long")}
    worst, same = m["worst"]["overall"], m["worst"]["same_skew_sign"]
    row = next(r for r in m["table"] if r["threshold"] == threshold)
    screen = "\n".join(f"- {scr['candidates'][name]['description']}{critical(scr['candidates'][name])}: worst "
                       f"{rate(scr['candidates'][name]['worst']['high'])}, {scr['candidates'][name]['in_band']} in "
                       f"the band, power {scr['candidates'][name]['power']['4.0']:g} at falsifier (c)"
                       for name in scr["order"])
    powered = "; ".join(f"{scr['candidates'][name]['description']}: worst "
                        f"{scr['candidates'][name]['worst']['high']['rate']:g}, power "
                        f"{scr['candidates'][name]['power']['4.0']:g}"
                        for name in scr["order"] if scr["candidates"][name]["power"]["4.0"] >= floor1)
    power = {k: ", ".join(f"{p:g} at delta {d}" for d, p in sorted(by[k]["power"].items(), key=lambda kv: float(kv[0])))
             for k in (t05, t)}
    method = m["method"]
    # the spread across the matched null-sides, and what drives size (fix pass 3, item D2)
    spread_b, spread_s = spread(m["matched"], "battery", threshold), spread(m["matched"], "second", threshold)
    s4 = [x for x in m["matched"] if x["null_side"].startswith("S4 ")]
    rest = [x for x in sorted(m["matched"], key=lambda x: -x["weight"]) if not x["null_side"].startswith("S4 ")]
    ranges = {k: (min(medians[x["null_side"]][k] for x in s4), max(medians[x["null_side"]][k] for x in s4))
              for k in ("skew", "kurt", "spec4_20")}
    others = "; ".join(f"{x['null_side']} ({x['weight']:.4f}; {medians[x['null_side']]['skew']:.2f}, "
                       f"{medians[x['null_side']]['kurt']:.2f}, {medians[x['null_side']]['spec4_20']:.2f}; "
                       f"{x['size_battery_seed'][t]:g} / {x['size_second_seed'][t]:g})" for x in rest)
    variants = {r["name"]: r for r in v["variants"]}
    family, cap05 = variants["prior uniform over the 3 families"], variants["cap 0.05"]
    # the variants' picks, the other summary seeds and the Monte Carlo error (fix pass 3, item D1)
    every = picks(spec)
    picked = [x for x in every if x is not None]
    # every combination of the table's choices and the power-requirement rows (fix pass 4, item F1)
    comb = spec["combinations"]
    fband = spec["fragile_band"]
    if fband != comb["band"]:
        raise PreregError(f"fragile_band {fband} is not the combinations' band {comb['band']}")
    order = [key(r["threshold"]) for r in m["table"]]
    lo2, hi2, counts2, none2 = counted(comb["two_at_a_time"]["picks"])
    lo3, hi3, counts3, none3 = counted(comb["full_grid"]["picks"])
    # the distinct rules, the menu and the combinations that pick none (fix pass 5, item G2)
    distinct, distinct2 = comb["full_grid"]["distinct_rules"], comb["two_at_a_time"]["distinct"]
    _, _, countsd3, noned3 = counted(distinct["picks"])
    _, _, countsd2, noned2 = counted(distinct2["picks"])
    if [key(x) for x in comb["thresholds"]] != order:
        raise PreregError(f"the combinations' menu {comb['thresholds']} is not the table's {order}")
    top, lowest = key(max(comb["thresholds"])), key(min(comb["thresholds"]))
    if lowest != key(fband[0]):
        raise PreregError(f"the band {fband} does not start at the menu's lowest threshold {lowest}")
    none_power, none_floor, none_size, none_cap, power_fail = none_at_lowest_text(comb, lowest)
    if [float(lo3), float(hi3)] != [float(x) for x in fband]:
        raise PreregError(f"the full grid picks p < {lo3} to p < {hi3}, the band is {fband}")
    rows_power = comb["power_rows"]
    power_picks = ("Both power-requirement rows pick no threshold" if all(r["threshold"] is None for r in rows_power)
                   else "The power-requirement rows pick " + ", ".join(pick(r["threshold"]) for r in rows_power))
    names = {"cap": "the cap", "accept": "the share accepted", "drop": "the summaries dropped",
             "scale": "the scaling", "logkurt": "the kurtosis logged", "prior": "the prior", "seeds": "the size seeds"}

    def value_words(dim, value):
        if dim == "accept":
            return f"{value:.2%}"
        if dim == "drop":
            return " and ".join(value) if value else "none"
        if dim == "logkurt":
            return "yes" if value else "no"
        return f"{value:g}" if isinstance(value, float) else str(value)

    choices = "; ".join(f"{names[dim]} ({', '.join(value_words(dim, x) for x in values)})"
                        for dim, values in comb["choices"].items())
    rows = v["summary_seeds"]["rows"]
    counts = [(a, n) for a, n in v["summary_seeds"]["picks"].items() if n]
    seed_picks = "; ".join(f"p < {a} on {n} of {len(rows)}" if a != "none" else f"none on {n} of {len(rows)}"
                           for a, n in counts)
    ups = sorted(r["threshold"] for r in m["table"] if r["threshold"] > threshold)
    up = key(ups[0]) if ups else t
    se = v["mc_se"]["registered_weights"]
    abc_b, abc_s = row["abc_size_battery_seed"], row["abc_size_second_seed"]
    # the conditional check (fix pass 3, item D2)
    cond_rows, diffs, zs, sizes = [], [], [], []
    for r in cond["by_accept"]:
        x = r["by_threshold"][t]
        cond_rows.append(f"{r['accept']:.2%} ({r['accepted']:,} paths, {r['sides']} null-sides) "
                         f"{f4(x['accepted_paths'])} ({f4(x['se'])}) against {f4(x['side_average'])}")
        diffs.append(x["accepted_paths"] - x["side_average"])
        zs.append(abs(x["accepted_paths"] - x["side_average"]) / x["se"] if x["se"] else float("inf"))
        sizes.append(x["accepted_paths"])
    other = cond["earlier"]["review_d"]["by_accept"]
    earlier = cond["earlier"]["fix_pass_3"]
    e_rows = [r["by_threshold"][t] for r in earlier["by_accept"]]
    if [r["accept"] for r in earlier["by_accept"]] != [x["accept"] for x in other]:
        raise PreregError("the two earlier conditional draws do not have the same acceptance shares")
    compared = draws_compared(cond, threshold, m["size_cap"], (abc_b, abc_s))
    within = "; ".join(f"{x['null_side']} (share {x['weight']:.4f}) {f4(x['nearest_10pct'][t])} on its nearest "
                       f"{x['n']:,} against {f4(x['all'][t])} on all its paths" for x in cond["within_side"])
    return wrap(RATIONALE.format(
        id=FORECAST_ID, threshold=threshold, floor1=f"{floor1:g}", shift=f"{m['shift_sd']:g}",
        fc_t=f"{row['falsifier_c_power']:g}", abc_power=f4(row["abc_power"]), h_th=f"{hist['threshold']:g}",
        h_sizes=" and ".join(f"{x['rate']:g} (seed {x['seed']}, {x['runs_per_null_side']:,} runs per matched "
                             "null-side of its own match)" for x in hist["review_a_abc_size"]),
        h_cap=f"{hist['size_cap']:g}", cap05=f"{cap05['cap']:g}", cap05_pick=pick(cap05["threshold"]),
        start=w["start"], end=w["end"], n=f"{w['n']:,}", last=w["last_target_end"],
        function=test["function"], q=test["q"],
        block=test["block"], draws=test["draws"], seed=test["seed"], draws_c=f"{test['draws']:,}",
        nominal=f"{NOMINAL:g}", runs=f"{s['runs']:,}", sim_draws=f"{s['simulated_draws']:,}", nulls=len(s["nulls"]),
        sides=2 * len(s["nulls"]), rho=f"{s['power_rho']:g}", b0=f"{band[0]:g}", b1=f"{band[1]:g}",
        in_band_05=by[t05]["in_band"], w05=rate(by[t05]["worst"]["high"]), l05=rate(by[t05]["worst"]["low"]),
        in_band_t=by[t]["in_band"], wt=rate(by[t]["worst"]["high"]), lt=rate(by[t]["worst"]["low"]), outside=outside,
        cn=f"{c['window']['n']:,}", acfs=", ".join(f"{real[f'acf{lag}']:g}" for lag in (1, 5, 21, 63, 126, 252)),
        ratios=", ".join(f"{real[r]:g}" for r in ("r21", "r42", "r84")), skew=f"{real['skew']:g}",
        kurt=f"{real['kurt']:g}", spec=f"{real['spec4_20']:g}", paths_per_null=method["paths_per_null"],
        mn=method["n"], joint_max=m["joint"]["max_share"], joint_null=m["joint"]["max_null_side"],
        nj=len(m["joint"]["summaries"]), ns=len(method["summaries"]), joint_rule=m["joint"]["rule"],
        accept_pct=f"{method['accept']:.0%}", paths=method["paths"], accepted=method["accepted"], k=len(m["matched"]),
        weights=weights, rule=m["rule"], mruns=m["runs"], cap=f"{m['size_cap']:g}", floor=f"{m['power_floor']:g}",
        table=threshold_table(spec), wo05=worst[t05]["rate"], wot=worst[t]["rate"], wo_null=worst[t]["null_side"],
        wo_skew=f"{worst[t]['median_skew']:+.2f}",
        wo_sign="the sign of" if worst[t]["median_skew"] * real["skew"] > 0 else "the sign opposite to",
        sign="+" if real["skew"] > 0 else "-", ws05=same[t05]["rate"], wst=same[t]["rate"],
        ws_null=same[t]["null_side"], ws_skew=f"{same[t]['median_skew']:+.2f}", orch_ar1=orch["ar1"],
        orch_long=orch["long"], abc_b=f4(abc_b), abc_s=f4(abc_s),
        lo_b=f"{spread_b['lowest']['rate']:g}", hi_b=f"{spread_b['highest']['rate']:g}",
        lo_s=f"{spread_s['lowest']['rate']:g}", hi_s=f"{spread_s['highest']['rate']:g}",
        lo_b_null=spread_b["lowest"]["null_side"], hi_b_null=spread_b["highest"]["null_side"],
        lo_s_null=spread_s["lowest"]["null_side"], hi_s_null=spread_s["highest"]["null_side"],
        power05=power[t05], power_t=power[t], vruns=v["runs"], second=v["seeds"]["second"],
        third=v["seeds"]["third"], pseed=v["seeds"]["power"], variants=variant_table(spec),
        nseeds=len(rows), seed0=v["summary_seeds"]["seeds"][0], seed1=v["summary_seeds"]["seeds"][-1],
        seedm=m["seeds"]["summaries"], seed_picks=seed_picks,
        sb_lo=f4(min(r["size"]["battery"][t] for r in rows)), sb_hi=f4(max(r["size"]["battery"][t] for r in rows)),
        ss_lo=f4(min(r["size"]["second"][t] for r in rows)), ss_hi=f4(max(r["size"]["second"][t] for r in rows)),
        next_up=up, s_up_min=f4(min(min(r["size"]["battery"][up], r["size"]["second"][up]) for r in rows)),
        se_b=f4(se["battery"][t]), se_s=f4(se["second"][t]),
        z_b=f"{(m['size_cap'] - abc_b) / se['battery'][t]:.1f}", z_s=f"{(m['size_cap'] - abc_s) / se['second'][t]:.1f}",
        npower=len(rows_power), power_rows=" ".join(power_row_text(r, order) for r in rows_power),
        choices=choices, n1=len(v["variants"]) - 1, n2=comb["two_at_a_time"]["n"], n3=comb["full_grid"]["n"],
        lo1=f"{min(picked):g}", hi1=f"{max(picked):g}", none1=none_words(len(every) - len(picked)),
        lo2=lo2, hi2=hi2, counts2=counts2, none2=none2, lo3=lo3, hi3=hi3, counts3=counts3, none3=none3,
        power_picks=power_picks, blo=f"{fband[0]:g}", bhi=f"{fband[1]:g}",
        nd3=distinct["n"], nrep=comb["full_grid"]["n"] - distinct["n"], countsd3=countsd3, noned3=noned3,
        mode3=mode(comb["full_grid"]["picks"]), moded3=mode(distinct["picks"]), nd2=distinct2["n"],
        countsd2=countsd2, noned2=noned2, menu=thresholds_text([str(x) for x in comb["thresholds"]]),
        ntop=comb["full_grid"]["picks"][top], ntop_d=distinct["picks"][top], top=f"{float(top):g}",
        nnone=len(comb["full_grid"]["none_at_lowest"]), lowest=f"{float(lowest):g}", none_power=none_power,
        none_floor=none_floor, none_size=none_size, none_cap=none_cap, power_fail=power_fail,
        n_s4=len(s4), w_s4=f4(sum(x["weight"] for x in s4)),
        sk_lo=f"{ranges['skew'][0]:.2f}", sk_hi=f"{ranges['skew'][1]:.2f}", ku_lo=f"{ranges['kurt'][0]:.2f}",
        ku_hi=f"{ranges['kurt'][1]:.2f}", sp_lo=f"{ranges['spec4_20'][0]:.2f}", sp_hi=f"{ranges['spec4_20'][1]:.2f}",
        js4=f"{max(sides[x['null_side']]['joint_share'] for x in s4):g}", others=others,
        pf_b=f4(family["size"]["battery"][t]), pf_s=f4(family["size"]["second"][t]), pf_pick=pick(family["threshold"]),
        cpaths=cond["paths_per_null"], cdraws=f"{cond['draws']:,}", gap=cond["gap"], cT=cond["T"],
        cside_paths=2 * len(s["nulls"]) * cond["paths_per_null"], cond_rows="; ".join(cond_rows),
        cseed=cond["seed_value"], e_paths=earlier["paths_per_null"],
        e_seed=re.search(r"default_rng\(\[(\d+),", earlier["seed"]).group(1),
        e_lo=f4(min(x["accepted_paths"] for x in e_rows)), e_hi=f4(max(x["accepted_paths"] for x in e_rows)),
        e_avg_lo=f4(min(x["side_average"] for x in e_rows)), e_avg_hi=f4(max(x["side_average"] for x in e_rows)),
        e_d_lo=f"{min(x['accepted_paths'] - x['side_average'] for x in e_rows):+.4f}",
        e_d_hi=f"{max(x['accepted_paths'] - x['side_average'] for x in e_rows):+.4f}",
        e_zmax=f"{max(abs(x['accepted_paths'] - x['side_average']) / x['se'] for x in e_rows):.1f}", **compared,
        c_lo=f4(min(sizes)), c_hi=f4(max(sizes)),
        d_lo=f"{min(diffs):+.4f}", d_hi=f"{max(diffs):+.4f}", zmax=f"{max(zs):.1f}", heavy=f"{cond['heavy']:g}",
        r_lo=f4(min(x["accepted_paths"] for x in other)), r_hi=f4(max(x["accepted_paths"] for x in other)),
        r_avg_lo=f4(min(x["side_average"] for x in other)), r_avg_hi=f4(max(x["side_average"] for x in other)),
        r_d_lo=f"{min(x['accepted_paths'] - x['side_average'] for x in other):+.4f}",
        r_d_hi=f"{max(x['accepted_paths'] - x['side_average'] for x in other):+.4f}",
        r_zmax=f"{max(abs(x['accepted_paths'] - x['side_average']) / x['se'] for x in other):.1f}",
        within=within, screen=screen, p4=by[t05]["power"]["4.0"], powered=powered,
        cstart=c["window"]["start"], cend=c["window"]["end"], acf1=c["acf"][1], r84=c["ratios"]["84"],
        skew_pop=c["skewness"], kurt_pop=c["excess_kurtosis"], nfiles=len(spec["scorer_files"]),
        libs=", ".join(f"{k} {v}" for k, v in spec["libraries"].items()),
        amend="A closure file edited by mistake, or another version of a library or of Python, makes the scorer "
              "refuse; the remedy is an amendment, a new dated file that names this one's hash."))


def print_dependence(dependence: dict) -> None:
    """The centred summaries of the calibration window (none reveals the mean of d or its sign)."""
    window = dependence["window"]
    print(f"calibration window {window['start']} .. {window['end']} (n {window['n']})")
    acf = dependence["acf"]
    print(f"acf lag 1 {acf[1]}, lag 21 {acf[21]}, lag 42 {acf[42]}, lag 63 {acf[63]}")
    print(f"se {dependence['se']}; ratios {dependence['ratios']}; skewness {dependence['skewness']}, "
          f"excess kurtosis {dependence['excess_kurtosis']}")
    print(f"summaries {dependence['summaries']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=("dependence", "forecast"))
    parser.add_argument("--out", type=Path, help="dependence: where to write the summaries (JSON)")
    parser.add_argument("--size", type=Path, help="forecast: tools/forecast_size.py battery's output")
    parser.add_argument("--match", type=Path, help="forecast: tools/forecast_size.py match's output")
    parser.add_argument("--variants", type=Path, help="forecast: tools/forecast_size.py variants' output")
    parser.add_argument("--conditional", type=Path, help="forecast: tools/forecast_size.py conditional's output (the "
                                                          "main draw)")
    parser.add_argument("--conditional-earlier", type=Path, help="forecast: an earlier conditional draw's output")
    parser.add_argument("--combinations", type=Path, help="forecast: tools/forecast_size.py combinations' output")
    parser.add_argument("--store", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.what == "dependence" and args.out is None:
        parser.error("dependence needs --out")
    if args.what == "forecast" and None in (args.size, args.match, args.variants, args.conditional,
                                            args.conditional_earlier, args.combinations):
        parser.error("forecast needs --size, --match, --variants, --conditional, --conditional-earlier and "
                     "--combinations")
    from volbt.data.store import Store

    store = Store(args.store)
    dependence = measure_dependence(store)
    print_dependence(dependence)
    if args.what == "dependence":
        args.out.write_text(json.dumps(dependence, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return 0
    inputs = {}
    for name in ("size", "match", "variants", "conditional", "earlier", "combinations"):
        path = getattr(args, "conditional_earlier" if name == "earlier" else name)
        inputs[name] = {**json.loads(path.read_text(encoding="utf-8")), "sha256": file_sha256(path)}
    spec = forecast_spec(store, dependence, **inputs)
    # the .md is built from the .json as written (sorted keys), so rationale_for(<the .json>) is the .md (item D3a)
    sums = write(spec, rationale_for(json.loads(canonical(spec))), PREREG_DIR)
    for ext, digest in sums.items():
        print(f"{digest}  {FORECAST_ID}.{ext}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
