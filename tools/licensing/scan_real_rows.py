"""Look for real vendor data copied into the repository. Local only.

    uv run python tools/licensing/scan_real_rows.py                # the repo's text files, from git
    uv run python tools/licensing/scan_real_rows.py --tree DIR     # every text file in DIR, no git

The raw sources it compares against (all read-only, none inside the repo):

* the reference downloads under ``work_dir()/raw``: Cboe ``VIX_History.csv`` and ``VIX3M_History.csv``,
  FRED ``DGS3MO.csv``, yfinance ``SPY_daily.csv`` (text, so rules 1 to 5 all apply);
* the DoltHub SPY export ``work_dir()/raw/dolthub/option_chain_spy.parquet`` (Parquet);
* the OptionsDX files ``kaggle_dir()/spy-eod-2010-2023/*.parquet`` (Parquet, about 9.5M rows).

A repository line is flagged when:

1. it is at least 12 characters long (after stripping), holds a digit, and appears verbatim in a raw text file
   (a CSV header has column names and no digit: that is not data, so rule 1 skips it);
2. it contains a whole raw data row (a raw line that starts with a date, at least 12 characters),
   for example inside a Python bytes literal, where ``\\n`` escapes keep rule 1 from matching;
3. it holds a number with 2 or more decimals and 3 or more significant digits (or an integer of 6
   or more digits, like a volume) that equals, rounded to the number's own decimals, a raw value of
   a date named near it: on the same line within ``NEAR_CHARS`` characters, or on a line up to
   ``NEAR_LINES`` lines away (a dated close typed into a fixture or a doc, also when the date and
   the value sit on different lines of a dict, or the row was partly edited). A date is
   ``2022-06-17``, ``06/17/2022`` or the Python call ``date(2022, 6, 17)`` (also spelled ``D(...)``);
4. it holds an integer of 6 or more digits (thousands separators ``,``, ``_`` or a space allowed)
   equal to the size of a raw file, or to the total size of all raw files, of the four reference
   downloads, of the DoltHub export, or of the OptionsDX files;
5. it holds a 64-hex string equal to the SHA-256 of a raw file (or the one its ``.meta.json`` records).

Parquet has no lines, so rules 1 and 2 read the text files only. Rules 3 to 5 cover Parquet:

* rule 3 uses the OptionsDX price (``C_BID``, ``C_ASK``, ``C_LAST``, ``P_*``), implied-vol (``C_IV``,
  ``P_IV``) and greek columns and ``UNDERLYING_LAST``, and the DoltHub bid, ask, vol and greek columns.
  It does not use strikes, DTE, strike distance or volumes: those are contract terms or counts.
* 9.5M rows with ~30 numeric columns are not indexed in full. The scanner first collects every date
  named anywhere in the files it scans, then reads the Parquet rows of those dates only (DuckDB, a join on the
  date column).
* a day's chain fills nearly every cent of 0.01 to 100 with some bid, ask or last, so one number that
  equals "a value of that day" says nothing: a made-up quote does it most of the time. For the chain
  columns (prices, IV, greeks) rule 3 therefore needs two or more numbers on the line that equal,
  each rounded to its own decimals, cells of one raw row of a date named near them, in columns of
  different kinds (a call IV and a put IV, an IV and a delta; the bid, ask and last of one side are
  one kind, they sit within cents of each other). It also has to be a match that chance rarely
  makes. For each number the scanner estimates ``h``, how many of the day's ``n`` rows chance alone
  would make equal it (the day's cells near it, per step of its last decimal; or the rows it equals
  beyond the first, for a round number the chain repeats). Two or more numbers are expected to meet
  in one row about ``n * (h1/n) * (h2/n) * ...`` times by chance; the line is flagged when that is
  below ``CHANCE`` divided by (pairs of numbers on the line * days searched), because the more
  tries, the likelier a chance match. A bid of 1.21 and an ask of 1.22 are common prices and do not
  reach it; a copied row, or two 4-5 decimal IVs, do. ``UNDERLYING_LAST`` and the text sources have
  one value per date, so one number is enough there. ``--chain-single`` drops the joint test and flags
  one number that equals any chain value (noisy: nearly all hits are coincidences).

Rule 3 can flag a coincidence (a made-up number that happens to equal a real value of a nearby
date); the fix is the same, pick another made-up number.

It prints only ``file:line`` for each flagged line and a count, never the text that matched, so its
output can be pasted anywhere. What it indexed goes to stderr, as counts. Exit 0 clean, 1 something
flagged, 2 no raw data to compare with (also when some source is missing and nothing was flagged:
that is not a clean result). It is not a test: CI has no raw data. Run it before every commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

from volbt import config

MIN_LINE = 12
NEAR_CHARS = 120  # rule 3, same line: a one-line JSON file names many dates far from any value
NEAR_LINES = 3  # rule 3, other lines: a dict or a table row spread over a few lines
LONG_LINE = 300  # a longer line (minified JSON) lends no dates to its neighbours
CHANCE = 0.01  # rule 3, chain columns: flag when chance alone would match this many rows or fewer
WINDOW = 10  # rule 3, chain columns: a number's local density is read from this many cells each side of it

REFERENCE_CSVS = ("cboe/VIX_History.csv", "cboe/VIX3M_History.csv", "fred/DGS3MO.csv", "yfinance/SPY_daily.csv")
DOLTHUB_EXPORT = "dolthub/option_chain_spy.parquet"
OPTIONSDX_DATASET = "spy-eod-2010-2023"

# Quote columns as (name, kind). Bid, ask and last of one side sit within cents of each other, so two of
# them equal two numbers of a line far more often than independence says: they share one kind, and
# rule 3 counts a row only when the numbers fit different kinds. Every other column is its own kind.
DOLTHUB_DATE = "date"
DOLTHUB_QUOTE = (("bid", "price"), ("ask", "price"), ("vol", "vol"), ("delta", "delta"), ("gamma", "gamma"), ("theta", "theta"), ("vega", "vega"), ("rho", "rho"))
DOLTHUB_SINGLE: tuple[str, ...] = ()
OPTIONSDX_DATE = "[QUOTE_DATE]"
OPTIONSDX_QUOTE = tuple(
    (f"[{side}_{field}]", f"{side}_price" if field in ("BID", "ASK", "LAST") else f"{side}_{field}")
    for side in "CP"
    for field in ("BID", "ASK", "LAST", "IV", "DELTA", "GAMMA", "VEGA", "THETA", "RHO")
)
OPTIONSDX_SINGLE = ("[UNDERLYING_LAST]",)  # one value per date

_US_DATE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_PY_DATE = re.compile(r"(?<![\w.])(?:date|D)\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)")  # date(2022, 6, 17)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w|\.\d)")  # "was 379.15." ends in a full stop, not a decimal
_BIG_INT = re.compile(r"(?<![\w.,])\d{1,3}(?:[,_ ]\d{3})+(?![\w.,]?\d)|(?<![\w.,])\d{6,}(?!\w|\.\d)")
_SHA = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])")
_RAW_ALPHABET = re.compile(r"[0-9A-Za-z/.,:^\- ]+")

Dates = list[tuple[int, int, date]]


def _dates_in(text: str) -> Dates:
    """``(start, end, date)`` for every M/D/Y, ISO or ``date(Y, M, D)`` token in ``text`` that is a real calendar date."""
    found = []
    for pattern, order in ((_US_DATE, (2, 0, 1)), (_ISO_DATE, (0, 1, 2)), (_PY_DATE, (0, 1, 2))):
        for match in pattern.finditer(text):
            parts = [int(g) for g in match.groups()]
            try:
                found.append((match.start(), match.end(), date(parts[order[0]], parts[order[1]], parts[order[2]])))
            except ValueError:
                continue
    return sorted(found)


def _significant_digits(token: str) -> int:
    digits = token.lstrip("-").replace(".", "").lstrip("0")
    return len(digits)


def _has_rounded(values: np.ndarray, number: float, decimals: int) -> bool:
    """True if a value of the sorted array ``values``, rounded to ``decimals``, equals ``number``."""
    half = 0.5 * 10.0**-decimals * (1 + 1e-9)
    lo = np.searchsorted(values, number - half, side="left")
    hi = np.searchsorted(values, number + half, side="right")
    return any(round(float(v), decimals) == number for v in values[lo:hi])


def _cells_equal(rows: np.ndarray, number: float, decimals: int) -> dict[int, set[int]]:
    """``{row: {columns}}`` of the cells of ``rows`` that, rounded to ``decimals``, equal ``number``."""
    half = 0.5 * 10.0**-decimals * (1 + 1e-9)
    found: dict[int, set[int]] = defaultdict(set)
    for r, c in np.argwhere(np.abs(rows - number) <= half):  # NaN compares false
        if round(float(rows[r, c]), decimals) == number:
            found[int(r)].add(int(c))
    return found


def _joint(hits: list[tuple[dict[int, set[int]], float]], kinds: tuple[str, ...], n_rows: int, limit: float) -> bool:
    """True if a raw row holds 2 or more of the numbers in columns of different kinds, and chance would rarely do that.

    Each entry of ``hits`` is one number: the rows it equals mapped to the columns it equals there, and
    ``h``, how many rows chance alone would make it equal (see ``_chance_rows``). For one row, the
    numbers that fit it get distinct kinds (the rarest number first) and the expected count of rows that
    chance alone would match is ``n_rows * product(h_i / n_rows)``; flagged when it is below ``limit``.
    """
    by_row: dict[int, list[tuple[float, set[str]]]] = defaultdict(list)
    for found, h in hits:
        for row, columns in found.items():
            by_row[row].append((h, {kinds[c] for c in columns}))
    for items in by_row.values():
        if len(items) < 2:
            continue
        used: set[str] = set()
        expected = float(n_rows)
        placed = 0
        for h, options in sorted(items, key=lambda item: (item[0], len(item[1]))):
            free = options - used
            if free:
                used.add(min(free))
                expected *= min(h / n_rows, 1.0)
                placed += 1
        if placed >= 2 and expected < limit:
            return True
    return False


def _chance_rows(cells: np.ndarray, found: dict[int, set[int]], number: float, decimals: int) -> float:
    """How many rows of the day chance alone would make equal ``number``, at its own decimals.

    Two estimates, the larger one: the day's cells within ``WINDOW`` steps of it (a step is one unit of
    its last decimal), per step, which is the density the number falls in; and the rows it equals
    beyond the first (the match itself is what we selected on, so it counts for nothing), which
    catches round numbers that the whole chain repeats.
    """
    step = 10.0**-decimals
    reach = WINDOW * step * (1 + 1e-9)
    near = np.searchsorted(cells, number + reach, side="right") - np.searchsorted(cells, number - reach, side="left")
    return max(near / (2 * WINDOW + 1), len(found) - 1)


class Chain:
    """One Parquet source, for the wanted dates only: per date its quote rows and its one-value column."""

    def __init__(self, rows: dict[date, np.ndarray], singles: dict[date, np.ndarray], kinds: tuple[str, ...] = ()):
        self.kinds = kinds  # per quote column
        self.rows = rows  # date -> (n rows, n quote columns), NaN where null
        self.singles = singles  # date -> sorted distinct finite values of the one-value-per-date columns
        self._cells: dict[date, np.ndarray] = {}

    def cells(self, day: date) -> np.ndarray | None:
        """Every finite quote cell of ``day``, sorted (duplicates kept)."""
        if day not in self._cells and day in self.rows:
            values = self.rows[day]
            self._cells[day] = np.sort(values[np.isfinite(values)])
        return self._cells.get(day)


def _load_chain(files: list[Path], date_col: str, quote: tuple[tuple[str, str], ...], single_cols: tuple[str, ...], wanted: set[date]) -> tuple[Chain, int, int]:
    """Read the rows of the wanted dates only (a DuckDB join on the date column); also rows and cells kept."""
    if not files or not wanted:
        return Chain({}, {}), 0, 0
    ident = lambda name: '"' + name.replace('"', '""') + '"'  # noqa: E731 - OptionsDX names carry brackets
    days = sorted(wanted)
    quote_cols = [name for name, _ in quote]
    columns = [*quote_cols, *single_cols]
    with tempfile.TemporaryDirectory() as spill:
        con = duckdb.connect()
        try:
            con.execute(f"SET temp_directory = '{spill}'")
            con.execute("CREATE TEMP TABLE wanted (id INTEGER, d VARCHAR)")
            con.executemany("INSERT INTO wanted VALUES (?, ?)", [(i, day.isoformat()) for i, day in enumerate(days)])
            con.execute(
                f"CREATE TEMP TABLE chain AS SELECT wanted.id AS id, {', '.join(ident(c) for c in columns)} "
                f"FROM read_parquet([{', '.join(repr(str(f)) for f in files)}]) AS t "
                f"JOIN wanted ON CAST(t.{ident(date_col)} AS VARCHAR) = wanted.d"
            )
            frame = con.execute("SELECT * FROM chain ORDER BY id").fetchnumpy()
        finally:
            con.close()
    ids = np.asarray(frame["id"])
    matrix = np.column_stack([np.ma.filled(np.ma.asarray(frame[c]).astype(np.float64), np.nan) for c in columns]) if len(ids) else np.empty((0, len(columns)))
    matrix[~np.isfinite(matrix)] = np.nan
    rows: dict[date, np.ndarray] = {}
    singles: dict[date, np.ndarray] = {}
    if len(ids):
        cuts = np.flatnonzero(ids[1:] != ids[:-1]) + 1
        for chunk_ids, chunk in zip(np.split(ids, cuts), np.split(matrix, cuts)):
            day = days[int(chunk_ids[0])]
            rows[day] = chunk[:, : len(quote_cols)]
            one = chunk[:, len(quote_cols) :]
            singles[day] = np.unique(one[np.isfinite(one)])
    return Chain(rows, singles, tuple(kind for _, kind in quote)), len(ids), int(np.isfinite(matrix).sum())


class RawIndex:
    """What rules 1 to 5 compare against, built from the raw files."""

    def __init__(self, work: Path, optionsdx_dir: Path, wanted: set[date], chain_single: bool = False):
        raw = work / "raw"
        self.chain_single = chain_single
        self.notes: list[str] = []  # what was indexed, as counts, for stderr
        self.missing: list[str] = []
        self.texts: list[str] = []
        self.rows_by_prefix: dict[str, list[str]] = defaultdict(list)
        self.values_by_date: dict[date, set[float]] = defaultdict(set)
        self.chains: list[Chain] = []
        self.sizes: set[int] = set()
        self.shas: set[str] = set()
        self.files = 0

        reference = [raw / name for name in REFERENCE_CSVS]
        for path in reference:
            if not path.is_file():
                self.missing.append(str(path))
        self._text_files([p for p in reference if p.is_file()])
        group_sizes = [sum(p.stat().st_size for p in reference if p.is_file())]

        dolthub = raw / DOLTHUB_EXPORT
        if dolthub.is_file():
            self._parquet("dolthub export", [dolthub], DOLTHUB_DATE, DOLTHUB_QUOTE, DOLTHUB_SINGLE, wanted)
            group_sizes.append(dolthub.stat().st_size)
        else:
            self.missing.append(str(dolthub))

        optionsdx = sorted(optionsdx_dir.glob("*.parquet"))
        if optionsdx:
            self._parquet("optionsdx", optionsdx, OPTIONSDX_DATE, OPTIONSDX_QUOTE, OPTIONSDX_SINGLE, wanted)
            group_sizes.append(sum(p.stat().st_size for p in optionsdx))
        else:
            self.missing.append(str(optionsdx_dir / "*.parquet"))

        self.sizes.update(group_sizes)
        self.sizes.add(sum(group_sizes))
        self.joined = "\n".join(self.texts)

    def _remember_file(self, path: Path) -> None:
        """Rules 4 and 5 data for one raw file: its size and SHA-256 (and what a .meta.json records)."""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 22), b""):
                digest.update(chunk)
        self.sizes.add(path.stat().st_size)
        self.shas.add(digest.hexdigest())
        self.files += 1
        meta = path.with_name(path.name + ".meta.json")
        if meta.is_file():
            try:
                recorded = json.loads(meta.read_text())
            except (OSError, ValueError):
                return
            if isinstance(recorded.get("bytes"), int):
                self.sizes.add(recorded["bytes"])
            if isinstance(recorded.get("sha256"), str):
                self.shas.add(recorded["sha256"].lower())

    def _text_files(self, paths: list[Path]) -> None:
        for path in paths:
            self._remember_file(path)
            text = path.read_bytes().decode("utf-8", errors="replace")
            self.texts.append(text)
            rows = 0
            for line in text.split("\n"):
                line = line.strip()
                dates = _dates_in(line)
                if not dates or dates[0][0] != 0:
                    continue  # a header, or not a data row
                rows += 1
                day = dates[0][2]
                if len(line) >= MIN_LINE:
                    self.rows_by_prefix[line[: dates[0][1]]].append(line)
                for token in line[dates[0][1] :].split(","):
                    try:
                        value = float(token)
                    except ValueError:
                        continue
                    if math.isfinite(value):
                        self.values_by_date[day].add(value)
            self.notes.append(f"{path.parent.name}/{path.name}: {rows} dated row(s), text (rules 1-5)")

    def _parquet(self, label: str, paths: list[Path], date_col: str, quote: tuple[tuple[str, str], ...], single_cols: tuple[str, ...], wanted: set[date]) -> None:
        for path in paths:
            self._remember_file(path)
        total = duckdb.sql(f"SELECT count(*) FROM read_parquet([{', '.join(repr(str(p)) for p in paths)}])").fetchall()[0][0]
        chain, rows, cells = _load_chain(paths, date_col, quote, single_cols, wanted)
        self.chains.append(chain)
        self.notes.append(
            f"{label}: {len(paths)} file(s), {total} row(s); read {rows} row(s) of {len(chain.rows)} of the "
            f"{len(wanted)} date(s) named in the scanned files; kept {cells} value(s) (rules 3-5)"
        )

    def dated_value(self, line: str, dates: Dates, nearby: list[date]) -> bool:
        """Rule 3 for one line: a number equal to a raw value of a date on this line or nearby."""
        groups: dict[tuple[int, date], list[tuple[dict[int, set[int]], float]]] = defaultdict(list)  # (chain, day) -> per number: (row -> columns, chance rows)
        numbers = 0
        searched: set[tuple[int, date]] = set()  # (chain, day) pairs that have rows
        for match in _NUMBER.finditer(line):
            token = match.group()
            decimals = len(token.split(".")[1]) if "." in token else 0
            if any(s <= match.start() < e for s, e, _ in dates):
                continue  # part of a date
            if not ((decimals >= 2 and _significant_digits(token) >= 3) or (decimals == 0 and len(token.lstrip("-")) >= 6)):
                continue  # one decimal matches a real value of some date by chance far too often
            days = [d for s, e, d in dates if min(abs(match.start() - e), abs(s - match.end())) <= NEAR_CHARS] + nearby
            number = float(token)
            numbers += 1
            for day in dict.fromkeys(days):
                if any(round(v, decimals) == number for v in self.values_by_date.get(day, ())):
                    return True
                for k, chain in enumerate(self.chains):
                    singles = chain.singles.get(day)
                    if singles is not None and _has_rounded(singles, number, decimals):
                        return True
                    if day not in chain.rows:
                        continue
                    searched.add((k, day))
                    if self.chain_single:
                        cells = chain.cells(day)
                        if cells is not None and _has_rounded(cells, number, decimals):
                            return True
                    else:
                        found = _cells_equal(chain.rows[day], number, decimals)
                        if found:
                            groups[(k, day)].append((found, _chance_rows(chain.cells(day), found, number, decimals)))
        if numbers < 2:
            return False
        # The more pairs of numbers and the more days tried, the likelier a chance match: split CHANCE among them.
        tried = max(1, numbers * (numbers - 1) // 2) * max(1, len(searched))
        return any(
            _joint(hits, self.chains[k].kinds, len(self.chains[k].rows[day]), CHANCE / tried)
            for (k, day), hits in groups.items()
            if len(hits) >= 2
        )

    def hits(self, line: str, dates: Dates) -> bool:
        """Rules 1, 2, 4 and 5 for one line (rule 3 needs the neighbouring lines: ``dated_value``)."""
        stripped = line.strip()
        # Rule 1: the whole line is in a raw text file. Raw text files hold only this alphabet, so
        # anything else cannot match and the expensive search is skipped.
        # A line with no digit (a CSV header) is column names, not data.
        if len(stripped) >= MIN_LINE and any(c.isdigit() for c in stripped) and _RAW_ALPHABET.fullmatch(stripped) and stripped in self.joined:
            return True
        for start, end, _day in dates:
            # Rule 2: a whole raw row starts at this date.
            for row in self.rows_by_prefix.get(line[start:end], ()):
                if line.startswith(row, start):
                    return True
        # Rule 4: a raw file size, or a total of them.
        for match in _BIG_INT.finditer(line):
            if int(re.sub(r"[,_ ]", "", match.group())) in self.sizes:
                return True
        # Rule 5: a raw file's hash.
        return any(token in self.shas for token in _SHA.findall(line))


def repo_text_files(repo: Path) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=repo, capture_output=True, check=True
    ).stdout.split(b"\0")
    return [repo / name.decode() for name in listed if name and (repo / name.decode()).is_file()]


def tree_files(tree: Path) -> list[Path]:
    """Every regular file under ``tree`` (no git, no ignore rules, symlinks not followed), sorted."""
    found = []
    for folder, _dirs, names in os.walk(tree):
        for name in names:
            path = Path(folder) / name
            if path.is_file() and not path.is_symlink():
                found.append(path)
    return sorted(found)


def read_text_files(paths: list[Path]) -> tuple[list[tuple[Path, list[str]]], int]:
    """``(path, lines)`` for each text file, and how many files were skipped (binary, not UTF-8, unreadable)."""
    texts = []
    skipped = 0
    for path in paths:
        try:
            blob = path.read_bytes()
            if b"\0" in blob[:8192]:
                raise ValueError("binary")
            text = blob.decode("utf-8")
        except (OSError, ValueError):  # UnicodeDecodeError is a ValueError
            skipped += 1
            continue
        # Split on "\n" only, so a reported line number agrees with grep -n and with an editor.
        texts.append((path, text.split("\n")))
    return texts, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tree", type=Path, help="scan every text file in this folder instead of the repo's git files")
    parser.add_argument("--work-dir", type=Path, help="where raw/ lives (default: work_dir(), the repo's data/ or $VOLBT_WORK_DIR)")
    parser.add_argument("--chain-single", action="store_true", help="flag one number that equals any OptionsDX or DoltHub value of a nearby date (noisy)")
    parser.add_argument("--optionsdx-dir", type=Path, help="the OptionsDX Parquet folder (default: kaggle_dir()/spy-eod-2010-2023)")
    args = parser.parse_args(argv)
    work = (args.work_dir or config.work_dir()).expanduser()
    optionsdx_dir = (args.optionsdx_dir or config.kaggle_dir() / OPTIONSDX_DATASET).expanduser()

    repo = Path(__file__).resolve().parents[2]
    if args.tree:
        base = args.tree.expanduser().resolve()
        if not base.is_dir():
            print(f"error: --tree {base} is not a folder", file=sys.stderr)
            return 2
        paths = tree_files(base)
    else:
        base = repo
        paths = repo_text_files(repo)
    texts, skipped = read_text_files(paths)

    # Every date named anywhere in the scanned text, for the Parquet filter and for rule 3.
    line_dates: dict[Path, list[Dates]] = {}
    wanted: set[date] = set()
    for path, lines in texts:
        per_line = [_dates_in(line) for line in lines]
        line_dates[path] = per_line
        wanted.update(d for found in per_line for _, _, d in found)

    index = RawIndex(work, optionsdx_dir, wanted, args.chain_single)
    for note in index.notes:
        print(f"indexed {note}", file=sys.stderr)
    for name in index.missing:
        print(f"missing raw source: {name}", file=sys.stderr)
    if not index.files:
        print(f"error: no raw files under {work / 'raw'} or {optionsdx_dir}; nothing to compare with", file=sys.stderr)
        return 2

    flagged = 0
    for path, lines in texts:
        per_line = line_dates[path]
        # Dates per line, for rule 3's neighbourhood; very long lines (minified JSON) lend none.
        lent = [[d for _, _, d in found] if len(line) <= LONG_LINE else [] for line, found in zip(lines, per_line)]
        for i, line in enumerate(lines):
            nearby = [d for j in range(max(0, i - NEAR_LINES), min(len(lines), i + NEAR_LINES + 1)) if j != i for d in lent[j]]
            if index.hits(line, per_line[i]) or index.dated_value(line, per_line[i], nearby):
                flagged += 1
                print(f"{path.relative_to(base)}:{i + 1}")
    if skipped:
        print(f"skipped {skipped} binary or non-UTF-8 file(s)", file=sys.stderr)
    summary = f"{len(texts)} text file(s) against {index.files} raw file(s)"
    if flagged:
        print(f"{flagged} line(s) flagged in {summary}")
        return 1
    if index.missing:
        print(f"incomplete: 0 lines flagged in {summary}, but {len(index.missing)} raw source(s) missing")
        return 2
    print(f"clean: 0 lines flagged in {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
