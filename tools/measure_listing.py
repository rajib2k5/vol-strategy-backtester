"""Re-measure the "M" facts of the milestone-4 plan (section 1) from the built store, one labelled line each.

Run:  uv run python tools/measure_listing.py [--store DIR]

Data notice. The DoltHub figures this tool prints (counts and shares of listed expiries) are derived from the
DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>),
licensed CC BY-SA 4.0 (<https://creativecommons.org/licenses/by-sa/4.0/>), and are shared under the same licence.
Changes: we aggregated it into counts and shares and compared it with OptionsDX; no quote row is reproduced.
The rest of this repository is MIT. See DATA.md.

Read-only: the store is opened with volbt.data.store.Store and queried with DuckDB / pyarrow; the yfinance file under
config.raw_dir() is only read. Nothing is written, and no P&L, NAV, return or Sharpe ratio is computed.

measure(store) returns every figure as a dict; main() prints them. Definitions, where the plan's wording is terse:
  - a day's LISTED expiries are the expiries in expiry_forwards for that source and quote date (option_quotes gives
    the same sets; measure() checks it);
  - the standard monthly of the CALENDAR for a month is the third Friday, or the last session before it when the
    third Friday is not a session (volbt.strategies.expiry's rule; it need not be listed on the day);
  - "front listed DTE 14" is read as: the nearest listed expiry is exactly 14 days out. The reading "at most 14 days
    out" is measured too, and reported beside it;
  - for a DoltHub session t and a calendar monthly m with DTE = (m - t).days: m is "listed" if it is among t's
    listed expiries; else "bracketed" if listed expiries exist on both sides of m, "below the front" if m is before
    the nearest listed expiry, "above the back" if after the farthest.
"""

from __future__ import annotations

import argparse
import csv
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from volbt import build, config
from volbt.data.store import Store, session_calendar
from volbt.strategies.expiry import standard_monthly, third_friday
from volbt.view import SPLITS
from volbt.data import store as store_module

DEVELOPMENT_START = SPLITS["development"][0]
YFINANCE_FILE = "SPY_daily.csv"
# The DTE bands of the plan's listing row, in its order: (label, lowest DTE, highest DTE).
BANDS = (("14", 14, 14), ("15-21", 15, 21), ("10-14", 10, 14), ("7", 7, 7), ("50-60", 50, 60),
         ("36-49", 36, 49), ("29-35", 29, 35))
DOLTHUB_PERIODS = (("2020-22", date(2020, 1, 1), date(2022, 12, 31)), ("2023", date(2023, 1, 1), date(2023, 12, 31)))
EXPECTED_FINGERPRINT_MODULES = ("__init__.py", "build.py", "config.py", "view.py", "data/__init__.py",
                                "data/flags.py", "data/store.py", "pricing/*.py")


def window_counts(sessions, start: date, end: date, days: int = 30) -> Counter:
    """For each session t in [start, end]: the number of sessions in (t, t + days calendar days]; a Counter of those."""
    ordered = sorted(sessions)
    counts = Counter()
    for day in ordered:
        if start <= day <= end:
            counts[bisect_right(ordered, day + timedelta(days=days)) - bisect_right(ordered, day)] += 1
    return counts


def calendar_monthlies(sessions, first: date, last: date) -> list[date]:
    """The standard monthly of the calendar for every month from first's to last's: the third Friday, or, when it is
    not a session, the last session before it. Ascending. Sessions must cover the months asked for."""
    days = set(sessions)
    found = []
    for year in range(first.year, last.year + 1):
        for month in range(1, 13):
            if (year, month) < (first.year, first.month) or (year, month) > (last.year, last.month):
                continue
            expiry = third_friday(year, month)
            while expiry not in days:
                expiry -= timedelta(days=1)
            found.append(expiry)
    return found


def listed_by_day(store: Store, source: str, first: date, last: date, table: str = "expiry_forwards") -> dict:
    """{quote date: set of listed expiry dates} for one source between first and last, inclusive."""
    frame = store.query(f"SELECT DISTINCT quote_date, expiry FROM {table} WHERE source = ? "
                        "AND quote_date BETWEEN ? AND ?", [source, first, last])
    listed = defaultdict(set)
    for quote_date, expiry in zip(frame.quote_date, frame.expiry):
        listed[quote_date.date()].add(expiry.date())
    return dict(listed)


def monthly_in_dte_range(listed: dict, sessions, low: int, high: int) -> int:
    """Days on which a standard monthly (volbt.strategies.expiry.standard_monthly) is listed with low <= DTE <= high."""
    days = frozenset(sessions)
    return sum(any(low <= (m - day).days <= high for m in standard_monthly(expiries, days))
               for day, expiries in listed.items())


def front_dte_counts(listed: dict) -> dict:
    """Sessions, and how many have the nearest listed expiry exactly 14 days out / at most 14 days out."""
    fronts = [(min(expiries) - day).days for day, expiries in listed.items()]
    return {"sessions": len(fronts), "front_eq_14": sum(f == 14 for f in fronts),
            "front_le_14": sum(f <= 14 for f in fronts)}


def monthly_listing(listed: dict, monthlies, low: int, high: int) -> dict:
    """Over all (session t, calendar monthly m) pairs with low <= (m - t).days <= high: how many pairs, how many have
    m listed on t, and, for the rest, whether m is bracketed by listed expiries, below the front, or above the back."""
    out = Counter()
    for day, expiries in listed.items():
        front, back = min(expiries), max(expiries)
        for m in monthlies:
            if low <= (m - day).days <= high:
                out["pairs"] += 1
                if m in expiries:
                    out["listed"] += 1
                elif m < front:
                    out["below_front"] += 1
                elif m > back:
                    out["above_back"] += 1
                else:
                    out["bracketed"] += 1
    return {key: out[key] for key in ("pairs", "listed", "bracketed", "below_front", "above_back")}


def yfinance_rows(path: Path) -> dict:
    """Rows of the raw yfinance file, and how many carry a non-zero 'Stock Splits' value. Read only."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {"rows": len(rows), "split_rows": sum(float(row["Stock Splits"]) != 0 for row in rows)}


def measure(store: Store) -> dict:
    """Every figure of plan section 1's M rows, keyed by fact."""
    out = {}
    cal = session_calendar(store)
    bars = store.query("SELECT COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last, "
                       "COUNT(*) FILTER (WHERE date < ?) AS before FROM spy_bars", [DEVELOPMENT_START]).iloc[0]
    out["spy_bars"] = {"rows": int(bars.n), "first": bars["first"].date(), "last": bars["last"].date(),
                       "before_2010_01_04": int(bars.before),
                       "view_columns": store_module.UPTO_READS["spy_bars"][2],
                       "view_sql_has_adj_close": "adj_close" in store_module.VIEW_SQL["spy_bars"],
                       "upto_reads_has_adj_close": "adj_close" in store_module.UPTO_READS["spy_bars"][2]}
    div = store.query("SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE ex_date < ?) AS before FROM dividends",
                      [date(2010, 1, 1)]).iloc[0]
    out["dividends"] = {"rows": int(div.n), "before_2010": int(div.before),
                        "yfinance": yfinance_rows(config.raw_dir() / "yfinance" / YFINANCE_FILE)}
    out["sessions_per_split"] = {name: sum(a <= d <= b for d in cal) for name, (a, b) in SPLITS.items()}
    out["window_30d"] = dict(sorted(window_counts(cal, *SPLITS["development"]).items()))
    dev_listed = listed_by_day(store, "optionsdx", *SPLITS["development"])
    dev_quotes = listed_by_day(store, "optionsdx", *SPLITS["development"], table="option_quotes")
    out["optionsdx_50_60"] = {"snapshots": len(dev_listed), "with_monthly_50_60": monthly_in_dte_range(dev_listed, cal, 50, 60),
                              "quotes_agree_with_forwards": dev_quotes == dev_listed}
    dolthub = {}
    for label, first, last in DOLTHUB_PERIODS:
        listed = listed_by_day(store, "dolthub", first, last)
        monthlies = calendar_monthlies(cal, first, last + timedelta(days=90))
        dolthub[label] = {"front": front_dte_counts(listed),
                          "monthly_14_listed_days": monthly_in_dte_range(listed, cal, 14, 14),
                          "bands": {name: monthly_listing(listed, monthlies, low, high) for name, low, high in BANDS}}
    out["dolthub"] = dolthub
    out["fingerprint_modules"] = tuple(build.FINGERPRINT_MODULES)
    out["fingerprint_modules_match"] = tuple(build.FINGERPRINT_MODULES) == EXPECTED_FINGERPRINT_MODULES
    return out


def share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def print_report(figures: dict) -> None:
    bars, div = figures["spy_bars"], figures["dividends"]
    print(f"spy_bars: {bars['rows']:,} rows, {bars['first']} to {bars['last']}; {bars['before_2010_01_04']:,} before "
          f"{DEVELOPMENT_START}; view columns {list(bars['view_columns'])}; adj_close in view SQL "
          f"{bars['view_sql_has_adj_close']}, in UPTO_READS {bars['upto_reads_has_adj_close']}")
    print(f"dividends: {div['rows']} rows, {div['before_2010']} before 2010; yfinance file {div['yfinance']['rows']:,} rows, "
          f"{div['yfinance']['split_rows']} split rows")
    print("sessions per split: " + ", ".join(f"{k} {v:,}" for k, v in figures["sessions_per_split"].items()))
    window = figures["window_30d"]
    print(f"sessions in (t, t+30 days], development: range {min(window)}-{max(window)}; "
          + ", ".join(f"{k} on {v:,}" for k, v in sorted(window.items(), key=lambda kv: -kv[1])))
    ox = figures["optionsdx_50_60"]
    print(f"OptionsDX development snapshots with a standard monthly at 50-60 DTE: {ox['with_monthly_50_60']:,} of "
          f"{ox['snapshots']:,} (option_quotes dates and expiries equal expiry_forwards': {ox['quotes_agree_with_forwards']})")
    for label, block in figures["dolthub"].items():
        front = block["front"]
        print(f"DoltHub {label}: {front['sessions']} sessions; nearest listed expiry exactly 14 DTE on "
              f"{front['front_eq_14']}, at most 14 DTE on {front['front_le_14']}; a standard monthly at exactly 14 DTE listed on "
              f"{block['monthly_14_listed_days']} sessions")
        for name, row in block["bands"].items():
            print(f"  monthly at DTE {name}: {row['pairs']} pairs, listed {row['listed']} ({share(row['listed'], row['pairs'])}), "
                  f"bracketed {row['bracketed']}, below the front {row['below_front']}, above the back {row['above_back']}")
    print(f"FINGERPRINT_MODULES: {', '.join(figures['fingerprint_modules'])} (equals the plan's list: "
          f"{figures['fingerprint_modules_match']})")
    print("DoltHub figures: derived from post-no-preference/options, CC BY-SA 4.0; see the data notice in this file's docstring.")


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=None, help="store folder (default: work_dir()/store)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    store = Store(args.store)
    if not store.has("spy_bars"):
        print("error: no built store: run tools/build_data.py and tools/build_pricing.py", file=sys.stderr)
        return 2
    print_report(measure(store))
    return 0


if __name__ == "__main__":
    sys.exit(main())
