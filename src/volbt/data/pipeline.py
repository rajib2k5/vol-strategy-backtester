"""The M1 job: vendor files in, checked tables out (docs/architecture/out/data_flow.mmd, "M1, ingest and clean").

    fetch_reference()   network: SPY bars and dividends, DGS3MO, VIX, VIX3M -> work_dir()/raw/
    export_dolthub()    the DoltHub clone, read-only, -> work_dir()/raw/dolthub/option_chain_spy.parquet
    build()             no network: raw/ + the Kaggle files -> work_dir()/store/

build() in order:
1. reference tables, and the sessions they define;
2. OptionsDX and DoltHub as raw long rows (schema checked first), then option_quotes with its
   flags (quotes.clean);
3. the quality report, then the QUALITY GATE. A failing gate writes the report (so it can be
   read) and stops before option_quotes is written; an old option_quotes is removed, so the
   store never pairs a new report with old quotes;
4. the DoltHub sampling masks (mask.py);
5. the cross-vendor check: distributions and the share of dates inside each chosen threshold,
   pooled and by year (crossvendor.py). Measurements only: nothing in it passes or fails;
6. build_summary.json: the headline numbers. It holds no clock time, so two builds from the
   same inputs give the same bytes; wall times go to build_timings.json instead.
"""

from __future__ import annotations

import shutil
import time
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from volbt import config
from volbt.data import crossvendor, dolthub, flags, mask, optionsdx, quality, quotes, reference
from volbt.data.store import Store, data_fingerprint, write_json

DOLTHUB_EXPORT = Path("dolthub") / "option_chain_spy.parquet"
# The date ADR-0009 asks M1 to check: a Juneteenth snapshot that looks like 2022-06-17's. It is
# dropped like every other non-session date (calendar.py says why); the summary keeps its check.
JUNETEENTH_2022 = date(2022, 6, 20)


class QualityGateError(RuntimeError):
    """The quality gate failed: option_quotes was not written."""


def fetch_reference(raw: Path | None = None) -> dict:
    """Download every reference series. The only network step of M1."""
    root = raw or config.raw_dir()
    return {"fred_dgs3mo": reference.fetch_fred_dgs3mo(root), "cboe_vix": reference.fetch_cboe("VIX", root),
            "cboe_vix3m": reference.fetch_cboe("VIX3M", root), "yfinance_spy": reference.fetch_spy(root)}


def export_dolthub(raw: Path | None = None) -> dict:
    return dolthub.export_spy_rows((raw or config.raw_dir()) / DOLTHUB_EXPORT)


def load_reference(raw: Path) -> dict[str, pd.DataFrame]:
    bars, dividends = reference.parse_spy_csv(raw / "yfinance" / "SPY_daily.csv")
    tables = {"spy_bars": bars, "dividends": dividends,
              "rates": reference.parse_fred_csv(raw / "fred" / "DGS3MO.csv"),
              "vix": reference.parse_cboe_csv(raw / "cboe" / "VIX_History.csv")}
    vix3m = raw / "cboe" / "VIX3M_History.csv"
    if vix3m.exists():
        tables["vix3m"] = reference.parse_cboe_csv(vix3m)
    return tables


def raw_dolthub_rows(con: duckdb.DuckDBPyConnection, parquet: Path) -> pd.DataFrame:
    """DoltHub's rows on every vendor date (before the calendar), with the quote-only flag bits."""
    rows = quotes.to_pandas(con.sql(dolthub.long_rows_sql(parquet)).to_arrow_table())
    rows = rows.rename(columns={"vendor_date": "quote_date"})
    rows["quality_flags"] = flags.mid_flags(flags.cents(rows["bid"]), flags.cents(rows["ask"]))
    return rows


def _no_nan(obj):
    """JSON has no NaN: a number that could not be computed (no overlap dates) is written as null."""
    if isinstance(obj, dict):
        return {key: _no_nan(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_no_nan(value) for value in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def _flag_totals(counts: pd.DataFrame) -> dict:
    return {source: {"rows": int(group["rows"].sum()),
                     **{name: int(group[name].sum()) for name in flags.FLAG_NAMES}}
            for source, group in counts.groupby("source")}


def _summary(clean, date_map, tables, gate, overlap, previous, fingerprint) -> dict:
    calendar = tables["quality_calendar"]
    non_session = tables["quality_non_session_dates"]
    june = non_session[(non_session["source"] == "optionsdx") & (non_session["vendor_date"] == JUNETEENTH_2022)]
    underlying = tables["quality_underlying"]["diff_cents"]
    previous_year = pd.to_datetime(previous["vendor_date"]).dt.year if len(previous) else pd.Series(dtype=int)
    weekend = previous[(previous_year == 2019) | (previous["weekday"].isin(["Saturday", "Sunday"]))] if len(previous) else previous
    holiday = previous.drop(weekend.index) if len(previous) else previous

    def closer_to_prev(part):
        both = part.dropna(subset=["spot_vs_close_prev_bp", "spot_vs_close_next_bp"])
        return {"closer_to_previous_close": int((both["spot_vs_close_prev_bp"].abs()
                                                 < both["spot_vs_close_next_bp"].abs()).sum()),
                "dates_tested": int(len(both)), "dates": int(len(part)),
                "spot_vs_close_prev_bp": crossvendor.distribution(part["spot_vs_close_prev_bp"]),
                "spot_vs_close_next_bp": crossvendor.distribution(part["spot_vs_close_next_bp"]),
                "iv30_diff_prev_pts": crossvendor.distribution(part["iv30_diff_prev_pts"]),
                "iv30_diff_next_pts": crossvendor.distribution(part["iv30_diff_next_pts"])}

    return {
        "input_fingerprint": fingerprint,
        "rows": {source: int(n) for source, n in clean.groupby("source").size().items()},
        "flags": _flag_totals(tables["quality_flag_counts"]),
        "calendar": {f"{r.source}/{r.action}": {"dates": int(r.dates), "rows": int(r.rows)}
                     for r in calendar.itertuples(index=False)},
        "dropped_optionsdx": [str(d) for d in date_map[(date_map["source"] == "optionsdx")
                                                       & (date_map["action"] == "drop")]["vendor_date"]],
        # The diagnostic that replaced the relabel rule: does a dropped date carry the last close?
        "non_session_dates": {
            source: {"dates": int(len(part)), "rows": int(part["rows"].sum()),
                     "underlying_equals_previous_close": int((part["underlying_minus_prev_close_cents"] == 0).sum()),
                     "no_underlying": int(part["underlying_minus_prev_close_cents"].isna().sum()),
                     "previous_session_has_no_snapshot": int((~part["prev_session_has_snapshot"]).sum())}
            for source, part in non_session.groupby("source")},
        "juneteenth_2022": june[["vendor_date", "underlying_last", "prev_session", "prev_close",
                                 "underlying_minus_prev_close_cents", "prev_session_has_snapshot", "rows"]]
        .astype(str).to_dict("records"),
        "underlying_minus_close_cents": {
            "dates": int(len(underlying)), "median_abs": float(np.median(np.abs(underlying))),
            "p95_abs": float(np.percentile(np.abs(underlying), 95)),
            "p99_abs": float(np.percentile(np.abs(underlying), 99)),
            "max_abs": int(np.max(np.abs(underlying))), "zero": int((underlying == 0).sum())},
        "quality_gate": {"passed": gate.passed, "failures": gate.failures},
        "cross_vendor": {
            "overlap_dates": int(len(overlap)),
            "iv30_diff_pts_dolthub_minus_optionsdx": crossvendor.distribution(overlap["iv30_diff_pts"]),
            "spot_dolthub_vs_close_bp": crossvendor.distribution(overlap["spot_dolthub_vs_close_bp"]),
            "spot_optionsdx_vs_close_bp": crossvendor.distribution(overlap["spot_optionsdx_vs_close_bp"]),
            "spot_dolthub_vs_open_bp": crossvendor.distribution(overlap["spot_dolthub_vs_open_bp"]),
            "spot_optionsdx_vs_open_bp": crossvendor.distribution(overlap["spot_optionsdx_vs_open_bp"]),
            # Thresholds chosen after looking at these same dates: shares inside them, no verdict.
            "within_thresholds": crossvendor.within_thresholds(overlap),
            "by_year": crossvendor.by_year(overlap),
            "label": "vendor IVs (each vendor's own IV column), raw-mid parity, no de-Americanisation",
        },
        "previous_session_test": {
            "label": "HYPOTHESIS TEST, not overlap: DoltHub rows dated on a non-session are the previous session's close",
            "weekends_2019_02_09_to_2020_01_04": closer_to_prev(weekend) if len(weekend) else {},
            "closures_2020_on": closer_to_prev(holiday) if len(holiday) else {},
        },
    }


def build(raw: Path | None = None, kaggle: Path | None = None, store: Store | None = None,
          optionsdx_paths: list[Path] | None = None, gate=quality.gate) -> dict:
    """Build the whole store. Returns the summary (also written as build_summary.json).

    `gate` is the quality gate; tests pass a different one to build tiny fixtures that the
    full-data thresholds would rightly refuse.
    """
    raw = raw or config.raw_dir()
    store = store or Store()
    timings: dict[str, float] = {}
    started = clock = time.monotonic()

    def lap(name: str) -> None:
        nonlocal clock
        timings[name] = round(time.monotonic() - clock, 1)
        clock = time.monotonic()

    paths = optionsdx_paths or optionsdx.files(kaggle)
    dolt_parquet = raw / DOLTHUB_EXPORT
    reference_files = sorted(p for p in raw.rglob("*") if p.is_file() and not p.name.endswith(".json"))
    fingerprint = {"optionsdx": data_fingerprint(paths, Path(paths[0]).parent),
                   "raw": data_fingerprint(reference_files, raw)}
    lap("fingerprint")

    ref = load_reference(raw)
    for name, table in ref.items():
        store.write_table(name, table, sort_by=("ex_date",) if name == "dividends" else ("date",))
    lap("reference")

    con = duckdb.connect()
    con.execute(f"CREATE VIEW raw_quotes AS {optionsdx.long_rows_sql(paths)}\nUNION ALL\n"
                f"{dolthub.long_rows_sql(dolt_parquet)}")
    clean, date_map = quotes.clean(con, "raw_quotes", ref["spy_bars"])
    lap("clean")

    tables = quality.report(clean, date_map)
    for name, table in tables.items():
        store.write_table(name, table, sort_by=tuple(c for c in ("source", "year", "quote_date", "vendor_date", "action")
                                                       if c in table.columns))
    verdict = gate(tables)
    if not verdict.passed:
        if store.table_dir("option_quotes").exists():
            shutil.rmtree(store.table_dir("option_quotes"))
        raise QualityGateError("; ".join(verdict.failures))
    store.write_table("option_quotes", clean, sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    store.write_table("calendar_actions", date_map, sort_by=("source", "vendor_date"))
    lap("write_quotes")

    pairs = mask.listed_pairs(clean[clean["source"] == "dolthub"])
    sessions = list(ref["spy_bars"]["date"])
    chain_mask = pd.concat([mask.build_mask(pairs, sessions, m) for m in ("dolthub", "dolthub_daily")],
                           ignore_index=True)
    store.write_table("chain_mask", chain_mask, sort_by=("mask", "quote_date", "expiry", "strike_milli"))
    lap("mask")

    overlap = crossvendor.overlap_table(clean, ref["spy_bars"], ref["rates"], ref["dividends"])
    raw_dolt = raw_dolthub_rows(con, dolt_parquet)
    non_sessions = sorted(date_map[(date_map["source"] == "dolthub") & (date_map["action"] == "drop")]["vendor_date"])
    previous = crossvendor.previous_session_test(raw_dolt, clean, ref["spy_bars"], ref["rates"],
                                                 ref["dividends"], non_sessions)
    store.write_table("cross_vendor_overlap", overlap, sort_by=("quote_date",))
    store.write_table("cross_vendor_previous_session", previous, sort_by=("vendor_date",))
    lap("cross_vendor")

    summary = _no_nan(_summary(clean, date_map, tables, verdict, overlap, previous, fingerprint))
    write_json(summary, store.root / "build_summary.json")
    timings["total"] = round(time.monotonic() - started, 1)
    write_json({"seconds": timings, "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
               store.root / "build_timings.json")
    return summary
