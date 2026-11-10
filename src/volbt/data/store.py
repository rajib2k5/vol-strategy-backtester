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
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from volbt import config
from volbt.view import LookAheadError, SplitError

# Fixed writer options. zstd at level 3 is small and fast; a fixed row-group size keeps the
# file layout independent of how the rows arrived.
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3
ROW_GROUP_ROWS = 1_000_000
WRITE_STATISTICS = True


def write_settings() -> dict:
    """The parquet writer's options, read when called: the bytes of every file depend on them.

    The pricing build fingerprints them (volbt.build.code_fingerprint), so changing one re-prices
    every partition instead of leaving files written under the old settings beside new ones.
    """
    return {"compression": COMPRESSION, "compression_level": COMPRESSION_LEVEL, "row_group_rows": ROW_GROUP_ROWS,
            "write_statistics": WRITE_STATISTICS}


def write_parquet(table: pa.Table, path: Path) -> None:
    """Write one parquet file byte-deterministically, atomically (temp file, then rename)."""
    # Schema metadata holds the pandas version and index layout: not data, and it changes
    # with the library. Without it, equal rows give equal bytes.
    table = table.replace_schema_metadata(None)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    settings = write_settings()
    pq.write_table(table, tmp, compression=settings["compression"], compression_level=settings["compression_level"],
                   row_group_size=settings["row_group_rows"], write_statistics=settings["write_statistics"])
    os.replace(tmp, path)


def write_json(obj, path: Path) -> None:
    """Stable JSON: sorted keys, LF endings, and no NaN (which is not valid JSON)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=1, sort_keys=True, allow_nan=False, default=str) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def read_json(path: Path):
    """The JSON object in `path`, or None when there is no such file."""
    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


class InconsistentStore(ValueError):
    """The store's folders are not what its writer leaves: a symlink, a stray file, a half-written partition."""


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

    def partitions(self, name: str) -> list[dict[str, str]]:
        """The hive partitions of table `name`, sorted: [{"source": "dolthub", "year": "2020"}, ...]."""
        found = []
        for path in sorted(self.table_dir(name).rglob("*.parquet")):
            folders = path.parent.relative_to(self.table_dir(name)).parts
            found.append(dict(part.split("=", 1) for part in folders))
        return found

    def checked_partitions(self, name: str, columns: tuple[str, ...] = ("source", "year")) -> list[dict[str, str]]:
        """The hive partitions of table `name`, sorted, after checking the folder is exactly what
        write_partition leaves: <columns[0]>=<v>/<columns[1]>=<v>/part-0.parquet and nothing else.

        Raises InconsistentStore, reading only, on: a symlink anywhere in the table (the table folder
        itself included), a path that resolves outside the store root, a file or folder at any other
        place or with any other name, and a partition folder without its part-0.parquet (a crashed
        write leaves part-0.parquet.tmp). Used before the pricing build deletes anything (M2 round 2,
        code claim 1): a deletion planned on a store that is not what the writer left could delete
        live data. A table that does not exist has no partitions.
        """
        table = self.table_dir(name)
        root = self.root.resolve()
        if table.is_symlink():
            raise InconsistentStore(f"{table} is a symlink: the store's tables must be real folders")
        if not table.exists():
            return []
        found = []
        for dirpath, dirnames, filenames in os.walk(table, followlinks=False):
            here = Path(dirpath)
            depth = len(here.relative_to(table).parts)
            for entry in [*dirnames, *filenames]:
                path = here / entry
                if path.is_symlink():
                    raise InconsistentStore(f"{path} is a symlink: the store's tables must be real folders and files")
                if not path.resolve().is_relative_to(root):
                    raise InconsistentStore(f"{path} resolves outside the store root {root}")
            if depth < len(columns):
                column = columns[depth]
                if filenames:
                    raise InconsistentStore(f"{here / filenames[0]}: a file where only {column}=<value> folders belong")
                for folder in dirnames:
                    if not (folder.startswith(f"{column}=") and len(folder) > len(column) + 1):
                        raise InconsistentStore(f"{here / folder}: expected a {column}=<value> folder")
            else:
                if dirnames:
                    raise InconsistentStore(f"{here / dirnames[0]}: a folder inside the partition {here}")
                if filenames != ["part-0.parquet"]:
                    raise InconsistentStore(f"{here}: a partition folder must hold exactly part-0.parquet, "
                                            f"it holds {sorted(filenames)} (a crashed write leaves part-0.parquet.tmp)")
                found.append(dict(part.split("=", 1) for part in here.relative_to(table).parts))
        return sorted(found, key=lambda p: tuple(p[c] for c in columns))

    def checked_table_file(self, name: str) -> Path:
        """The one file of the unpartitioned table `name`, <root>/<name>/part-0.parquet, after checking the
        folder is exactly what write_table leaves: that file and nothing else.

        Raises InconsistentStore, reading only, on: a symlink (the table folder or anything in it), any
        other file (a second parquet, a part-0.parquet.tmp a crashed write leaves, a note), a folder inside
        it, or no part-0.parquet. connect() reads every <name>/**/*.parquet, so a second parquet changes
        what a query of the table returns while a hash of part-0.parquet alone does not change: the M2
        round-4 reviewer's rates/part-1.parquet moved the rate the pricing build used from 0.0522 to 0.0722
        with the summary and the export accepting the store (decision G1). Refused, not hashed: such a
        store is not what the writer left (the rule of checked_partitions).
        """
        table = self.table_dir(name)
        if table.is_symlink():
            raise InconsistentStore(f"{table} is a symlink: the store's tables must be real folders")
        if not table.is_dir():
            raise InconsistentStore(f"{table}: no such table folder (expected {table / 'part-0.parquet'})")
        entries = sorted(table.iterdir())
        for path in entries:
            if path.is_symlink():
                raise InconsistentStore(f"{path} is a symlink: the store's tables must be real folders and files")
        names = [path.name for path in entries]
        path = table / "part-0.parquet"
        if names != ["part-0.parquet"] or not path.is_file():
            raise InconsistentStore(f"{table}: an unpartitioned table's folder must hold exactly the file part-0.parquet, "
                                    f"it holds {names} (a crashed write leaves part-0.parquet.tmp)")
        return path

    def partition_file(self, name: str, partition: dict[str, object]) -> Path:
        """The one parquet file of a partition (it need not exist)."""
        return self.table_dir(name).joinpath(*(f"{c}={v}" for c, v in partition.items()), "part-0.parquet")

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

    def write_partition(self, name: str, table, partition: dict[str, object], sort_by: tuple[str, ...]) -> Path:
        """Replace ONE partition of table `name` (e.g. {"source": "optionsdx", "year": 2023}).

        The other partitions are left as they are, so a build can redo one year without the rest
        (the M2 pricing build runs one partition per process). The same rules as write_table: the
        old folder goes first, rows are sorted by `sort_by`, partition columns live in the folder
        names only. An empty table still writes its (empty) file, so the partition reads as built.
        """
        arrow = _as_arrow(table)
        folder = self.table_dir(name).joinpath(*(f"{column}={value}" for column, value in partition.items()))
        if folder.exists():
            shutil.rmtree(folder)
        if arrow.num_rows:
            arrow = arrow.sort_by([(column, "ascending") for column in sort_by])
        path = folder / "part-0.parquet"
        write_parquet(arrow.select([c for c in arrow.column_names if c not in partition]), path)
        return path

    def delete_partition(self, name: str, partition: dict[str, object]) -> None:
        """Remove ONE partition folder of table `name`, and any folder it leaves empty above it.

        The pricing build uses it for a derived partition whose input partition no longer exists,
        so the tables and their summary describe only the quotes that are there. It refuses
        (InconsistentStore, deleting nothing) a target that is a symlink, lies under one, or resolves
        outside the table's folder in the store root.
        """
        folder = self.table_dir(name).joinpath(*(f"{column}={value}" for column, value in partition.items()))
        for path in (folder, *folder.parents):          # up to the store root, which may itself be a link
            if path == self.root:
                break
            if path.is_symlink():
                raise InconsistentStore(f"refusing to delete {folder}: {path} is a symlink")
        if not folder.resolve().is_relative_to(self.table_dir(name).resolve()) or \
                not self.table_dir(name).resolve().is_relative_to(self.root.resolve()):
            raise InconsistentStore(f"refusing to delete {folder}: it resolves outside {self.table_dir(name)}")
        if folder.exists():
            shutil.rmtree(folder)
        parent = folder.parent
        while parent != self.table_dir(name) and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent

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


# The columns the milestone-3 day reads serve (VIEW_SQL and the year cache serve the same ones).
QUOTE_COLUMNS = ("quote_date", "osi_symbol", "expiry", "strike", "call_put", "bid", "ask", "volume", "spy_close",
                 "quality_flags")
QUOTE_IV_COLUMNS = ("quote_date", "osi_symbol", "expiry", "log_moneyness", "is_otm", "in_smile", "iv", "iv_flags")
FORWARD_COLUMNS = ("quote_date", "expiry", "tau_years", "r_cc", "discount_factor", "spot", "forward", "forward_carry",
                   "method", "flags")
SMILE_COLUMNS = ("quote_date", "expiry", "tau_years", "k_nodes", "total_var_nodes", "n_points", "atm_iv", "fit_flags")
# The day reads: view method -> (table, the day's sort column, the columns served).
DAY_READS = {"chain": ("option_quotes", "osi_symbol", None), "quotes": ("option_quotes", "osi_symbol", QUOTE_COLUMNS),
             "quote_ivs": ("quote_iv", "osi_symbol", QUOTE_IV_COLUMNS),
             "forwards": ("expiry_forwards", "expiry", FORWARD_COLUMNS),
             "smiles": ("smile_fits", "expiry", SMILE_COLUMNS)}
# The reads bounded by `<= as_of`: view method -> (table, date column, the columns served).
UPTO_READS = {"sessions": ("spy_bars", "date", ("date",)),
              "spy_bars": ("spy_bars", "date", ("date", "open", "high", "low", "close", "volume")),
              "dividends": ("dividends", "ex_date", ("ex_date", "amount")),
              "rates": ("rates", "date", ("date", "dgs3mo_pct", "r_cc")),
              "vix": ("vix", "date", ("date", "open", "high", "low", "close"))}


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
    # Milestone 3: the derived tables of one session, and the quote columns the engine needs. The same
    # rule: one source, one year, one quote date, and the view's own bound.
    "quotes": (f"SELECT {', '.join(QUOTE_COLUMNS)} FROM option_quotes WHERE source = ? AND year = ? "
               "AND quote_date = ? AND quote_date <= ? ORDER BY osi_symbol"),
    "quote_ivs": (f"SELECT {', '.join(QUOTE_IV_COLUMNS)} FROM quote_iv WHERE source = ? AND year = ? "
                  "AND quote_date = ? AND quote_date <= ? ORDER BY osi_symbol"),
    "forwards": (f"SELECT {', '.join(FORWARD_COLUMNS)} FROM expiry_forwards WHERE source = ? AND year = ? "
                 "AND quote_date = ? AND quote_date <= ? ORDER BY expiry"),
    "smiles": (f"SELECT {', '.join(SMILE_COLUMNS)} FROM smile_fits WHERE source = ? AND year = ? "
               "AND quote_date = ? AND quote_date <= ? ORDER BY expiry"),
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

    # --- milestone 3: one session's derived tables, for the engine and (from M4) the strategies ----------

    def _day(self, name: str, quote_date: date, source: str, osi_symbols) -> pd.DataFrame:
        day = check_not_after(quote_date, self._as_of, name)
        return self._read(name, source, str(day.year), day, symbols=None if osi_symbols is None else sorted(set(osi_symbols)))

    def quotes(self, quote_date: date, osi_symbols=None, source: str = "optionsdx") -> pd.DataFrame:
        """option_quotes of one session (QUOTE_COLUMNS), all of them or only `osi_symbols`, by osi_symbol."""
        return self._day("quotes", quote_date, source, osi_symbols)

    def quote_ivs(self, quote_date: date, osi_symbols=None, source: str = "optionsdx") -> pd.DataFrame:
        """quote_iv of one session (QUOTE_IV_COLUMNS): log-moneyness, OTM, in_smile, IV, iv_flags."""
        return self._day("quote_ivs", quote_date, source, osi_symbols)

    def forwards(self, quote_date: date, source: str = "optionsdx") -> pd.DataFrame:
        """expiry_forwards of one session (FORWARD_COLUMNS), by expiry; empty on a session with no snapshot."""
        return self._day("forwards", quote_date, source, None)

    def smiles(self, quote_date: date, source: str = "optionsdx") -> pd.DataFrame:
        """smile_fits of one session (SMILE_COLUMNS), by expiry: the nodes the surface is read from."""
        return self._day("smiles", quote_date, source, None)


class YearCache:
    """One source's derived and quote tables, a year at a time, in memory (milestone 3, decision D1).

    Per-day SQL is too slow for a 14-year run: one connect() is 45.6 ms, a day's chain 36-84 ms (the M3
    plan's measurements), so the engine reads a year at once instead. On the first read of a year the cache
    loads that year's option_quotes, quote_iv, expiry_forwards and smile_fits partitions (each its one
    part-0.parquet: the engine checks the store with Store.checked_partitions and checked_table_file before a
    run, volbt.engine.loop.run_inputs) and the reference tables, and keeps the two most recent years. That
    spares a reload of the old year in early January; ADR-0004 rule 4 does not need it, because a stale
    surface is the DaySurface the engine already holds (M3 review: keep = 1 is equivalent for it). A cached
    chain() has the stored columns; the SQL one also has the hive columns source and year.

    It has NO public read method. Only a view's private reader reads it, and the reader applies the view's
    own bound: one quote date that check_not_after has passed, or `date <= as_of`. A strategy holds a view,
    never the cache (the engine keeps the handle). What the cache guarantees about the frames it returns:
    no frame is a view into the cached year. Each one owns all its memory (owned_frame: the day's rows are
    copied out with Table.take, every numpy array once more), so no buffer behind it holds a row it does not
    show, and writing to a frame changes nothing in the cache (M3 round-2 review: zero-copy slices let a
    strategy read 30 sessions ahead). What it does not guarantee: a read past the end of an array still
    reads whatever memory follows, the cached year included (M3 round-3 review: an as_strided read 63 MB
    past a frame's buffer once landed in the live cached year). Nor does it stop code that holds the cache
    itself. The import-boundary rule for strategies and signals (no as_strided, stride_tricks, lib or .base,
    no ctypes, no __array_interface__, __array_struct__ or __array__) is a tripwire against accidents, not a
    sandbox: ADR-0001 test 1.
    """

    __slots__ = ("_store", "_source", "_keep", "_years", "_reference")

    def __init__(self, store: Store, source: str, keep: int = 2) -> None:
        self._store, self._source, self._keep = store, source, keep
        self._years: dict[int, dict] = {}
        self._reference: dict[str, tuple[pd.DataFrame, np.ndarray]] = {}

    def _year(self, year: int) -> dict:
        if year in self._years:
            return self._years[year]
        loaded = {}
        for name, (table, key, columns) in DAY_READS.items():
            if table in loaded:
                continue
            path = self._store.partition_file(table, {"source": self._source, "year": year})
            if not path.is_file():
                loaded[table] = None
                continue
            arrow = pq.read_table(path)
            days = arrow["quote_date"].to_numpy().astype("datetime64[D]").astype(np.int64)
            if days.size and np.any(np.diff(days) < 0):
                arrow = arrow.sort_by([("quote_date", "ascending"), (key, "ascending")])
                days = arrow["quote_date"].to_numpy().astype("datetime64[D]").astype(np.int64)
            loaded[table] = (_dates_as_timestamps(arrow), days)
        self._years[year] = loaded
        while len(self._years) > self._keep:
            del self._years[min(self._years)]
        return loaded

    def _slice(self, name: str, source: str, day: date, symbols=None) -> pd.DataFrame:
        """The rows of `name` dated exactly `day` (the caller has bounded it), as a new DataFrame; with
        `symbols`, only those contracts (filtered before the conversion, which is most of the cost)."""
        if source != self._source:
            raise ValueError(f"this year cache serves {self._source!r}, not {source!r}")
        table, key, columns = DAY_READS[name]
        entry = self._year(day.year)[table]
        if entry is None:
            return pd.DataFrame(columns=list(columns) if columns else [])
        arrow, days = entry
        target = np.datetime64(day, "D").astype(np.int64)
        lo, hi = np.searchsorted(days, target, "left"), np.searchsorted(days, target, "right")
        # Take the day's rows out of a slice of the day (a take over the whole year's chunks cost 0.9 ms a read):
        # the take writes new buffers that hold those rows only, and owned_frame copies them into numpy.
        part = arrow.slice(lo, hi - lo)
        rows = np.arange(hi - lo)
        if symbols is not None:
            wanted = pc.is_in(part["osi_symbol"], value_set=pa.array(list(symbols), type=pa.string()))
            rows = rows[np.asarray(wanted.to_numpy(zero_copy_only=False), dtype=bool)]
        if columns is not None:
            part = part.select(list(columns))
        return owned_frame(part.take(pa.array(rows, type=pa.int64())))

    def _upto(self, name: str, bound: date) -> pd.DataFrame:
        """The rows of a reference table dated on or before `bound`, as a new DataFrame."""
        table, column, columns = UPTO_READS[name]
        if table not in self._reference:
            frame = _dates_as_timestamps(pq.read_table(self._store.checked_table_file(table))).to_pandas()
            frame = frame.sort_values(column, kind="stable").reset_index(drop=True)
            self._reference[table] = (frame, pd.to_datetime(frame[column]).to_numpy().astype("datetime64[D]"))
        frame, days = self._reference[table]
        end = int(np.searchsorted(days, np.datetime64(bound, "D"), "right"))
        return frame.iloc[:end][list(columns)].copy()


def owned_frame(part: pa.Table) -> pd.DataFrame:
    """`part` as a DataFrame that shares no memory with the table it was taken from (M3 round-2 review).

    Table.slice and to_pandas are zero-copy for string and list columns: a day's frame kept views into the whole
    cached year, and np.lib.stride_tricks.as_strided on one smile row read the smiles of the next 30 sessions. So
    `part` must come from Table.take, which copies the rows it selects into buffers of their own (string data,
    offsets, list children); then every numpy array is copied once more, so that the frame owns all its memory
    and a test can measure it: each column's buffer is exactly the frame's rows, each list element its own array.
    """
    frame = part.to_pandas().copy(deep=True)
    for name in frame.columns:
        if frame[name].dtype == object:
            owned = np.empty(len(frame), dtype=object)
            for i, value in enumerate(frame[name]):
                owned[i] = value.copy() if isinstance(value, np.ndarray) else value
            frame[name] = owned
    return frame


def _dates_as_timestamps(table: pa.Table) -> pa.Table:
    """Date columns as timestamp[us], cast once in Arrow, so a cached read converts to the dtype DuckDB's .df()
    gives (datetime64[us]) and equals an SQL read; the cast at load costs nothing per session."""
    for index, column in enumerate(table.schema):
        if pa.types.is_date(column.type):
            table = table.set_column(index, column.name, table.column(index).cast(pa.timestamp("us")))
    return table


def session_calendar(store: Store) -> list[date]:
    """Every SPY session date in the store, future ones included (milestone-3 decision D3).

    The engine reads it once, outside any view: it needs the next session (an order's target fill date,
    a DTE exit, projected ex-dates). Exchange holidays are published in advance, so knowing which future
    weekdays trade is not look-ahead; what it does leak is an UNSCHEDULED closure a day early (2012-10-29/30,
    2018-12-05, 2025-01-09 are absent from spy_bars). Dates only: no price of a future date.
    """
    bars = pq.read_table(store.checked_table_file("spy_bars"), columns=["date"]).to_pandas()
    return sorted(d.date() if hasattr(d, "date") else d for d in bars["date"])


def view(as_of: date, split: str, store: Store | None = None, cache: YearCache | None = None) -> StoreView:
    """Create the view for one session. Raises SplitError if as_of is past the split's end.

    as_of must be a plain datetime.date (plain_date above); it is rebuilt before use. The
    split check, and the bound every query of the view carries, use only this module's code.
    With a YearCache the reader slices the cached year instead of running SQL (milestone 3): the same
    queries, the same bound, applied by this closure itself.
    """
    day = check_split(as_of, split)
    source = store if store is not None else Store()

    def read(name: str, *params, symbols=None) -> pd.DataFrame:
        if name not in VIEW_SQL:
            raise ValueError(f"a view runs only its own queries {sorted(VIEW_SQL)}, not {name!r}")
        sql = VIEW_SQL[name]
        if sql.count("?") != len(params) + 1:
            raise TypeError(f"view query {name!r} takes {sql.count('?') - 1} parameters, not {len(params)}")
        if symbols is not None and name not in ("quotes", "quote_ivs"):
            raise TypeError(f"view query {name!r} takes no symbol filter")
        if cache is None:
            rows = source.query(sql, [*params, day])
            if symbols is not None:
                rows = rows[rows["osi_symbol"].isin(set(symbols))].reset_index(drop=True)
            return rows
        if name in DAY_READS:
            quote_source, _, requested = params
            # The bound again, with this module's code: the slice is one date, and never after as_of.
            return cache._slice(name, quote_source, check_not_after(requested, day, name), symbols)
        return cache._upto(name, day)

    return StoreView(day, split, read)
