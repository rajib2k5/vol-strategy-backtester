"""volbt.build: the derived-table build. Milestone 2 adds the pricing build.

Why a separate module (ADR-0001 §3). `pricing` must stay pure (no files, no store), yet someone
has to read option_quotes, run the pricing functions and store what they return. That is this
module, and it does all of its I/O THROUGH volbt.data: it never opens a file itself.

Two kinds of build live here:

- `Step` and `run`: a generic list of steps, each a pure function from whole tables to one new
  table (M1's skeleton; the tests use it).
- The PRICING BUILD (M2), which works one partition at a time because option_quotes is 19 M rows:
  for each (source, year) it reads that year's quotes, prices every snapshot with
  volbt.pricing.chain.price_chain, and writes the year's partition of three tables:

      expiry_forwards  one row per (source, quote_date, expiry): tau, r, DF, the forward (raw and
                       de-Americanised), the carry forward, K*, the pair counts, the method
      quote_iv         one row per quote of option_quotes: log-moneyness, OTM or not, in the smile
                       or not, the IV of the de-Americanised mid (OTM only), the quote's American IV
                       and the premium removed at it, the ITM side's premium for PARITY_OUTLIER, iv_flags
      smile_fits       one row per (source, quote_date, expiry): the smile's nodes in total
                       variance, the ATM IV, fit_flags

  Partitions are independent, so they run in parallel processes, and a partition whose inputs
  and code have not changed since its last build is skipped (pricing_inputs.json). "The code"
  is every volbt module the build imports, the versions of the libraries that compute or write
  (numpy, scipy, pandas, pyarrow, duckdb) and Python, and the store's parquet write settings
  (code_fingerprint; the M2 review found a change to the compression level re-priced nothing
  yet wrote different bytes). pricing_inputs.json records, per partition, the code fingerprint
  that priced it and its input fingerprint. An unfiltered build deletes a pricing partition whose
  option_quotes partition no longer exists, after checking the store and planning every deletion
  (orphan_partitions; a filtered build deletes nothing). After the partitions, pricing_summary.json
  is computed from the stored tables alone, so it is the same bytes whichever partitions were
  rebuilt (no clock time; wall times go to pricing_timings.json), and only when every partition
  was priced by the current code from its current quotes and reference tables (require_current;
  round 3, F1). The build removes the old summary before it deletes or writes anything.

It also builds the body of the app's surface_frames.json (ADR-0001 §5) from the stored smiles.

May import (volbt): config, data, pricing.
"""

from __future__ import annotations

import hashlib
import multiprocessing
import platform
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from fractions import Fraction
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import scipy

from volbt.data import flags as quality
from volbt.data import store as store_module
from volbt.data.store import Store, file_sha256, read_json, write_json
from volbt.pricing import chain, dividends, iv, smile


@dataclass(frozen=True)
class Step:
    output: str                                 # the table this step writes
    inputs: tuple[tuple[str, str], ...]         # (table, ORDER BY clause) for each table it reads
    compute: Callable                           # dict[name, DataFrame] -> DataFrame, no I/O
    sort_by: tuple[str, ...]                    # the key the output is sorted by on disk
    partition_by: tuple[str, ...] = ()


def run(steps: tuple[Step, ...], store: Store | None = None) -> dict[str, int]:
    """Run the steps in order. Each reads through the store and writes through the store.

    A later step may read what an earlier one wrote. Returns {table written: rows}.
    """
    target = store or Store()
    written = {}
    for step in steps:
        tables = {name: target.read_table(name, order_by=order) for name, order in step.inputs}
        result = step.compute(tables)
        target.write_table(step.output, result, sort_by=step.sort_by, partition_by=step.partition_by)
        written[step.output] = len(result)
    return written


# --- the pricing build (M2) -------------------------------------------------------------------

PRICING_TABLES = ("expiry_forwards", "quote_iv", "smile_fits")
SORT_KEYS = {"expiry_forwards": ("quote_date", "expiry"), "quote_iv": ("quote_date", "osi_symbol"),
             "smile_fits": ("quote_date", "expiry")}
SUMMARY_FILE = "pricing_summary.json"
INPUTS_FILE = "pricing_inputs.json"
TIMINGS_FILE = "pricing_timings.json"
REFERENCE_TABLES = ("rates", "dividends", "spy_bars")

# A quote has a two-sided mid when both sides are there and not crossed (ADR-0004 rules 1 and 2:
# a zero bid still has the mid ask/2).
NO_MID = quality.BID_NULL | quality.ASK_NULL | quality.CROSSED
# ...and is VALID for the parity forward and the smile when it is also a rule-1 quote: a bid
# above zero and not stale (ADR-0004 rule 1; ADR-0008 §3, "flags clear").
NOT_VALID = NO_MID | quality.ZERO_BID | quality.STALE
# ...and is a SMILE NODE only when it is also not WIDE (ask - bid > mid): a WIDE quote keeps its IV and
# may enter the forward, but its mid is too uncertain to be a node (round 3, decision F2).
NOT_SMILE = NOT_VALID | quality.WIDE

QUOTE_COLUMNS = "quote_date, osi_symbol, expiry, strike, call_put, bid, ask, spy_close, quality_flags"

FORWARD_SCHEMA = pa.schema([
    ("quote_date", pa.date32()), ("expiry", pa.date32()), ("tau_years", pa.float64()), ("r_cc", pa.float64()),
    ("discount_factor", pa.float64()), ("spot", pa.float64()), ("forward", pa.float64()),
    ("forward_raw", pa.float64()), ("forward_carry", pa.float64()), ("k_star", pa.float64()),
    ("n_pairs_valid", pa.int32()), ("n_pairs_used", pa.int32()), ("n_deamericanised", pa.int32()),
    ("fk_slope_per_strike", pa.float64()), ("forward_mad_rel", pa.float64()), ("method", pa.string()),
    ("flags", pa.int32()),
])
QUOTE_IV_SCHEMA = pa.schema([
    ("quote_date", pa.date32()), ("osi_symbol", pa.string()), ("expiry", pa.date32()),
    ("log_moneyness", pa.float64()), ("is_otm", pa.bool_()), ("in_smile", pa.bool_()), ("iv", pa.float64()),
    ("iv_raw", pa.float64()), ("iv_american", pa.float64()), ("eep", pa.float64()), ("eep_partner", pa.float64()),
    ("iv_flags", pa.int32()), ("solver", pa.string()), ("iterations", pa.int16()), ("iv_fail_reason", pa.string()),
])
SMILE_SCHEMA = pa.schema([
    ("quote_date", pa.date32()), ("expiry", pa.date32()), ("tau_years", pa.float64()),
    ("k_nodes", pa.list_(pa.float64())), ("total_var_nodes", pa.list_(pa.float64())), ("n_points", pa.int32()),
    ("atm_iv", pa.float64()), ("fit_flags", pa.int32()),
])
SCHEMAS = {"expiry_forwards": FORWARD_SCHEMA, "quote_iv": QUOTE_IV_SCHEMA, "smile_fits": SMILE_SCHEMA}


def _floats(values) -> pa.Array:
    """float64 with every NaN written as a null: "not computed" reads as NULL in SQL, not as a number."""
    values = np.asarray(values, dtype=float)
    return pa.array(values, type=pa.float64(), mask=~np.isfinite(values))


def _names(codes, names) -> pa.Array:
    """Small integer codes as strings; code 0 ("") as a null."""
    text = np.asarray(names, dtype=object)[np.asarray(codes, dtype=int)]
    return pa.array([s if s else None for s in text], type=pa.string())


def reference_inputs(store: Store) -> dict:
    """The rate history, the paid dividends and the sessions, read once for the whole build."""
    rates = store.read_table("rates", order_by="date")
    paid = store.read_table("dividends", order_by="ex_date")
    bars = store.read_table("spy_bars", order_by="date")
    return {"rate_days": pd.to_datetime(rates["date"]).to_numpy().astype("datetime64[D]"),
            "r_cc": rates["r_cc"].to_numpy(float),
            "ex_dates": [d.date() if hasattr(d, "date") else d for d in paid["ex_date"]],
            "amounts": paid["amount"].to_numpy(float).tolist(),
            "sessions": [d.date() if hasattr(d, "date") else d for d in bars["date"]]}


def rate_on(reference: dict, day: date) -> float:
    """The last DGS3MO continuous rate dated strictly BEFORE `day` (M2 review amendment, 2026-10-29).

    DGS3MO for day t is the Treasury's ~15:30 ET bid, published by the Treasury around 18:00 ET and
    on H.15/FRED at 16:15 ET the next business day: it is not public at the 16:00 ET snapshot of t.
    """
    index = int(np.searchsorted(reference["rate_days"], np.datetime64(day, "D"), side="left")) - 1
    if index < 0:
        raise ValueError(f"no DGS3MO rate dated before {day}")
    return float(reference["r_cc"][index])


def price_snapshot(quotes: pd.DataFrame, quote_date: date, reference: dict) -> dict[str, dict]:
    """Price the quotes of one (source, quote_date). Returns {table: {column: array}} for the 3 tables."""
    expiry_dates = sorted(set(quotes["expiry"]))
    expiry_index = {day: i for i, day in enumerate(expiry_dates)}
    tau = np.array([(e - quote_date).days / 365 for e in expiry_dates])
    schedules = [dividends.schedule(reference["ex_dates"], reference["amounts"], quote_date, e, reference["sessions"])
                 for e in expiry_dates]
    width = max((len(times) for times, _ in schedules), default=0)
    div_times = np.zeros((len(expiry_dates), width))
    div_amounts = np.zeros((len(expiry_dates), width))
    for row, (times, amounts) in enumerate(schedules):
        div_times[row, :len(times)], div_amounts[row, :len(amounts)] = times, amounts

    bits = quotes["quality_flags"].to_numpy(np.int64)
    bid, ask = quotes["bid"].to_numpy(float), quotes["ask"].to_numpy(float)
    has_mid = ((bits & NO_MID) == 0) & (ask > 0)
    mid = np.where(has_mid, (bid + ask) / 2, np.nan)
    valid = has_mid & ((bits & NOT_VALID) == 0)
    spot = float(quotes["spy_close"].iloc[0])
    rate = rate_on(reference, quote_date)
    priced = chain.price_chain(spot, rate, tau, div_times, div_amounts,
                               np.array([expiry_index[e] for e in quotes["expiry"]]),
                               quotes["strike"].to_numpy(float), (quotes["call_put"] == "C").to_numpy(),
                               mid, valid, smile_ok=(bits & NOT_SMILE) == 0)
    e, q = priced["expiries"], priced["quotes"]
    days = [quote_date] * len(expiry_dates)
    return {
        "expiry_forwards": {
            "quote_date": days, "expiry": expiry_dates, "tau_years": tau, "r_cc": np.full(tau.size, rate),
            "discount_factor": np.exp(-rate * tau), "spot": np.full(tau.size, spot), **{
                name: e[name] for name in ("forward", "forward_raw", "forward_carry", "k_star", "n_pairs_valid",
                                           "n_pairs_used", "n_deamericanised", "fk_slope_per_strike",
                                           "forward_mad_rel", "flags")},
            "method": e["method"]},
        "quote_iv": {"quote_date": [quote_date] * len(quotes), "osi_symbol": quotes["osi_symbol"].tolist(),
                     "expiry": quotes["expiry"].tolist(), **{
                         name: q[name] for name in ("log_moneyness", "is_otm", "in_smile", "iv", "iv_raw", "iv_american",
                                                    "eep", "eep_partner", "iv_flags", "solver", "iterations")},
                     "iv_fail_reason": q["fail"]},
        "smile_fits": {"quote_date": days, "expiry": expiry_dates, "tau_years": tau,
                       "k_nodes": [s["k_nodes"].tolist() for s in priced["smiles"]],
                       "total_var_nodes": [s["w_nodes"].tolist() for s in priced["smiles"]],
                       "n_points": [s["n_points"] for s in priced["smiles"]],
                       "atm_iv": [s["atm_iv"] for s in priced["smiles"]],
                       "fit_flags": [s["fit_flags"] for s in priced["smiles"]]},
    }


def _arrow(name: str, parts: list[dict]) -> pa.Table:
    """Concatenate one table's per-snapshot columns into an arrow table with its fixed schema."""
    schema = SCHEMAS[name]
    if not parts:
        return schema.empty_table()
    column = {field: [v for part in parts for v in part[field]]
              if field in ("quote_date", "expiry", "osi_symbol", "k_nodes", "total_var_nodes")
              else np.concatenate([np.asarray(part[field]) for part in parts]) for field in parts[0]}
    arrays = {}
    for field in schema:
        values = column[field.name]
        if field.name == "method":
            arrays[field.name] = _names(values, chain.METHOD_NAMES)
        elif field.name == "solver":
            arrays[field.name] = _names(values, iv.SOLVER_NAMES)
        elif field.name == "iv_fail_reason":
            arrays[field.name] = _names(values, iv.FAIL_NAMES)
        elif field.name == "iterations":
            values = np.asarray(values, dtype=np.int16)
            arrays[field.name] = pa.array(values, type=pa.int16(), mask=values < 0)
        elif pa.types.is_floating(field.type):
            arrays[field.name] = _floats(values)
        else:
            arrays[field.name] = pa.array(list(values) if pa.types.is_list(field.type) else values, type=field.type)
    return pa.Table.from_arrays([arrays[f.name] for f in schema], schema=schema)


def price_partition(root: str, source: str, year: str) -> dict:
    """Price one (source, year) and write its partition of the three tables. Runs in a worker process."""
    started = time.monotonic()
    store = Store(Path(root))
    reference = reference_inputs(store)
    quotes = store.query(f"SELECT {QUOTE_COLUMNS} FROM option_quotes WHERE source = ? AND year = ? "
                         "ORDER BY quote_date, osi_symbol", [source, str(year)])
    quotes["quote_date"] = pd.to_datetime(quotes["quote_date"]).dt.date
    quotes["expiry"] = pd.to_datetime(quotes["expiry"]).dt.date
    parts: dict[str, list] = {name: [] for name in PRICING_TABLES}
    for quote_date, snapshot in quotes.groupby("quote_date", sort=True):
        snapshot = snapshot.reset_index(drop=True)
        for name, columns in price_snapshot(snapshot, quote_date, reference).items():
            parts[name].append(columns)
    for name in PRICING_TABLES:
        store.write_partition(name, _arrow(name, parts[name]), {"source": source, "year": year}, SORT_KEYS[name])
    return {"source": source, "year": year, "quotes": int(len(quotes)), "seconds": round(time.monotonic() - started, 1)}


# Everything a partition's bytes depend on besides its inputs (M2 review, code claim 10). The volbt
# modules the build imports (a test runs a build in a fresh interpreter and requires every volbt
# module it loaded to be in this list), the libraries that compute or write the numbers, and Python.
PACKAGE_DIR = Path(__file__).resolve().parent
FINGERPRINT_MODULES = ("__init__.py", "build.py", "config.py", "view.py", "data/__init__.py", "data/flags.py",
                       "data/store.py", "pricing/*.py")
# Each library's own __version__, the string its installed distribution carries (importlib, which
# would read the distribution's metadata, is banned in volbt by the import-boundary test).
FINGERPRINT_LIBRARIES = {"numpy": np, "scipy": scipy, "pandas": pd, "pyarrow": pa, "duckdb": duckdb}


def fingerprinted_files() -> list[Path]:
    """The volbt source files code_fingerprint hashes, sorted."""
    files = set()
    for pattern in FINGERPRINT_MODULES:
        files.update(PACKAGE_DIR.glob(pattern))
    return sorted(files)


def fingerprint_lines() -> list[str]:
    """What code_fingerprint hashes, one line each: files, library versions, Python, store settings."""
    lines = [f"{path.relative_to(PACKAGE_DIR).as_posix()}\t{file_sha256(path)}" for path in fingerprinted_files()]
    lines += [f"{name}=={module.__version__}" for name, module in FINGERPRINT_LIBRARIES.items()]
    lines.append(f"python=={platform.python_version()}")
    lines += [f"store.{key}={value}" for key, value in sorted(store_module.write_settings().items())]
    return lines


def code_fingerprint() -> str:
    """SHA-256 over fingerprint_lines(): a change to any of them re-prices every partition."""
    return hashlib.sha256("\n".join(fingerprint_lines()).encode("utf-8")).hexdigest()


def partition_fingerprint(store: Store, partition: dict[str, str], code: str) -> str:
    """SHA-256 over what one partition's pricing reads: its quotes, the reference tables and the code.

    Each reference table must be its one part-0.parquet (Store.checked_table_file raises InconsistentStore
    otherwise): pricing reads every parquet in the table's folder, so a second one would change the prices
    and not this fingerprint (round 4, decision G1).
    """
    files = [store.partition_file("option_quotes", partition)] + [store.checked_table_file(t)
                                                                  for t in REFERENCE_TABLES]
    lines = [code] + [file_sha256(path) for path in files]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


class PricingNotCurrent(ValueError):
    """The pricing tables do not all come from the current code and the current quotes: no summary, no export."""


def partition_key(partition: dict[str, str]) -> str:
    return f"source={partition['source']}/year={partition['year']}"


def orphan_partitions(store: Store, live_keys: set[str]) -> list[tuple[str, dict[str, str]]]:
    """Every pricing partition whose option_quotes partition is gone, as (table, partition): the plan.

    Reads only. Before it plans anything it checks option_quotes and the three pricing tables with
    Store.checked_partitions (no symlink anywhere in them, nothing outside the store root, no stray
    file or folder, no quotes partition without its part-0.parquet) and raises InconsistentStore
    on the first problem, so a deletion is never planned on a store that is not what the writer
    left (M2 round 2, code claim 1: a symlinked quotes partition, a .tmp leftover or a stray folder
    each deleted live pricing, and a symlinked table deleted files outside the store).
    """
    quotes = {partition_key(p) for p in store.checked_partitions("option_quotes")}
    if quotes != live_keys:
        raise store_module.InconsistentStore(f"option_quotes lists {sorted(quotes ^ live_keys)} differently when read "
                                             "file by file and folder by folder")
    plan = []
    for name in PRICING_TABLES:
        plan += [(name, p) for p in store.checked_partitions(name) if partition_key(p) not in live_keys]
    root = store.root.resolve()
    for name, partition in plan:      # the whole plan is checked before the first deletion
        folder = store.table_dir(name).joinpath(*(f"{c}={v}" for c, v in partition.items()))
        if folder.is_symlink() or not folder.resolve().is_relative_to(root):
            raise store_module.InconsistentStore(f"refusing to delete {folder}: not a real folder inside {root}")
    return plan


def pricing_problems(store: Store, code: str | None = None) -> list[str]:
    """Why the pricing tables are not one build of the current code over the current inputs ([] if they are).

    Every option_quotes partition must have its partition in each of the three tables, no pricing
    partition may lack its quotes, and every partition's record in pricing_inputs.json must be
    exactly {"code": code, "inputs": partition_fingerprint(store, partition, code)}: the code that
    priced it is the current code (default: code_fingerprint()), AND its quotes and the reference
    tables are the bytes it was priced from. A filtered build after a code change re-prices only the
    partitions it was asked for (M2 round 2, design claim 3), and quotes rewritten with the code
    unchanged left pricing from the old quotes under a summary and an export that accepted them
    (round 3, code claim 6; decision F1). Re-hashing the inputs costs one SHA-256 pass over
    option_quotes (about 0.5 GB) per call.

    Provenance is what pricing_inputs.json records: it is not signed, so a hand edit of that file
    is not defended against (ADR-0001 amendment, ADR-0008).
    """
    code = code or code_fingerprint()
    live = store.checked_partitions("option_quotes")
    quotes = {partition_key(p) for p in live}
    recorded = read_json(store.root / INPUTS_FILE) or {}
    problems = []
    for name in PRICING_TABLES:
        priced = {partition_key(p) for p in store.checked_partitions(name)}
        if quotes - priced:
            problems.append(f"quotes partitions with no {name}: {sorted(quotes - priced)}")
        if priced - quotes:
            problems.append(f"{name} partitions whose quotes are gone: {sorted(priced - quotes)}")
    older = sorted(k for k in quotes if not isinstance(recorded.get(k), dict) or recorded[k].get("code") != code)
    if older:
        problems.append(f"partitions priced by older code: run a full build (tools/build_pricing.py without --source "
                        f"or --year): {older}")
    changed = sorted(partition_key(p) for p in live if partition_key(p) not in older
                     and recorded[partition_key(p)] != {"code": code, "inputs": partition_fingerprint(store, p, code)})
    if changed:
        problems.append(f"partitions whose quotes or reference tables changed since they were priced: run a build "
                        f"(tools/build_pricing.py): {changed}")
    return problems


def require_current(store: Store, code: str | None = None) -> None:
    """Raise PricingNotCurrent, naming each problem, unless pricing_problems() is empty."""
    problems = pricing_problems(store, code)
    if problems:
        raise PricingNotCurrent("; ".join(problems))


def build_pricing(store: Store | None = None, sources: list[str] | None = None, years: list[str] | None = None,
                  workers: int = 1, force: bool = False) -> dict:
    """Price every (source, year) partition of option_quotes (or the ones asked for); then the summary.

    A partition whose recorded code fingerprint and input fingerprint (quotes, reference tables,
    code) equal the current ones, and whose three outputs exist, is skipped unless `force`.

    Orphans (M2 round 2, decision E2: deleting them is deleting data). Only an UNFILTERED build
    (no `sources`, no `years`) deletes the pricing partitions whose option_quotes partition is gone,
    and only after orphan_partitions has checked the store and planned every deletion; a filtered
    build deletes nothing. With no option_quotes partition at all the build raises before it reads
    or deletes anything (a wrong store root, or M1 rebuilding the table, must not empty the
    pricing tables). A reference table (rates, dividends, spy_bars) whose folder holds anything but
    its part-0.parquet raises InconsistentStore before anything is deleted (round 4, decision G1).

    Unfiltered means `sources is None and years is None` (round 3, decision F5): an empty list is
    not "everything" (it deleted orphans as if it were), so it raises ValueError before anything is
    read or deleted.

    The summary of the earlier build is removed at the start, after the empty-store check and before
    any deletion or write (round 3, decision F1): a build interrupted after it deleted orphans, or
    killed while pricing, leaves no summary, so the export refuses instead of reading one that no
    longer describes the store. The summary is computed again only when every partition is current
    (require_current): otherwise it raises PricingNotCurrent, after writing the partitions it priced
    and their fingerprints. Returns the summary.

    One writer at a time (round 3, decision F6): there is no lock on the store. Two builds, or a
    build and an M1 rewrite of option_quotes, running at once can leave partitions priced from
    quotes that changed under them; pricing_problems then refuses the summary and the export, and
    the cost is a re-price of derived data.
    """
    for name, values in (("sources", sources), ("years", years)):
        if values is not None and len(values) == 0:
            raise ValueError(f"{name}=[] names no partition: pass None to price every partition (nothing was read "
                             "or deleted)")
    store = store or Store()
    started = time.monotonic()
    code = code_fingerprint()
    live = store.partitions("option_quotes")
    if not live:
        raise ValueError(f"{store.root} has no option_quotes partition: nothing to price, and nothing was deleted "
                         "(build the store first: uv run python tools/build_data.py)")
    for table in REFERENCE_TABLES:              # InconsistentStore before anything is deleted (round 4, G1)
        store.checked_table_file(table)
    (store.root / SUMMARY_FILE).unlink(missing_ok=True)      # it describes the store before this build
    keys = {partition_key(p) for p in live}
    recorded = read_json(store.root / INPUTS_FILE) or {}
    if sources is None and years is None:
        for name, partition in orphan_partitions(store, keys):
            store.delete_partition(name, partition)
        recorded = {key: value for key, value in recorded.items() if key in keys}
    todo, prints = [], {}
    for partition in live:
        key = partition_key(partition)
        if ((sources is not None and partition["source"] not in sources)
                or (years is not None and partition["year"] not in years)):
            continue
        prints[key] = {"code": code, "inputs": partition_fingerprint(store, partition, code)}
        built = all(store.partition_file(name, partition).is_file() for name in PRICING_TABLES)
        if force or not built or recorded.get(key) != prints[key]:
            todo.append(partition)
    # Largest first, so the long years do not start last.
    todo.sort(key=lambda p: -store.partition_file("option_quotes", p).stat().st_size)
    jobs = [(str(store.root), p["source"], p["year"]) for p in todo]
    if workers > 1 and len(jobs) > 1:
        # spawn, not fork: a forked child would inherit the parent's DuckDB threads and locks.
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            results = list(pool.map(price_partition, *zip(*jobs)))
    else:
        results = [price_partition(*job) for job in jobs]
    recorded.update({partition_key(r): prints[partition_key(r)] for r in results})
    write_json(dict(sorted(recorded.items())), store.root / INPUTS_FILE)
    try:
        summary = pricing_summary(store, code)
        write_json(summary, store.root / SUMMARY_FILE)
    finally:
        write_json({"partitions": sorted(results, key=lambda r: (r["source"], r["year"])), "workers": workers,
                    "total_seconds": round(time.monotonic() - started, 1),
                    "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
                   store.root / TIMINGS_FILE)
    return summary


# --- the summary, from the stored tables only -------------------------------------------------

def _q(column: str, p: float) -> str:
    return f"quantile_cont({column}, {p})"


# Tenor buckets in calendar days: the strategies trade the first, OptionsDX also lists the others.
TENOR = ("CASE WHEN expiry - quote_date <= 60 THEN '0-60' WHEN expiry - quote_date <= 180 THEN '61-180' "
         "ELSE '181+' END")
# Every block is reported by (source, year, tenor), by (source, tenor) over all years, and by
# source alone; a null year or tenor in a row means "all".
GROUPS = "GROUPING SETS ((source, year, tenor), (source, tenor), (source))"
ORDER = "ORDER BY source, year NULLS LAST, tenor NULLS LAST"

SUMMARY_SQL = {
    "forwards": f"""
        SELECT source, year, tenor, count(*) AS expiries, count(DISTINCT quote_date) AS dates,
               count(*) FILTER (method = 'parity_median5_deam') AS parity,
               count(*) FILTER (method = 'dividend_fallback') AS fallback,
               count(*) FILTER (method = 'parity_median5_raw') AS parity_raw,
               count(*) FILTER (method = 'expiry_day') AS expiry_day,
               list(r_cc) AS mean_r_cc,
               {_q("(forward / forward_carry - 1) * 1e4", 0.05)} FILTER (method = 'parity_median5_deam') AS vs_carry_bp_p05,
               {_q("(forward / forward_carry - 1) * 1e4", 0.5)} FILTER (method = 'parity_median5_deam') AS vs_carry_bp_median,
               {_q("(forward / forward_carry - 1) * 1e4", 0.95)} FILTER (method = 'parity_median5_deam') AS vs_carry_bp_p95,
               {_q("(forward_raw / forward_carry - 1) * 1e4", 0.5)} AS raw_vs_carry_bp_median,
               {_q("(forward / forward_raw - 1) * 1e4", 0.5)} AS deam_shift_bp_median,
               {_q("(forward / forward_raw - 1) * 1e4", 0.95)} AS deam_shift_bp_p95,
               max((forward / forward_raw - 1) * 1e4) AS deam_shift_bp_max,
               {_q("forward_mad_rel * 1e4", 0.5)} AS mad_bp_median,
               {_q("forward_mad_rel * 1e4", 0.95)} AS mad_bp_p95,
               {_q("fk_slope_per_strike", 0.5)} AS fk_slope_median
        FROM (SELECT *, {TENOR} AS tenor FROM expiry_forwards WHERE tau_years > 0) GROUP BY {GROUPS} {ORDER}""",
    # has_mid, valid and smile_ok are build.price_snapshot's rules, read back from option_quotes' own flags.
    "quotes": f"""
        SELECT source, year, tenor, count(*) AS quotes,
               count(*) FILTER (is_otm AND has_mid) AS otm_attempted,
               count(*) FILTER (iv IS NOT NULL) AS solved,
               count(*) FILTER (is_otm AND has_mid AND valid) AS otm_valid,
               count(*) FILTER (is_otm AND has_mid AND valid AND wide) AS otm_valid_wide,
               count(*) FILTER (is_otm AND has_mid AND smile_ok) AS otm_smile_ok,
               count(*) FILTER (in_smile) AS in_smile,
               count(*) FILTER (solver = 'newton') AS newton,
               count(*) FILTER (solver = 'bisection') AS bisection,
               count(*) FILTER (iv_flags & 1 <> 0) AS iv_fail,
               count(*) FILTER (iv_flags & 1 <> 0 AND valid) AS iv_fail_valid,
               count(*) FILTER (iv_fail_reason = 'below_lower_bound') AS fail_below_lower_bound,
               count(*) FILTER (iv_fail_reason = 'above_upper_bound') AS fail_above_upper_bound,
               count(*) FILTER (iv_fail_reason = 'no_root') AS fail_no_root,
               count(*) FILTER (iv_fail_reason = 'unresolved') AS fail_unresolved,
               count(*) FILTER (iv_fail_reason LIKE 'american_%') AS fail_american,
               count(*) FILTER (iv_fail_reason = 'american_below_floor') AS fail_american_below_floor,
               count(*) FILTER (iv_fail_reason = 'american_above_cap') AS fail_american_above_cap,
               count(*) FILTER (iv_fail_reason = 'american_no_convergence') AS fail_american_no_convergence,
               count(*) FILTER (iv_fail_reason = 'american_unidentified') AS fail_american_unidentified,
               count(*) FILTER (eep IS NOT NULL AND iv_american IS NULL) AS premium_from_partner,
               count(*) FILTER (iv_flags & 2 <> 0) AS parity_outlier,
               count(*) FILTER (iv_flags & 4 <> 0) AS forward_fallback,
               {_q("(iv_raw - iv) * 100", 0.5)} AS deam_iv_pts_median,
               {_q("(iv_raw - iv) * 100", 0.95)} AS deam_iv_pts_p95,
               {_q("(iv_raw - iv) * 100", 0.99)} AS deam_iv_pts_p99,
               max((iv_raw - iv) * 100) AS deam_iv_pts_max,
               count(*) FILTER (abs(log_moneyness) > 0.15 AND iv IS NOT NULL) AS beyond_015,
               count(*) FILTER (abs(log_moneyness) > 0.15 AND (iv_raw - iv) * 100 > 0.02) AS beyond_015_above_002,
               {_q("(iv_raw - iv) * 100", 0.99)} FILTER (abs(log_moneyness) > 0.15) AS deam_iv_pts_beyond_015_p99,
               max((iv_raw - iv) * 100) FILTER (abs(log_moneyness) > 0.15) AS deam_iv_pts_beyond_015_max
        FROM (SELECT q.*, {TENOR} AS tenor,
                     (o.quality_flags & {NO_MID}) = 0 AND o.ask > 0 AS has_mid,
                     (o.quality_flags & {NOT_VALID}) = 0 AND o.ask > 0 AS valid,
                     (o.quality_flags & {quality.WIDE}) <> 0 AS wide,
                     (o.quality_flags & {NOT_SMILE}) = 0 AND o.ask > 0 AS smile_ok
              FROM quote_iv q JOIN (SELECT source, year, quote_date, osi_symbol, quality_flags, ask FROM option_quotes) o
                   USING (source, year, quote_date, osi_symbol)
              WHERE expiry > quote_date) GROUP BY {GROUPS} {ORDER}""",
    "smiles": f"""
        SELECT source, year, tenor, count(*) AS smiles, count(*) FILTER (fit_flags & 1 = 0) AS usable,
               {_q("n_points", 0.5)} AS nodes_median,
               count(*) FILTER (fit_flags & 2 <> 0) AS atm_outside_nodes
        FROM (SELECT *, {TENOR} AS tenor FROM smile_fits WHERE tau_years > 0) GROUP BY {GROUPS} {ORDER}""",
    # Leave-one-out: drop each interior node and read it back from its two neighbours, linear in w.
    # The piecewise-linear smile is exact at its nodes, so this is its honest interpolation error.
    "leave_one_out": f"""
        WITH nodes AS (
            SELECT source, year, quote_date, expiry, tau_years, {TENOR} AS tenor,
                   unnest(k_nodes) AS k, unnest(total_var_nodes) AS w, generate_subscripts(k_nodes, 1) AS i
            FROM smile_fits WHERE fit_flags & 1 = 0),
        neighbours AS (
            SELECT *, lag(k) OVER s AS k0, lag(w) OVER s AS w0, lead(k) OVER s AS k1, lead(w) OVER s AS w1
            FROM nodes WINDOW s AS (PARTITION BY source, quote_date, expiry ORDER BY i)),
        errors AS (
            SELECT source, year, tenor, k,
                   abs(sqrt(greatest(w0 + (w1 - w0) * (k - k0) / (k1 - k0), 0) / tau_years) - sqrt(w / tau_years)) * 100 AS err
            FROM neighbours WHERE k0 IS NOT NULL AND k1 IS NOT NULL)
        SELECT source, year, tenor, count(*) AS points,
               {_q("err", 0.5)} AS median_pts, {_q("err", 0.9)} AS p90_pts,
               {_q("err", 0.5)} FILTER (abs(k) <= 0.05) AS median_pts_k005,
               {_q("err", 0.9)} FILTER (abs(k) <= 0.05) AS p90_pts_k005,
               {_q("err", 0.5)} FILTER (abs(k) <= 0.15) AS median_pts_k015,
               {_q("err", 0.9)} FILTER (abs(k) <= 0.15) AS p90_pts_k015
        FROM errors GROUP BY {GROUPS} {ORDER}""",
}


def _records(frame: pd.DataFrame) -> list[dict]:
    """Rows as dicts of plain Python numbers, rounded to 6 significant places; NaN as None."""
    out = []
    for row in frame.to_dict("records"):
        clean = {}
        for key, value in row.items():
            if isinstance(value, (float, np.floating)):
                clean[key] = None if not np.isfinite(value) else float(f"{float(value):.6g}")
            elif isinstance(value, (int, np.integer)):
                clean[key] = int(value)
            else:
                clean[key] = value
        out.append(clean)
    return out


def exact_mean(values) -> float:
    """The mean of a list of floats, computed exactly in rationals and rounded once: the same bits in any order."""
    values = [Fraction(float(v)) for v in values]
    return float(sum(values) / len(values)) if values else float("nan")


def summary_blocks(store: Store) -> dict[str, pd.DataFrame]:
    """SUMMARY_SQL's blocks, unrounded, deterministic BY CONSTRUCTION (M2 round 2, code claim 6).

    Every float aggregate is an order statistic (quantile_cont, max), a count, or a mean taken by
    exact_mean over the group's list of values: none depends on the order DuckDB's threads meet the rows,
    so the bits are the same at any thread count. avg() was not (1.8e-15 run to run at 20 threads),
    and only the 6-digit rounding of _records hid it.
    """
    blocks = {name: store.query(sql) for name, sql in SUMMARY_SQL.items()}
    blocks["forwards"]["mean_r_cc"] = [exact_mean(v) for v in blocks["forwards"]["mean_r_cc"]]
    return blocks


def pricing_summary(store: Store, code: str | None = None) -> dict:
    """The headline numbers of the pricing build, by (source, year), read back from the store.

    Refuses (PricingNotCurrent) unless every partition was priced by the current code over the
    current quotes (require_current), so its code_fingerprint names the code of every row it counts.
    """
    code = code or code_fingerprint()
    require_current(store, code)
    blocks = {name: _records(frame) for name, frame in summary_blocks(store).items()}
    return {"code_fingerprint": code, **blocks}


# --- surface_frames.json (ADR-0001 §5) --------------------------------------------------------

# The fixed grid every frame is read on: log-moneyness -0.30 to +0.20 in steps of 0.02 (the same
# as the illustrative surface, so the two can be compared), and 11 tenors in calendar days.
GRID_MONEYNESS = tuple(round(-0.30 + 0.02 * i, 2) for i in range(26))
GRID_DTE = (7, 14, 21, 30, 45, 60, 90, 120, 180, 270, 365)
FRAME_DECIMALS = 6


def usable_smiles(rows: pd.DataFrame) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """(tau, k_nodes, w_nodes) of every smile with at least MIN_NODES nodes, sorted by tau."""
    usable = []
    for row in rows.sort_values("tau_years").itertuples(index=False):
        if row.tau_years > 0 and row.n_points >= smile.MIN_NODES:
            usable.append((float(row.tau_years), np.asarray(row.k_nodes, dtype=float),
                           np.asarray(row.total_var_nodes, dtype=float)))
    return usable


def surface_frame(smiles: list, grid_k=GRID_MONEYNESS, grid_dte=GRID_DTE) -> dict:
    """{iv[dte][k], cell_flags[dte][k], quoted_share, atm_iv_30d} from one date's usable smiles.

    quoted_share is the share of grid cells read without extrapolation: no SURFACE_EXTRAP_STRIKE
    and no SURFACE_EXTRAP_TENOR (every cell between two listed expiries is SURFACE_CROSS_EXPIRY,
    which is interpolation, so it counts as quoted).
    """
    k = np.asarray(grid_k, dtype=float)
    rows, flag_rows = [], []
    for dte in grid_dte:
        sigma, cell = smile.surface_iv(k, dte / 365, smiles)
        rows.append(sigma)
        flag_rows.append(cell)
    sigma, cells = np.round(np.vstack(rows), FRAME_DECIMALS), np.vstack(flag_rows)
    # surface_iv's w never falls with tau (the calendar constraint), but rounding each IV to 6 decimals
    # can make it fall by ~1e-7 where w is flat in tau. Such a cell is raised by one unit of the last
    # decimal until iv^2 dte / 365, computed as the app computes it, does not fall; if 4 units are not
    # enough, the frame is refused here rather than written for the app to refuse.
    days = np.asarray(grid_dte, dtype=float)
    for i in range(1, days.size):
        for raises in range(5):
            low = sigma[i] * sigma[i] * days[i] / 365 < sigma[i - 1] * sigma[i - 1] * days[i - 1] / 365
            if not low.any():
                break
            if raises == 4:
                raise ValueError(f"rounding to {FRAME_DECIMALS} decimals makes w fall at {int(low.sum())} cells of the "
                                 f"{int(days[i])}-day row even after 4 raises: the surface itself falls there")
            sigma[i] = np.where(low, np.round(sigma[i] + 10.0**-FRAME_DECIMALS, FRAME_DECIMALS), sigma[i])
    extrapolated = (cells & (smile.SURFACE_EXTRAP_STRIKE | smile.SURFACE_EXTRAP_TENOR)) != 0
    # The 30-day ATM IV is the grid's own cell, so the file cannot hold two values for it.
    atm = sigma[list(grid_dte).index(30), list(np.round(k, 2)).index(0.0)]
    return {"iv": sigma.tolist(), "cell_flags": cells.astype(int).tolist(),
            "quoted_share": round(float(1 - extrapolated.mean()), FRAME_DECIMALS), "atm_iv_30d": float(atm)}


def surface_frames_body(store: Store, frames: list[tuple[date, str]], source: str = "optionsdx") -> dict:
    """surface_frames.json after the envelope: the grid, and one frame per (date, label).

    Each frame: date, label, spot (the SPY close), vix_close, the number of usable expiries, and
    surface_frame()'s fields. Every number comes from the store: the app draws, it computes nothing.
    """
    out = []
    for day, label in frames:
        rows = store.query("SELECT tau_years, k_nodes, total_var_nodes, n_points FROM smile_fits "
                           "WHERE source = ? AND quote_date = ? ORDER BY expiry", [source, day])
        smiles = usable_smiles(rows)
        if not smiles:
            raise ValueError(f"{source} has no usable smile on {day}: run tools/build_pricing.py first")
        spot = store.query("SELECT close FROM spy_bars WHERE date = ?", [day])["close"]
        vix = store.query("SELECT close FROM vix WHERE date = ?", [day])["close"]
        out.append({"date": day.isoformat(), "label": label, "spot": round(float(spot.iloc[0]), 2),
                    "vix_close": round(float(vix.iloc[0]), 2), "expiries_used": len(smiles),
                    **surface_frame(smiles)})
    return {"grid_moneyness": list(GRID_MONEYNESS), "grid_dte": list(GRID_DTE),
            "cell_flag_names": list(smile.SURFACE_FLAG_NAMES), "frames": out}
