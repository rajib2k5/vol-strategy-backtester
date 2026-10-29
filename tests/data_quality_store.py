"""A tiny built store for the data_quality.json exporter tests (not a test file: pytest does not collect it).

It holds the three report tables the exporter reads and a build_summary.json, written with the real
Store writer, in the shapes the M1 build writes. The numbers are small enough to check by hand:
tests/test_export_data_quality.py works out the expected file from them.

    dolthub    2019 (10 quotes on one thin date, before the gate checks DoltHub), 2020, 2021
    optionsdx  2010, 2011
"""

from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd

from volbt.data import flags
from volbt.data.store import Store, write_json

# (source, year, quotes, {flag: quotes carrying it})
FLAG_ROWS = [
    ("dolthub", 2019, 10, {"ZERO_BID": 1, "VOLUME_UNRELIABLE": 10}),
    ("dolthub", 2020, 1000, {"ZERO_BID": 100, "CROSSED": 5, "STALE": 20, "VOLUME_UNRELIABLE": 1000}),
    ("dolthub", 2021, 2000, {"ZERO_BID": 300, "CROSSED": 8, "VOLUME_UNRELIABLE": 2000}),
    ("optionsdx", 2010, 4000, {"BID_NULL": 120, "ASK_NULL": 120, "ZERO_BID": 400, "STALE": 40,
                               "VENDOR_IV_INVALID": 200, "VOLUME_UNRELIABLE": 4000}),
    ("optionsdx", 2011, 8000, {"BID_NULL": 80, "ASK_NULL": 80, "CROSSED": 16, "UNDERLYING_MISMATCH": 400,
                               "VENDOR_IV_INVALID": 240, "VOLUME_UNRELIABLE": 8000}),
]
# (source, action, vendor dates, quotes). The calendar keeps a session or drops the date (since
# round 2 of the M1 review there is no relabel), so the session rows equal the dates below.
CALENDAR_ROWS = [
    ("dolthub", "drop", 2, 7),
    ("dolthub", "session", 5, 3010),
    ("optionsdx", "drop", 1, 6),
    ("optionsdx", "session", 4, 12000),
]
# (source, quote date, quotes). The sums per source equal FLAG_ROWS' quotes.
DATE_ROWS = [
    ("dolthub", "2019-05-10", 10),
    ("dolthub", "2020-01-06", 400),
    ("dolthub", "2020-01-08", 600),
    ("dolthub", "2021-03-01", 1200),
    ("dolthub", "2021-03-02", 800),
    ("optionsdx", "2010-01-04", 1500),
    ("optionsdx", "2010-01-05", 2500),
    ("optionsdx", "2011-01-03", 3000),
    ("optionsdx", "2011-01-04", 5000),
]

SUMMARY = {
    "cross_vendor": {
        "label": "vendor IVs (each vendor's own IV column), raw-mid parity, no de-Americanisation",
        "overlap_dates": 100,
        "iv30_diff_pts_dolthub_minus_optionsdx": {
            "n": 98, "mean": 0.123456789, "mean_abs": 0.5, "p05": -0.25, "p25": 0.125, "median": 0.25,
            "p75": 0.5, "p95": 1.5},
        "spot_dolthub_vs_close_bp": {
            "n": 100, "mean": 1.0, "mean_abs": 9.0, "p05": -18.0, "p25": -4.5, "median": 1.5,
            "p75": 7.5, "p95": 21.0},
        "spot_optionsdx_vs_close_bp": {
            "n": 100, "mean": 0.0, "mean_abs": 5.0, "p05": -10.0, "p25": -3.5, "median": -0.5,
            "p75": 2.0, "p95": 12.5},
        "spot_dolthub_vs_open_bp": {
            "n": 100, "mean": 6.5, "mean_abs": 70.0, "p05": -156.0, "p25": -37.5, "median": 13.0,
            "p75": 60.5, "p95": 140.0},
        "spot_optionsdx_vs_open_bp": {
            "n": 100, "mean": 5.5, "mean_abs": 69.5, "p05": -163.0, "p25": -44.0, "median": 12.0,
            "p75": 63.5, "p95": 137.5},
        "within_thresholds": {"iv30_pts": 1.0, "iv30_dates": 98, "iv30_share_within": 0.96,
                              "spot_bp": 25.0, "spot_dates": 100, "spot_share_within": 0.875},
        "by_year": {"year": [2020, 2021], "dates": [40, 60], "iv30_share_within": [0.95, 0.9666666666],
                    "spot_dolthub_share_within": [0.8, 0.925],
                    "spot_dolthub_vs_close_median_bp": [2.5, -1.25],
                    "spot_optionsdx_vs_close_median_bp": [1.1, -0.5]},
    },
    "quality_gate": {"passed": True, "failures": []},
    "underlying_minus_close_cents": {"dates": 4, "max_abs": 60, "median_abs": 3.0, "p95_abs": 12.0, "p99_abs": 24.0},
}


def flag_counts_frame() -> pd.DataFrame:
    records = [{"source": source, "year": year, "rows": rows, **{name: carrying.get(name, 0) for name in flags.FLAG_NAMES}}
               for source, year, rows, carrying in FLAG_ROWS]
    return pd.DataFrame(records).astype({"year": "int32"})


def calendar_frame() -> pd.DataFrame:
    return pd.DataFrame(CALENDAR_ROWS, columns=["source", "action", "dates", "rows"])


def rows_per_date_frame() -> pd.DataFrame:
    frame = pd.DataFrame(DATE_ROWS, columns=["source", "quote_date", "rows"])
    return frame.assign(quote_date=pd.to_datetime(frame["quote_date"]).astype("datetime64[us]"))


def make_store(root: Path, summary: dict | None = None, skip: tuple[str, ...] = ()) -> Store:
    """Write the tiny store under root. `summary` replaces build_summary.json; `skip` names files to leave out."""
    store = Store(root)
    tables = {"quality_flag_counts": (flag_counts_frame(), ("source", "year")),
              "quality_calendar": (calendar_frame(), ("source", "action")),
              "quality_rows_per_date": (rows_per_date_frame(), ("source", "quote_date"))}
    for name, (frame, sort_by) in tables.items():
        if name not in skip:
            store.write_table(name, frame, sort_by=sort_by)
    if "build_summary.json" not in skip:
        write_json(copy.deepcopy(SUMMARY) if summary is None else summary, root / "build_summary.json")
    return store
