"""The store: parquet files on disk, queried in-process with DuckDB, and the concrete MarketView.

Layout (ADR-0001 §3). Every table is a folder of parquet files under the store root:

    <root>/<table>/part-0.parquet                          an unpartitioned table
    <root>/option_quotes/source=<s>/year=<y>/part-0.parquet  partitioned by source/year

DuckDB is a library, not a server: `connect()` opens an in-memory database whose views
read those files directly, so a query on one year touches only that year's files.

Determinism (ADR-0001 §7). The same input rows must give the same bytes, so a run can be
checked with a hash. The writer therefore sorts every table by its key before writing,
strips the pandas/arrow metadata (it names library versions and index details), and uses
fixed parquet options. Every read has an explicit ORDER BY.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import date
from pathlib import Path
from types import MappingProxyType

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from volbt import config
from volbt.view import LookAheadError, SplitError

# Fixed writer options. zstd at level 3 is small and fast; a fixed row-group size keeps the
# file layout independent of how the rows arrived.
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3
ROW_GROUP_ROWS = 1_000_000


def write_parquet(table: pa.Table, path: Path) -> None:
    """Write one parquet file byte-deterministically, atomically (temp file, then rename)."""
    # Schema metadata holds the pandas version and index layout: not data, and it changes
    # with the library. Without it, equal rows give equal bytes.
    table = table.replace_schema_metadata(None)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp, compression=COMPRESSION, compression_level=COMPRESSION_LEVEL,
                   row_group_size=ROW_GROUP_ROWS, write_statistics=True)
    os.replace(tmp, path)


def write_json(obj, path: Path) -> None:
    """Stable JSON: sorted keys, LF endings, and no NaN (which is not valid JSON)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=1, sort_keys=True, allow_nan=False, default=str) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes, read in 1 MiB chunks so a big file never sits in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def data_fingerprint(paths: list[Path], root: Path) -> str:
    """ADR-0001 §7: SHA-256 over the sorted (path, size, SHA-256) list of input files.

    Paths are taken relative to `root`, so the fingerprint does not depend on where the
    data folder sits on this machine.
    """
    lines = sorted(
        f"{Path(path).resolve().relative_to(Path(root).resolve()).as_posix()}\t"
        f"{Path(path).stat().st_size}\t{file_sha256(Path(path))}"
        for path in paths
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _as_arrow(table) -> pa.Table:
    if isinstance(table, pa.Table):
        return table
    return pa.Table.from_pandas(table, preserve_index=False)


class Store:
    """Read and write the tables under one root folder (default: config.store_dir())."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else config.store_dir()

    def table_dir(self, name: str) -> Path:
        return self.root / name

    def has(self, name: str) -> bool:
        return any(self.table_dir(name).rglob("*.parquet"))

    def tables(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and self.has(p.name))

    def files(self) -> list[Path]:
        """Every parquet file in the store, sorted, for hashing."""
        return sorted(self.root.rglob("*.parquet"))

    def write_table(self, name: str, table, sort_by: tuple[str, ...],
                    partition_by: tuple[str, ...] = ()) -> list[Path]:
        """Replace table `name`: sort by `sort_by`, split by `partition_by`, one file per partition.

        The old folder is removed first, so a partition that no longer exists cannot linger.
        Partition columns are not stored inside the files: the folder names carry them
        (`source=optionsdx/year=2010`), which is the "hive" layout DuckDB reads natively.
        """
        arrow = _as_arrow(table)
        target = self.table_dir(name)
        if target.exists():
            shutil.rmtree(target)
        if arrow.num_rows:
            # Sort once, by partition columns first, so each partition is a contiguous slice.
            arrow = arrow.sort_by([(column, "ascending") for column in (*partition_by, *sort_by)])
        if not partition_by:
            path = target / "part-0.parquet"
            write_parquet(arrow, path)
            return [path]
        written = []
        keys = arrow.select(list(partition_by)).to_pandas().drop_duplicates()
        data_columns = [c for c in arrow.column_names if c not in partition_by]
        for key in keys.itertuples(index=False):
            mask = None
            for column, value in zip(partition_by, key):
                part = pa.compute.equal(arrow[column], pa.scalar(value, arrow.schema.field(column).type))
                mask = part if mask is None else pa.compute.and_(mask, part)
            folder = target.joinpath(*(f"{c}={v}" for c, v in zip(partition_by, key)))
            path = folder / "part-0.parquet"
            write_parquet(arrow.filter(mask).select(data_columns), path)
            written.append(path)
        return written

    def connect(self) -> duckdb.DuckDBPyConnection:
        """An in-memory DuckDB with one view per stored table."""
        con = duckdb.connect()
        for name in self.tables():
            glob = (self.table_dir(name) / "**" / "*.parquet").as_posix()
            # hive_partitioning turns `source=optionsdx/year=2010` folders back into columns.
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{glob}', "
                        "hive_partitioning = true, hive_types_autocast = false)")
        return con

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        with self.connect() as con:
            return con.execute(sql, params or []).df()

    def read_table(self, name: str, order_by: str, where: str = "", params: list | None = None) -> pd.DataFrame:
        """SELECT * from one table. `order_by` is required: every read has an explicit order."""
        clause = f" WHERE {where}" if where else ""
        return self.query(f"SELECT * FROM {name}{clause} ORDER BY {order_by}", params)


# --- the look-ahead and split guard -----------------------------------------------------------
#
# Every check below reads only names of THIS module, bound when it is imported: datetime.date,
# SPLITS and the two error classes. It calls nothing in volbt.view, the one volbt module that
# strategies and signals may import: a function or table read through it at call time is one a
# strategy could rebind, before this module is imported or after (M1 review, round 2: rebinding
# `volbt.view.exact_date` to add a day moved a Tuesday view to Wednesday, and its bars, dividends
# and VIX with it). This module is out of a strategy's reach: the import test bans `data` there.

# ADR-0010 §1: (first date, last date) of each split, both inclusive. The same table as
# volbt.view.SPLITS, written out again on purpose, so that rebinding that one changes no view;
# tests/test_view.py requires the two to be equal.
SPLITS = MappingProxyType({
    "development": (date(2010, 1, 4), date(2019, 12, 31)),
    "validation": (date(2020, 1, 2), date(2023, 12, 29)),
    "holdout": (date(2024, 1, 2), date(2026, 10, 26)),
})


def plain_date(value: object, what: str) -> date:
    """`value` rebuilt as a plain datetime.date; TypeError for anything else.

    The rule of volbt.view.exact_date, applied with this module's own code: only an object whose
    type IS datetime.date passes (a subclass could answer `>` with whatever it likes, and a
    datetime or Timestamp would be truncated by its time of day), and the date is rebuilt from
    its year, month and day, so the date that is checked is the date that reaches the SQL.
    """
    if type(value) is not date:
        raise TypeError(f"{what} must be a datetime.date, not {type(value).__module__}.{type(value).__qualname__}"
                        " (pass a plain date: .date() of a datetime or Timestamp)")
    return date(value.year, value.month, value.day)


def check_split(as_of: date, split: str) -> date:
    """Raise SplitError if `as_of` is after the last date of `split`. Returns as_of rebuilt."""
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; expected one of {sorted(SPLITS)}")
    day = plain_date(as_of, "as_of")
    last = SPLITS[split][1]
    if day > last:
        raise SplitError(f"as_of {day} is after the end of the {split} split ({last})")
    return day


def check_not_after(requested: date, as_of: date, what: str) -> date:
    """Raise LookAheadError if a read asks for a date after `as_of`. Returns the date to read.

    Both dates are rebuilt by plain_date first, so the comparison is datetime.date's own, and
    the caller must pass the RETURNED date on to the query, never `requested` itself.
    """
    day, limit = plain_date(requested, what), plain_date(as_of, "as_of")
    if day > limit:
        raise LookAheadError(f"{what} for {day} requested from a view at as_of {limit}")
    return day


# The only SQL a view ever runs. Each query reads one table and ends with the bound
# `<= as_of`, whose value the reader in view() supplies itself: a caller passes the other
# parameters, never the bound. Columns are named, so a new column in a table is not served
# until someone decides it is safe to serve.
VIEW_SQL = {
    "sessions": "SELECT date FROM spy_bars WHERE date <= ? ORDER BY date",
    # No adj_close: a dividend-adjusted price on day t is scaled by every dividend paid AFTER t,
    # so its level encodes the future (at 2015-01-02, adj/close equals the product of the 47
    # later dividend factors to 6 digits).
    "spy_bars": "SELECT date, open, high, low, close, volume FROM spy_bars WHERE date <= ? ORDER BY date",
    "dividends": "SELECT ex_date, amount FROM dividends WHERE ex_date <= ? ORDER BY ex_date",
    "rates": "SELECT date, dgs3mo_pct, r_cc FROM rates WHERE date <= ? ORDER BY date",
    "vix": "SELECT date, open, high, low, close FROM vix WHERE date <= ? ORDER BY date",
    # year = ? lets DuckDB skip every other year's files (partition pruning).
    "chain": ("SELECT * FROM option_quotes WHERE source = ? AND year = ? AND quote_date = ? "
              "AND quote_date <= ? ORDER BY osi_symbol"),
}


class StoreView:
    """The concrete MarketView (protocol in volbt.view). The engine creates it with `view()`.

    It holds NO public reference to the store. The only route to the data is the private
    `_read`, a closure that runs one of VIEW_SQL's fixed queries with the view's own as_of
    as the bound, so even code that reaches `_read` (through a private-attribute read the
    import-boundary test bans in strategies and signals) reads nothing after as_of. The Store
    object sits in that closure's cell: reachable only by reflection (`__closure__`,
    `__globals__`, inspect, gc), which the same test bans there. A test walks every public
    attribute to check that no object from `volbt.data` is reachable.
    """

    # __slots__: no instance __dict__, so nothing can be attached to a view by accident.
    __slots__ = ("_as_of", "_split", "_read")

    def __init__(self, as_of: date, split: str, read) -> None:
        self._as_of = as_of
        self._split = split
        self._read = read

    @property
    def as_of(self) -> date:
        return self._as_of

    @property
    def split(self) -> str:
        return self._split

    def sessions(self) -> list[date]:
        bars = self._read("sessions")
        return [d.date() if hasattr(d, "date") else d for d in bars["date"]]

    def chain(self, quote_date: date, source: str = "optionsdx") -> pd.DataFrame:
        # The date read is the one check_not_after returns: a plain date rebuilt from the argument.
        day = check_not_after(quote_date, self._as_of, "option chain")
        return self._read("chain", source, str(day.year), day)

    def spy_bars(self) -> pd.DataFrame:
        return self._read("spy_bars")

    def dividends(self) -> pd.DataFrame:
        return self._read("dividends")

    def rates(self) -> pd.DataFrame:
        return self._read("rates")

    def vix(self) -> pd.DataFrame:
        return self._read("vix")


def view(as_of: date, split: str, store: Store | None = None) -> StoreView:
    """Create the view for one session. Raises SplitError if as_of is past the split's end.

    as_of must be a plain datetime.date (plain_date above); it is rebuilt before use. The
    split check, and the bound every query of the view carries, use only this module's code.
    """
    day = check_split(as_of, split)
    source = store if store is not None else Store()

    def read(name: str, *params) -> pd.DataFrame:
        if name not in VIEW_SQL:
            raise ValueError(f"a view runs only its own queries {sorted(VIEW_SQL)}, not {name!r}")
        sql = VIEW_SQL[name]
        if sql.count("?") != len(params) + 1:
            raise TypeError(f"view query {name!r} takes {sql.count('?') - 1} parameters, not {len(params)}")
        return source.query(sql, [*params, day])

    return StoreView(day, split, read)
