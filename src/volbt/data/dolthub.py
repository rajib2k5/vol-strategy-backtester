"""DoltHub `post-no-preference/options`: every dolt call runs in OUR PRIVATE MIRROR of the clone.

The clone at config.dolthub_options_dir() is SHARED with other projects. On dolt 2.6.1 even
a plain SELECT, or `dolt status`, rewrites files in the database it runs in (measured
2026-10-29: `noms/manifest`, `noms/journal.idx`, the journal and the `stats/` files get new
modification times, with the same bytes, and `.dolt/tmp/` appears). Two projects querying
one clone would contend for those files. So the project-wide rule from 2026-10-29 is: never
run dolt in the shared clone. Each project copied it once (`cp -a`) and queries only its own
copy, here config.dolthub_mirror_dir(). dolt's housekeeping writes land in the mirror, which
is ours. (Until 2026-10-29 M1 ran dolt on an `unshare` overlay of the clone; the mirror
replaced it.)

Three guards:
- `run_dolt` refuses a mirror path that resolves inside a shared clone (SharedCloneError: the
  default clone is refused whatever VOL_DATA_DIR says, config.shared_clones), or anywhere but
  under this project's cache folder (MirrorPathError), before any process starts;
- every SQL string goes through `assert_read_only_sql`, which refuses writes (a guard on our
  own code: we never mean to change even the mirror's data);
- the export runs `dolt status` on the mirror before and after, and refuses to read from a
  mirror, or write the parquet of one, whose working tree is not clean (DirtyMirrorError).
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv

from volbt import config
from volbt.config import SharedCloneError
from volbt.data.schema import check_dolthub_rows_header, check_dolthub_schema
from volbt.data.store import write_json, write_parquet

# Words that would make a statement write. "CALL DOLT_" covers dolt's stored procedures
# (DOLT_COMMIT, DOLT_ADD, DOLT_GC...), which write without saying INSERT. These five are the
# ADR-0009 list; the read-only test checks the loader's SQL against them.
BANNED_SQL = ("INSERT", "UPDATE", "DELETE", "CALL DOLT_", "COMMIT")
# Also refused, because each is a way round the list above:
#   DOLT_  dolt also runs its procedures as functions: `SELECT DOLT_COMMIT('-am', 'x')` starts
#          with SELECT, and the "_" before COMMIT hides the word from a word-boundary match.
#   INTO   `SELECT ... INTO OUTFILE` writes a file.
BANNED_EXTRA = ("DOLT_", "INTO")
ALLOWED_SQL_START = ("SELECT", "SHOW", "DESCRIBE")

# Every SQL statement this loader sends. The read-only test checks each one.
SQL_DESCRIBE = "DESCRIBE option_chain"
SQL_SPY_ROWS = (
    "SELECT `date`, act_symbol, expiration, strike, call_put, bid, ask, vol, delta, gamma, theta, vega, rho "
    "FROM option_chain WHERE act_symbol = 'SPY' "
    "ORDER BY `date`, expiration, strike, call_put"
)
LOADER_SQL = (SQL_DESCRIBE, SQL_SPY_ROWS)

# dolt status must say exactly this before and after an export.
CLEAN_STATUS = "nothing to commit, working tree clean"

# The column types we give the CSV that dolt prints. Decimals become float64: every price is
# a whole number of cents (decimal(7,2)), so cents can be recovered exactly with round(x*100).
SPY_CSV_TYPES = {
    "date": pa.date32(), "act_symbol": pa.string(), "expiration": pa.date32(),
    "strike": pa.float64(), "call_put": pa.string(), "bid": pa.float64(), "ask": pa.float64(),
    "vol": pa.float64(), "delta": pa.float64(), "gamma": pa.float64(), "theta": pa.float64(),
    "vega": pa.float64(), "rho": pa.float64(),
}


class UnsafeSqlError(ValueError):
    """The SQL could write to the database."""


class DoltUnavailable(RuntimeError):
    """dolt is not on PATH, so nothing was run."""


class DirtyMirrorError(RuntimeError):
    """`dolt status` on the mirror was not clean, so its rows were not exported."""


class MirrorPathError(ValueError):
    """The dolt target does not resolve under this project's cache folder, config.project_cache_dir()."""


def assert_read_only_sql(sql: str) -> None:
    """Refuse any statement that is not a plain SELECT, SHOW or DESCRIBE, or that names a write."""
    text = " ".join(sql.split()).upper()
    if not text.startswith(ALLOWED_SQL_START):
        raise UnsafeSqlError(f"only SELECT, SHOW or DESCRIBE may be sent to dolt: {sql!r}")
    for word in (*BANNED_SQL, *BANNED_EXTRA):
        # Word boundaries: a column called `updated_at` must not trip "UPDATE". A word ending in
        # "_" (CALL DOLT_, DOLT_) is a prefix, so it gets no boundary after it.
        if re.search(r"\b" + re.escape(word) + (r"\b" if word[-1].isalpha() else ""), text):
            raise UnsafeSqlError(f"{word!r} is not allowed in SQL sent to dolt: {sql!r}")
    if ";" in text.rstrip(";"):
        raise UnsafeSqlError(f"one statement per call: {sql!r}")


def mirror_dir(path: Path | None = None) -> Path:
    """The dolt database to run in: `path`, else config.dolthub_mirror_dir(), never a shared clone.

    Two checks, both on the path with `~`, symlinks and `..` resolved: it is not inside any
    shared clone (config.shared_clones), and it lies under config.project_cache_dir(), where
    this project's mirror lives. A folder anywhere else is not ours to run dolt in.
    """
    mirror = Path(path) if path is not None else config.dolthub_mirror_dir()
    if config.inside_shared_clone(mirror):
        raise SharedCloneError(f"{mirror} resolves inside a shared DoltHub clone "
                               f"{[str(c) for c in config.shared_clones()]}; dolt runs only in the private mirror")
    cache = config.project_cache_dir().resolve()
    if not Path(mirror).expanduser().resolve().is_relative_to(cache):
        raise MirrorPathError(f"{mirror} does not resolve under this project's cache folder {cache}; "
                              "dolt runs only in the private mirror there")
    return mirror


def dolt_root(work: Path) -> Path:
    """dolt's own home (DOLT_ROOT_PATH) inside work_dir, with telemetry switched off.

    Without this, dolt writes its global config and metrics events to ~/.dolt, outside the repo.
    """
    root = work / "dolt_root"
    settings = root / ".dolt" / "config_global.json"
    if not settings.exists():
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text('{"metrics.disabled":"true"}', encoding="utf-8")
    return root


def run_dolt(args: list[str], mirror: Path | None = None, work: Path | None = None,
             timeout: float = 3600.0) -> str:
    """Run `dolt <args>` inside the private mirror and return its stdout.

    The mirror check comes first, so a path inside the shared clone never gets as far as a
    process. work_dir() refuses a work folder inside the clone for the same reason.
    """
    target = mirror_dir(mirror)
    work_root = Path(work) if work is not None else config.work_dir()
    if config.inside_shared_clone(work_root):
        raise SharedCloneError(f"the work folder {work_root} resolves inside a shared DoltHub clone")
    if shutil.which("dolt") is None:
        raise DoltUnavailable("`dolt` is not on PATH; dolt was not run")
    if not (target / ".dolt").is_dir():
        raise FileNotFoundError(f"no dolt database at {target}: make the mirror with "
                                f"cp -a {config.dolthub_options_dir()} {target}")
    env = {**os.environ, "DOLT_ROOT_PATH": str(dolt_root(work_root))}
    result = subprocess.run(["dolt", *args], cwd=target, env=env, capture_output=True, text=True,
                            timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"dolt {' '.join(args[:1])} failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def dolt_sql(sql: str, mirror: Path | None = None, work: Path | None = None) -> str:
    """Run one read-only statement in the mirror; return the CSV text dolt prints."""
    assert_read_only_sql(sql)
    return run_dolt(["sql", "--result-format", "csv", "--query", sql], mirror, work)


def dolt_status(mirror: Path | None = None, work: Path | None = None) -> str:
    return run_dolt(["status"], mirror, work)


def parse_describe(csv_text: str) -> list[tuple[str, str]]:
    """(Field, Type) pairs from the CSV that `DESCRIBE option_chain` prints."""
    table = pacsv.read_csv(io.BytesIO(csv_text.encode("utf-8")))
    return list(zip(table["Field"].to_pylist(), table["Type"].to_pylist()))


def parse_spy_rows(csv_text: str) -> pa.Table:
    """The SPY rows as a typed table. Empty cells (dolt prints NULL as nothing) become nulls."""
    # include_columns would drop an extra column and fix the order, so check the header itself first.
    check_dolthub_rows_header(csv_text.split("\n", 1)[0], "dolthub SPY rows")
    options = pacsv.ConvertOptions(column_types=SPY_CSV_TYPES, strings_can_be_null=True,
                                   include_columns=list(SPY_CSV_TYPES))
    table = pacsv.read_csv(io.BytesIO(csv_text.encode("utf-8")), convert_options=options)
    return table


def long_rows_sql(parquet: Path) -> str:
    """DuckDB SQL: the exported SPY rows as raw long rows (quotes.RAW_COLUMNS).

    DoltHub has no last price, volume, sizes or underlying, so those are NULL. 'Call'/'Put'
    become 'C'/'P'; any other value fails the CAST to the enum and stops the build.
    """
    return f"""
    SELECT
        'dolthub' AS source,
        "date" AS vendor_date,
        expiration AS expiry,
        strike,
        CASE CAST(call_put AS ENUM ('Call', 'Put')) WHEN 'Call' THEN 'C' ELSE 'P' END AS call_put,
        bid, ask,
        CAST(NULL AS DOUBLE) AS last,
        CAST(NULL AS DOUBLE) AS volume,
        CAST(NULL AS BIGINT) AS bid_size,
        CAST(NULL AS BIGINT) AS ask_size,
        vol AS vendor_iv,
        delta AS vendor_delta, gamma AS vendor_gamma, vega AS vendor_vega,
        theta AS vendor_theta, rho AS vendor_rho,
        CAST(NULL AS DOUBLE) AS underlying_last
    FROM read_parquet('{Path(parquet).as_posix()}')
    WHERE act_symbol = 'SPY'"""


def _require_clean(status: str, when: str) -> None:
    if CLEAN_STATUS not in status:
        raise DirtyMirrorError(f"dolt status on the mirror {when} the export is not clean: {status!r}")


def export_spy_rows(dest: Path, mirror: Path | None = None, work: Path | None = None) -> dict:
    """Export every SPY row of option_chain from the mirror to `dest` (parquet).

    Steps: `dolt status` (must be clean, or nothing is read), check the 13-column schema, run
    the one SELECT, `dolt status` again (must be clean, or the parquet is not written).
    Returns the evidence, which is also written next to `dest` as JSON.
    """
    started = time.monotonic()
    status_before = dolt_status(mirror, work)
    _require_clean(status_before, "before")
    describe_csv = dolt_sql(SQL_DESCRIBE, mirror, work)
    check_dolthub_schema(parse_describe(describe_csv), "dolthub option_chain")
    table = parse_spy_rows(dolt_sql(SQL_SPY_ROWS, mirror, work))
    status_after = dolt_status(mirror, work)
    evidence = {
        "sql": list(LOADER_SQL),
        "rows": table.num_rows,
        "ran_in": "the private mirror, config.dolthub_mirror_dir()" if mirror is None else "a mirror passed in",
        "dolt_status_before": status_before,
        "dolt_status_after": status_after,
        "wall_seconds": round(time.monotonic() - started, 1),
    }
    write_json(evidence, dest.with_suffix(".export.json"))
    _require_clean(status_after, "after")
    write_parquet(table, dest)
    return evidence
