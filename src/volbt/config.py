"""Where data lives on this machine: vendor sources outside the repo, our own output inside it.

Two kinds of data, two roots:

    data_dir()   the vendor SOURCES (Kaggle downloads, the DoltHub clone). Big, licensed,
                 sometimes shared with other projects, so they live OUTSIDE the repo and
                 we only ever read them. Override with VOL_DATA_DIR.
    work_dir()   everything this project WRITES: downloads (raw/) and built tables
                 (store/). It is the repo's own data/ folder, which .gitignore keeps out
                 of git. Override with VOLBT_WORK_DIR. (Default taken 2026-10-29: this
                 project writes only inside its repo. The owner can override it.)

One exception to "we only read under data_dir()": dolthub_mirror_dir(), this project's own
copy of the shared DoltHub clone (a project-wide rule from 2026-10-29: dolt rewrites files
in a clone even to answer a SELECT, so every project queries a private copy). The mirror is
ours, and lives under project_cache_dir(); the shared clone is never touched. "The shared
clone" is every path in shared_clones(): the one data_dir() names AND the default
~/data/vol-projects/dolthub/options, whatever VOL_DATA_DIR or HOME say (M1 review, round 2:
with VOL_DATA_DIR pointed elsewhere, the real clone passed as a mirror and as a work folder).

Code asks this module for a path instead of hard-coding one, so the same code runs on
any machine.

The directories are not created here and need not exist. Asking "where would
the data be?" must never have side effects; the code that downloads data
creates the folder when it actually needs it.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import pwd                    # the account database: the home folder whatever $HOME says
except ImportError:               # not on Windows
    pwd = None

# The env var that overrides the default, and the default itself.
ENV_VAR = "VOL_DATA_DIR"
DEFAULT_DATA_DIR = "~/data/vol-projects"
# Where the shared clone sits by default, under the default data_dir().
DEFAULT_CLONE = "~/data/vol-projects/dolthub/options"
# This project's folder under data_dir(), where its private dolt mirror lives.
PROJECT_NAME = "vol-strategy-backtester"


class SharedCloneError(ValueError):
    """A path we would write to, or run dolt in, resolves inside the shared DoltHub clone."""

# The same pair for our own output. The repo root is three levels up from this file:
# src/volbt/config.py -> parents[0] = src/volbt, [1] = src, [2] = the repo.
WORK_ENV_VAR = "VOLBT_WORK_DIR"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORK_DIR = REPO_ROOT / "data"


def data_dir() -> Path:
    """Root folder for all raw data: $VOL_DATA_DIR, else ~/data/vol-projects."""
    # `or` (not a get-default) so an empty VOL_DATA_DIR="" also falls back;
    # Path("") would silently mean "the current directory".
    raw = os.environ.get(ENV_VAR) or DEFAULT_DATA_DIR
    # expanduser() turns a leading "~" into the home folder. Path does not do
    # that by itself, so "~/x" would otherwise be a relative folder named "~".
    return Path(raw).expanduser()


def kaggle_dir() -> Path:
    """Where Kaggle downloads go: <data_dir>/kaggle."""
    return data_dir() / "kaggle"


def dolthub_options_dir() -> Path:
    """The SHARED DoltHub options clone: <data_dir>/dolthub/options. Never run dolt in it."""
    return data_dir() / "dolthub" / "options"


def project_cache_dir() -> Path:
    """This project's own folder under data_dir(): <data_dir>/vol-strategy-backtester/cache."""
    return data_dir() / PROJECT_NAME / "cache"


def dolthub_mirror_dir() -> Path:
    """Our private copy of that clone: <data_dir>/vol-strategy-backtester/cache/dolt_mirror/options.

    Every dolt call runs here (volbt.data.dolthub), and dolt may run only under
    project_cache_dir(). It was made once with `cp -a` of the shared clone; dolt's own
    housekeeping writes land in it, which is fine: nobody else reads it.
    """
    return project_cache_dir() / "dolt_mirror" / "options"


def shared_clones() -> list[Path]:
    """Every path that is the shared clone, resolved: never written, never a place to run dolt.

    The clone under data_dir(), and the default clone under the home folder twice over: as $HOME
    says, and as the account database says. So no setting of VOL_DATA_DIR or HOME makes the real
    clone look like any other folder.
    """
    clones = [dolthub_options_dir(), Path(DEFAULT_CLONE).expanduser()]
    if pwd is not None:
        try:
            home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        except KeyError:          # a uid with no account entry (some containers)
            home = None
        if home is not None:
            clones.append(home / Path(DEFAULT_CLONE).relative_to("~"))
    # resolve() also works for a path that does not exist yet (strict=False is the default).
    return [clone.resolve() for clone in clones]


def inside_shared_clone(path: Path) -> bool:
    """True if `path`, with `~`, symlinks and `..` resolved, is a shared clone or lies inside one."""
    resolved = Path(path).expanduser().resolve()
    return any(resolved.is_relative_to(clone) for clone in shared_clones())


def work_dir() -> Path:
    """Root folder for everything we write: $VOLBT_WORK_DIR, else the repo's data/ folder.

    Raises SharedCloneError if it resolves inside the shared DoltHub clone: everything below
    it is written to, and the clone must never be.
    """
    # Same two guards as data_dir(): an empty value falls back, and "~" is expanded.
    raw = os.environ.get(WORK_ENV_VAR)
    work = Path(raw).expanduser() if raw else DEFAULT_WORK_DIR
    if inside_shared_clone(work):
        raise SharedCloneError(f"{WORK_ENV_VAR}={work} is inside a shared DoltHub clone "
                               f"{[str(c) for c in shared_clones()]}; point it anywhere else")
    return work


def raw_dir() -> Path:
    """Downloads, kept exactly as received: <work_dir>/raw."""
    return work_dir() / "raw"


def store_dir() -> Path:
    """Built tables (parquet, read with DuckDB): <work_dir>/store."""
    return work_dir() / "store"
