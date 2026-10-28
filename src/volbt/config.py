"""Where raw vendor data lives on this machine.

Raw vendor data (Kaggle downloads, DoltHub option chains) is big and often
licensed, so it lives OUTSIDE the repo and is never committed. Code asks this
module for a path instead of hard-coding one, so the same code runs on any
machine: set VOL_DATA_DIR to point somewhere else.

The directories are not created here and need not exist. Asking "where would
the data be?" must never have side effects; the code that downloads data
creates the folder when it actually needs it.
"""

from __future__ import annotations

import os
from pathlib import Path

# The env var that overrides the default, and the default itself.
ENV_VAR = "VOL_DATA_DIR"
DEFAULT_DATA_DIR = "~/data/vol-projects"


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
    """Where the DoltHub options database is cloned: <data_dir>/dolthub/options."""
    return data_dir() / "dolthub" / "options"
