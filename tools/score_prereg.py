"""Score a frozen pre-registration, once (milestone 4, plan section 6).

Run:  uv run python tools/score_prereg.py <prereg id> [--store DIR]
      (only after the whole tree is committed: its three files, spent.jsonl and tools/ in full)

It reads and writes docs/validation/prereg/ and the side ledger in the git common directory only (no other folder
can be named). main() takes the command line and nothing else (fix pass 6, item H2: review G called main() from
`python -c` with another repository, an edited module root, a made-up store or made-up series). It refuses, with exit
code 2 and nothing computed, when:
  run as a script, before `import prereg` (name_clashes; fix pass 7, item I1, review H claims 1 and 2: Python's finder
  tries a package folder and an extension module before a .py file, so a tools/prereg/ package ran in place of
  tools/prereg.py at `import prereg`, before every check):
    - an entry of <repo>/tools that the checks read (below) other than a closure module's .py file has that module's
      name (CLOSURE_TOOLS: a tools/prereg/ folder, a tools/prereg.<extension suffix> file, a tools/prereg.pyc), or two
      entries of <repo>/tools that the checks read share a module name
  before any third-party import (check_process), in this order:
    - PYTHONPATH, PYTHONHOME or PYTHONUSERBASE is set (fix pass 4, item F5), or _PYTHON_SYSCONFIGDATA_NAME is set: it
      names the module sysconfig imports in check_process, so a tools/ file of that name would run there, before the
      commit check (fix pass 9, item K2; review J N1)
    - an entry of <repo>/tools that the checks read has the name of a standard-library module, or of a module that
      importlib.machinery.PathFinder finds on another entry of sys.path: tools/ is first on sys.path, so it would run
      in that module's place (fix pass 5, item G5: tools/gettext.py; fix pass 6, item H1, review G claim 2:
      tools/pytz.py, which pandas imports after this check; fix pass 8, item J2, review I claim 3:
      tools/_sysconfigdata__linux_aarch64-linux-gnu.py, which sysconfig imports in check_process, so this check comes
      before the next one, which calls sysconfig)
    - an entry of sys.path before the standard library is not <repo>/tools, or main() is defined in a file other than
      <repo>/tools/score_prereg.py: an edited copy under another name (fix pass 4, item F5). `python -I` cannot run
      the scorer: it leaves tools/ off sys.path, so `import prereg` fails; that is kept so (review E N1)
    - HEAD does not hold an entry of <repo>/tools that the checks read (a file with an import suffix, or a folder) as
      committed: a file must be in HEAD with the same bytes; for a folder, HEAD must hold it as a folder and every
      file with an import suffix directly in it must be committed as it is; files deeper down, and files without an
      import suffix, are not checked (fix pass 6, item H1: tools/numexpr.py is found nowhere else, and pandas imports
      it when it exists; revised after the ninth review, fix pass 9, item K1, review J claim 1: this said a folder
      must be committed as it is)
    - sys.modules holds a module loaded from <repo>/tools that is not one of the closure's tools files (fix pass 5;
      fix pass 8, item J3: a tools/gettext.py that removed its own file after argparse imported it)
  in check(), in this order:
    - a module of the scorer's closure was loaded from anywhere but the repository, or a Python path entry put another
      checkout first (tools/prereg.py check_loaded)
    - a file does not match its .sha256 line, or is not committed, or differs from the committed file, or a symlink
      lies on its path (tools/prereg.py `committed`)
    - <id>.result.json or <id>.sessions.csv exists: it was scored
    - the scorer's SHA-256 (tools/prereg.py scorer_closure: the repository files the scorer imports, found from the
      source; other code is not hashed, fix pass 5, item G5) is not the one the pre-registration names, or one of
      those files is not committed as it is; or score() was given a module root whose closure files are not the
      repository's byte for byte (fix pass 6, item H2)
    - a library the scorer imports, or Python itself, has another version than the one it names
    - the store's tables are not the ones it names
    - its fragile band is not two numbers 0 < lo < hi < 1 (fix pass 4, item F1)
    - spent.jsonl is not committed as it is
    - the repository is shallow, or a window of the spec shares a date with a spent window: in the working
      spent.jsonl, in its side ledger in the git common directory, or in any version of spent.jsonl git can reach
      (the index, every branch, tag, stash and reflog entry; tools/prereg.py spent_lines)
  under the ledgers' lock, just before the first spent line: a window is spent (again), or sys.modules holds a module
  loaded from <repo>/tools that is not a closure file (check_tools_modules again; by then check() has imported every
  closure module and library, and the store's calendar has been read; fix pass 6, item H1).
Then, under that lock, it appends a "spent" line for every window of the spec to the side ledger and to spent.jsonl,
before the result is computed (fix pass 2, review B claim 1); computes the result in memory; appends a "result" line
(its SHA-256) to both; writes <id>.result.json and the per-session file <id>.sessions.csv; and prints the result.
Kinds: "forecast_test" (tools/forecast_test.py).

The entries of tools/ these checks read (tools_entries; revised after the eighth review, fix pass 8, items J1 and J2):
every folder, and every file whose name ends with an import suffix (.py, .pyc, an extension module's suffix). A file's
module name is its name less the longest import suffix; a folder's is its name. They leave out an entry whose module
name holds a dot (tools/prereg.old.py, tools/.mypy_cache/), which no finder loads under any name, and tools/__pycache__,
Python's bytecode cache: Python writes it when the scorer imports its modules, git ignores it, and PathFinder also finds
a __pycache__ namespace package in the standard library, so reading it would refuse every run. `import __pycache__` can
load it; no check reads what it holds. A name with a hyphen is read (sysconfig imports
_sysconfigdata__linux_aarch64-linux-gnu by name).

These checks are tripwires, not a sandbox (revised after the seventh review). They catch mistakes and the routes they
name; they do not stop code written to defeat them. Any code that runs in this process before or between the checks
can defeat them: a file put on the import path, a .pth file, an edited library or standard library, a forged .pyc, a
module that removes itself from sys.modules, an edited closure file (it runs before the hash check). These are
examples, not a complete list. Known routes (tests/test_prereg.py shows each but the forged module root, which review H
showed):
  - a tools/ file with a standard-library name that the scorer imports before the first check (tools/gettext.py,
    which argparse imports) runs before check_process refuses it;
  - a committed tools/ file that a library imports when it exists (tools/numexpr.py, which pandas imports) runs before
    the check under the lock. If its import raises ImportError, Python removes it from sys.modules and pandas
    carries on, so no check refuses it and the scorer scores, though its code ran (fix pass 7, item I2; review H L1);
  - a committed tools/ file that is first imported after the spend: nothing checks after the spend;
  - a process that imports this module and calls score() with its own store, days_for or series_for, or with a
    module root whose code compares itself (score() keeps them for the tests; check()).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import inspect
import json
import os
import sys
import sysconfig
from datetime import date, datetime, timezone
from pathlib import Path

CACHE = "__pycache__"
# The closure's modules in tools/: the tools/ files of prereg.scorer_closure(), written out because the check that
# reads them runs before `import prereg` (tests/test_prereg.py checks the two agree; fix pass 7, item I1)
CLOSURE_TOOLS = ("forecast_test", "prereg", "score_prereg")


def tools_entries(tools: Path) -> list[tuple[str, Path]]:
    """(module name, path) for every entry of the folder `tools` that the checks of tools/ read: a folder, or a file
    whose name ends with an import suffix (importlib.machinery.all_suffixes(): .py, .pyc and the extension module
    suffixes). A file's module name is its name less the longest import suffix it ends with
    (forecast_test.cpython-312-aarch64-linux-gnu.so and x.abi3.so give forecast_test and x); a folder's is its name
    (fix pass 8, item J2; review I claim 3 and N1; default taken 2026-11-10, owner can override). An entry is left out
    when its module name holds a dot: no finder loads it under any name (`import prereg` cannot load
    tools/prereg.old.py; tools/report_m1.v2.py, tools/diagrams.bak/, tools/.ipynb_checkpoints/ and tools/.mypy_cache/
    are the same). A name with a hyphen or another character that is not an identifier's is read: __import__ and
    importlib can load it, and sysconfig loads _sysconfigdata__linux_aarch64-linux-gnu so, with tools/ first on
    sys.path (revised after the eighth review: fix pass 7 left out every name that is not an identifier).
    tools/__pycache__ is also left out (fix pass 6): it is Python's bytecode cache, which Python writes when the scorer
    imports its modules and git ignores, and PathFinder finds a namespace package of that name in the standard
    library's and site-packages' __pycache__ folders, so the name check and the commit check would refuse every
    run. `import __pycache__` loads it as a namespace package, and no check reads what it holds (a forged .pyc there
    is a route the module docstring names). Standard library only: name_clashes runs it before `import prereg`."""
    suffixes = sorted(importlib.machinery.all_suffixes(), key=len, reverse=True)
    if not Path(tools).is_dir():
        return []
    out = []
    for entry in sorted(Path(tools).iterdir()):
        suffix = "" if entry.is_dir() else next((s for s in suffixes if entry.name.endswith(s)), None)
        if suffix is None:
            continue
        name = entry.name[:len(entry.name) - len(suffix)]
        if "." not in name and name != CACHE:
            out.append((name, entry))
    return out


def name_clashes(tools: Path) -> str | None:
    """Why `import <name>` may load another entry of `tools` than the one the scorer means, or None (fix pass 7, item
    I1; review H claim 1): an entry (tools_entries) whose module name is a closure module's (CLOSURE_TOOLS) and that
    is not that module's .py file, or two entries that share a module name. In each sys.path folder, Python's finder
    tries a package folder <name>/ (one with an __init__ file), then an extension module <name>.<suffix>, then
    <name>.py, then <name>.pyc: a tools/prereg/ package or a tools/prereg.<extension suffix> file runs in place of
    tools/prereg.py, which the scorer's SHA-256 covers. (A folder without an __init__ file, or a <name>.pyc, beside
    <name>.py does not run in its place; either is refused all the same.) Module names are tools_entries' (fix pass 8,
    item J2): a tools/foo-bar.py and a tools/foo-bar/ share the name 'foo-bar', and a tools/prereg.old.py is not
    read. Standard library only: when this file runs as a script, it runs before `import prereg`."""
    seen: dict[str, Path] = {}
    for name, entry in tools_entries(tools):
        if name in CLOSURE_TOOLS and entry.name != f"{name}.py":
            return (f"{entry} takes the name of the scorer's module {name!r}: `import {name}` can load it in place of "
                    f"{Path(tools) / (name + '.py')}, the file the scorer's SHA-256 covers")
        if name in seen:
            return (f"{seen[name]} and {entry} share the module name {name!r}: an import of {name!r} loads only one "
                    "of them, and which one depends on the finder's order, not on the scorer")
        seen[name] = entry
    return None


if __name__ == "__main__":
    # fix pass 7, item I1: refused before `import prereg` can load an entry of tools/ in place of tools/prereg.py
    _clash = name_clashes(Path(__file__).resolve().parent)
    if _clash is not None:
        print(f"refused: {_clash}", file=sys.stderr)
        sys.exit(2)

import prereg  # noqa: E402
from prereg import PreregError  # noqa: E402


def check(prereg_id: str, store, repo: Path = prereg.REPO, modules_root: Path | None = None) -> dict:
    """The refusals of check() in the module docstring, in that order; returns the spec. `modules_root` is where the
    scorer's modules must be loaded from (prereg.check_loaded): the repository unless a test scores a throwaway copy.
    A module root other than the repository must hold the closure's files byte for byte (fix pass 6, item H2: review
    G scored a repository with an edited copy of the scorer as the module root). That comparison runs in the module
    root's own code (its prereg.file_sha256 and this function), the code it compares, so it catches a mistake, not a
    forgery: review H scored with a module root whose prereg.file_sha256 reported the repository's hash for its own
    edited file (fix pass 7, item I7). Only a direct score() call passes a module root; main() never does."""
    directory = prereg.prereg_dir(repo)
    prereg.check_loaded(repo, modules_root)
    spec = prereg.load(prereg_id, repo)
    for path in prereg.result_paths(prereg_id, directory):
        if os.path.lexists(path):
            raise PreregError(f"{prereg_id}: {path.name} exists: it was scored, and it is scored once")
    closure = prereg.scorer_sha256(repo)
    if spec.get("scorer_sha256") != closure:
        raise PreregError(f"{prereg_id}: the scorer's SHA-256 is {closure}, the pre-registration names "
                          f"{spec.get('scorer_sha256')}: amend it in a new dated file")
    for name in prereg.scorer_closure(repo):
        if not prereg.committed(Path(repo) / name, repo):
            raise PreregError(f"{name} is not committed as it is: the scorer must be the committed code")
        if modules_root is not None and (prereg.file_sha256(Path(modules_root) / name)
                                         != prereg.file_sha256(Path(repo) / name)):
            raise PreregError(f"{Path(modules_root) / name} is not {Path(repo) / name} byte for byte: the code that "
                              "runs must be the code the scorer's SHA-256 covers")
    versions = prereg.library_versions(repo)
    if spec.get("libraries") != versions:
        raise PreregError(f"{prereg_id}: the libraries are {versions}, the pre-registration names "
                          f"{spec.get('libraries')}")
    if spec.get("data") != prereg.store_tables(store):
        raise PreregError(f"{prereg_id}: the store's tables are not the ones it names")
    fragile_band(spec)
    if not prereg.committed(directory / prereg.SPENT, repo):
        raise PreregError(f"{prereg.SPENT} is not committed as it is: commit it before scoring")
    prereg.require_full_history(repo)
    unspent(spec, repo)
    return spec


def unspent(spec: dict, repo: Path) -> None:
    """PreregError when a window of the spec shares a date with a spent window (prereg.spent_by)."""
    for window in spec["windows"]:
        spent = prereg.spent_by(window, repo)
        if spent is not None:
            raise PreregError(f"{spec['id']}: the window {window['name']} shares dates with one spent by "
                              f"{spent['prereg_id']} on {spent['date']}: it is scored once")


def fragile_band(spec: dict) -> tuple[float, float]:
    """The spec's "fragile_band" [lo, hi]: the p-values that the modelling choices of the threshold, not the data,
    decide (tools/forecast_size.py combinations; fix pass 4, item F1). PreregError unless 0 < lo < hi < 1; check()
    reads it before the spend."""
    band = spec.get("fragile_band")
    if not (isinstance(band, list) and len(band) == 2
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in band) and 0 < band[0] < band[1] < 1):
        raise PreregError(f"{spec.get('id')}: the fragile band {band!r} is not [lo, hi] with 0 < lo < hi < 1")
    return float(band[0]), float(band[1])


def forecast_result(spec: dict, series: dict) -> dict:
    """p, the EWC t, the CI and the decision, from the paired series (the spec's "test"). The decision is HAR when p
    is below the registered threshold (spec "threshold", checked on the matched nulls); the result carries it as
    "threshold" and as "alpha" (the key tools/export_app_data.py and the app read), with the matched-null effective
    size next to the p-value (fix pass 2, item 16). It also carries the fragile band and "fragile": true when p lies
    in it, so a p that the modelling choices decide is marked as such (fix pass 4, item F1)."""
    import numpy as np
    from volbt.analytics.inference import ewc_bootstrap, holm

    test, d = spec["test"], np.asarray(series["d"], dtype=float)
    if not d.any():
        # d identically 0 (candidate = benchmark): no EWC t (0/0); the null control of plan section 7 says p = 1.
        out = {"t": 0.0, "se": 0.0, "p": 1.0, "ci": (0.0, 0.0)}
    else:
        out = ewc_bootstrap(d, test["q"], test["block"], test["draws"], seed=test["seed"], level=test["level"])
    threshold = spec["threshold"]
    use_har = out["p"] < threshold
    lo, hi = fragile_band(spec)
    return {"n": int(d.size), "q": test["q"], "block": test["block"], "draws": test["draws"],
            "mean_d": float(d.mean()), "ewc_t": out["t"], "se": out["se"], "p": out["p"],
            "p_holm": float(holm([out["p"]])[0]), "ci": list(out["ci"]), "threshold": threshold,
            "alpha": threshold, "effective_size": spec["effective_size"],
            "worst_simulated_size": spec["size"]["worst"]["high"]["rate"],
            "fragile_band": [lo, hi], "fragile": bool(lo <= out["p"] < hi),
            "decision": "har" if use_har else "naive", "label": spec["metric"]["label"]}


def sessions_csv(days, rows, series) -> str:
    lines = ["t,fit_date,har_flags,yhat_har,yhat_naive,y,qlike_har,qlike_naive,d"]
    for i, (day, row) in enumerate(zip(days, rows)):
        lines.append(",".join([day.isoformat(), row["fit_date"].isoformat() if row["fit_date"] else "",
                               str(row["har_flags"])] + [repr(float(series[k][i])) for k in
                                                         ("har", "naive", "y", "loss_har", "loss_naive", "d")]))
    return "\n".join(lines) + "\n"


def score(prereg_id: str, store, repo: Path = prereg.REPO, days_for=None, series_for=None,
          today: date | None = None, modules_root: Path | None = None) -> dict:
    """Check, spend, compute, write. `days_for(store, window)` -> the window's dates and `series_for(store, days)`
    -> (rows, series) default to tools/forecast_test. The test is computed on the first window; every window of the
    spec is spent. Under the ledgers' lock, just before the first spent line, the windows are checked again and so are
    the modules loaded from tools/ (check_tools_modules; fix pass 6, item H1): by then check() has imported every
    closure module and library, and days_for has read the store's calendar.

    `repo`, `days_for`, `series_for`, `today` and `modules_root` are for the tests, which call score() (main() takes
    the command line only; fix pass 6, item H2). A process that imports this module and calls score() with its own
    store, days_for or series_for scores data of its choosing: like a patch in memory, that is code in the scorer's
    process, which these checks do not stop. A modules_root must hold the repository's closure byte for byte
    (check); that comparison runs in the module root's own code, so it catches a mistake, not a forgery (fix pass 7,
    item I7; review H claim 5)."""
    directory = prereg.prereg_dir(repo)
    spec = check(prereg_id, store, repo, modules_root)
    if spec.get("kind") != "forecast_test":
        raise PreregError(f"{prereg_id}: no scorer for kind {spec.get('kind')!r}")
    window = spec["windows"][0]
    days = (days_for or window_days)(store, window)
    if prereg.dates_sha256(days) != window["dates_sha256"]:
        raise PreregError(f"{prereg_id}: the window's dates are not the ones it names")
    prereg_sha256 = prereg.prereg_hash(prereg_id, directory)
    day = (today or datetime.now(timezone.utc).date()).isoformat()
    with prereg.ledger_lock(repo):
        unspent(spec, repo)                         # again, under the lock: no second scorer between check and spend
        check_tools_modules(Path(modules_root if modules_root is not None else repo))     # again, just before the spend
        for spend in spec["windows"]:
            prereg.append_both(prereg.SPENT, prereg.SIDE_SPENT, {
                "event": "spent", "window": {k: spend[k] for k in ("name", "split", "start", "end")},
                "prereg_id": prereg_id, "prereg_sha256": prereg_sha256,
                "candidates": [c["name"] for c in spec["candidates"]], "date": day}, repo)
    rows, series = (series_for or forecast_series)(store, days)
    result = {"prereg_id": prereg_id, "prereg_sha256": prereg_sha256, "window": window["name"],
              **forecast_result(spec, series)}
    text = json.dumps(result, indent=1, sort_keys=True) + "\n"
    with prereg.ledger_lock(repo):
        prereg.append_both(prereg.SPENT, prereg.SIDE_SPENT, {
            "event": "result", "prereg_id": prereg_id, "prereg_sha256": prereg_sha256,
            "result_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "date": day}, repo)
    result_json, sessions = prereg.result_paths(prereg_id, directory)
    result_json.write_text(text, encoding="utf-8", newline="\n")
    sessions.write_text(sessions_csv(days, rows, series), encoding="utf-8", newline="\n")
    return result


def window_days(store, window: dict) -> list[date]:
    import forecast_test as ft
    from volbt.data.store import session_calendar

    return ft.window(session_calendar(store), date.fromisoformat(window["start"]),
                     date.fromisoformat(window["last_target_end"]))


def forecast_series(store, days):
    import forecast_test as ft

    rows = ft.forecasts(store, days)
    return rows, ft.paired(rows, ft.realised(store, days))


# fix pass 9, item K2 (review J N1): sysconfig imports the module that _PYTHON_SYSCONFIGDATA_NAME names
HIDDEN_PATH_VARIABLES = ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "_PYTHON_SYSCONFIGDATA_NAME")


def stdlib_entries() -> set[Path]:
    """The sys.path entries of the standard library: its folder and the python3XY.zip next to it."""
    stdlib = Path(sysconfig.get_path("stdlib"))
    return {stdlib.resolve(), (stdlib.parent / f"python{sys.version_info[0]}{sys.version_info[1]}.zip").resolve()}


def found_elsewhere(name: str, others: list[str]) -> str | None:
    """Where the module `name` is outside tools/: "the standard library" for a name of sys.stdlib_module_names, else
    where importlib.machinery.PathFinder.find_spec finds it on the sys.path entries `others` (its file, or the folders
    of a namespace package); None when neither has it (fix pass 6, item H1; review G claim 2). This covers the
    libraries the closure imports (numpy, pandas, ...) and the modules they import (pytz, six, dateutil, _duckdb)."""
    if name in sys.stdlib_module_names:
        return "the standard library"
    spec = importlib.machinery.PathFinder.find_spec(name, others)
    if spec is None:
        return None
    return spec.origin or ", ".join(spec.submodule_search_locations or ()) or name


def uncommitted_entries(root: Path) -> list[Path]:
    """The entries of <root>/tools that tools_entries reads (a file with an import suffix, or a folder) and that HEAD
    does not hold as committed (fix pass 6, item H1): a symlink; a file that is not in HEAD with the same bytes
    (prereg.committed); a folder that HEAD does not hold as a folder; and, in a folder that HEAD holds as a folder,
    each file with an import suffix directly in it that is not committed as it is. Files deeper down, and files
    without an import suffix, are not checked: only an import that names a subpackage of the folder loads a deeper
    file (revised after the ninth review, fix pass 9, item K1; review J claim 1 edited a deeper file and added two
    untracked ones, a deeper .py file and a .txt file, and the scorer scored)."""
    root = Path(root)
    suffixes = tuple(importlib.machinery.all_suffixes())
    out = []
    for _, entry in tools_entries(root / "tools"):
        if entry.is_symlink():
            out.append(entry)
        elif entry.is_dir():
            kind = prereg.git(root, "cat-file", "-t", f"HEAD:tools/{entry.name}")
            if kind.returncode != 0 or kind.stdout.decode().strip() != "tree":
                out.append(entry)
                continue
            out += [path for path in sorted(entry.iterdir())
                    if path.name.endswith(suffixes) and not prereg.committed(path, root)]
        elif not prereg.committed(entry, root):
            out.append(entry)
    return out


def check_tools_modules(root: Path, modules: dict | None = None) -> None:
    """PreregError when a module in `modules` (sys.modules by default) was loaded from <root>/tools (its __file__,
    __spec__.origin or a package folder) and is not one of the closure's tools files: code that is not hashed ran in
    this process (fix pass 5, item G5). check_process runs it before any third-party import, and score() again under
    the ledgers' lock just before the first spent line (fix pass 6, item H1; review G claim 2: a tools/pytz.py loaded
    after check_process patched the result). It sees only what `modules` holds when it runs: a module whose import
    raised an exception is not there (Python removes it), though its code ran (fix pass 7, item I2; review H L1)."""
    root = Path(root).resolve()
    modules = sys.modules if modules is None else modules
    closure = {(root / rel).resolve() for rel in prereg.scorer_closure(root) if rel.startswith("tools/")}
    tools_folder = (root / "tools").resolve()
    for name, module in list(modules.items()):
        spec = getattr(module, "__spec__", None)
        places = [getattr(module, "__file__", None), getattr(spec, "origin", None),
                  *(getattr(spec, "submodule_search_locations", None) or [])]
        for place in places:
            if not isinstance(place, str) or not os.path.isabs(place):
                continue
            resolved = Path(place).resolve()
            if resolved.is_relative_to(tools_folder) and resolved not in closure:
                raise PreregError(f"the module {name!r} is loaded from {place}, a file of tools/ outside the scorer's "
                                  "closure: code that is not hashed ran in this process")


def check_process(root: Path, environ=None, path: list[str] | None = None, source: str | None = None,
                  modules: dict | None = None) -> None:
    """PreregError when this process can run code from outside the repository before the scorer's checks, or is not
    the scorer (fix pass 4, item F5; review E claim 3). In this order:
      - PYTHONPATH, PYTHONHOME or PYTHONUSERBASE is set (review E put a json package in front with PYTHONPATH and
        scored a second time), or _PYTHON_SYSCONFIGDATA_NAME is set: it names the module sysconfig imports when
        stdlib_entries calls sysconfig.get_path, so a tools/ file of that name would run there, after the name check
        and before the commit check (fix pass 9, item K2; review J N1: such a file that put the standard library's
        module in its own sys.modules slot and deleted itself scored);
      - an entry of <root>/tools that tools_entries reads (its module docstring says which) has the name of a
        standard-library module or of a module that PathFinder finds on another entry of `path` (found_elsewhere;
        fix pass 5, item G5, and fix pass 6, item H1: review F's tools/gettext.py, which argparse imports before main()
        runs, and review G's tools/pytz.py, which pandas imports after this check). This check comes before the next
        one because stdlib_entries calls sysconfig.get_path, which imports sysconfig's data module by a name with
        hyphens from tools/ when a file there has that name: so a tools/_sysconfigdata__linux_aarch64-linux-gnu.py is
        refused before it runs (fix pass 8, item J2; review I claim 3; revised after the eighth review: it ran first).
        The data module has its default name here, because _PYTHON_SYSCONFIGDATA_NAME is refused first (fix pass 9);
      - an entry of sys.path before the first entry of the standard library is not <root>/tools (the script's
        folder), or main() is defined in a file other than <root>/tools/score_prereg.py (review E's edited copy under
        another file name, which passed every other check);
      - HEAD does not hold an entry of <root>/tools that tools_entries reads (a file with an import suffix, or a
        folder) as committed (uncommitted_entries): for a folder, HEAD must hold it as a folder and every file with an
        import suffix directly in it must be committed as it is; files deeper down, and files without an import
        suffix, are not checked (revised after the ninth review, fix pass 9, item K1). A module named after an optional
        dependency that is not installed, such as tools/numexpr.py, is found nowhere else, and pandas imports it when
        it exists (default taken 2026-11-10, owner can override);
      - a module in `modules` (sys.modules) loaded from <root>/tools that is not one of the closure's tools files
        (check_tools_modules; fix pass 7, item I5). On the scorer's own imports no such module is loaded by then, so
        this refusal needs other code to have run first: a module whose entry the two checks above do not see, as a
        tools/gettext.py that argparse imported and that removed its own file (tested with the scorer as a script:
        fix pass 8, item J3; review I claim 5).
    It runs before any third-party import: a tools/ file that a library imports is refused before it runs, unless it
    is committed and its name is found nowhere else. Such a file runs when the library imports it, after this check;
    score() refuses it under the ledgers' lock if sys.modules still holds it then. A module whose import raised an
    exception is not held, so no check refuses it (fix pass 7, item I2; review H L1: a committed tools/numexpr.py that
    replaced the result and raised ImportError; revised after the seventh review). `environ`, `path`, `source` and
    `modules` default to this process's; tests pass made-up ones. What these checks leave open is in the module
    docstring."""
    root = Path(root).resolve()
    environ = os.environ if environ is None else environ
    path = sys.path if path is None else path
    source = inspect.getsourcefile(main) if source is None else source
    for name in HIDDEN_PATH_VARIABLES:
        if name in environ:
            why = ("it names the module sysconfig imports" if name == "_PYTHON_SYSCONFIGDATA_NAME"
                   else "it can put other code before the scorer's")
            raise PreregError(f"{name} is set ({environ[name]!r}): {why}; unset it to score")
    tools = root / "tools"
    # the name check comes before stdlib_entries: its sysconfig.get_path imports sysconfig's data module with
    # __import__, from tools/ when tools/ holds a file of that name (fix pass 8, item J2; review I claim 3)
    others = [entry for entry in path if Path(entry or ".").resolve() != tools]
    for name, entry in tools_entries(tools):
        place = found_elsewhere(name, others)
        if place is not None:
            raise PreregError(f"{entry} takes the name of the module {name!r} ({place}): tools/ comes first on "
                              "sys.path, so it would run in its place")
    stdlib = stdlib_entries()
    first = next((i for i, entry in enumerate(path) if Path(entry or ".").resolve() in stdlib), None)
    if first is None:
        raise PreregError(f"no sys.path entry is the standard library ({sorted(map(str, stdlib))})")
    for entry in path[:first]:
        if Path(entry or ".").resolve() != tools:
            raise PreregError(f"the sys.path entry {entry!r} comes before the standard library and is not {tools}: "
                              "it can put another module in place")
    if source is None or Path(source).resolve() != root / prereg.SCORER:
        raise PreregError(f"main() is defined in {source}, not {root / prereg.SCORER}: an edited copy of the scorer "
                          "is refused")
    stray = uncommitted_entries(root)
    if stray:
        more = f" ({len(stray) - 1} more entries of tools/ are not either)" if len(stray) > 1 else ""
        raise PreregError(f"{stray[0]} is not committed as it is{more}: code in tools/ that git does not hold can run "
                          "in this process; commit it or remove it")
    check_tools_modules(root, modules)


def main(argv: list[str] | None = None) -> int:
    """The command line, and only it (fix pass 6, item H2; review G claim 2: main(..., repo=, modules_root=) called
    from `python -c` scored another repository with an edited copy of the scorer, and series_for= or store= scored
    made-up data, every check passing). It runs check_process on this repository, then score() with the store that
    --store names. Tests call score() or run this file as a script; the in-process ones replace
    score_prereg.check_tools_modules, because pytest's process holds modules of tools/ outside the closure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prereg_id")
    parser.add_argument("--store", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        check_process(prereg.REPO)
    except PreregError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    from volbt.data.store import Store

    try:
        result = score(args.prereg_id, Store(args.store))
    except PreregError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
