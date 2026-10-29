"""The quality report and the quality gate.

REPORT. For each (source, year): the row count and how many rows carry each of the 13 flags;
the vendor dates the calendar kept or dropped, and their rows; per OptionsDX date,
UNDERLYING_LAST minus the SPY close (ADR-0009 asks for the distribution, not just the
UNDERLYING_MISMATCH count, because the 0.10% tolerance, about $0.45, hides a cents-level gap);
and, per dropped vendor date, its underlying minus the previous session's close, a diagnostic
of what the closure-dated snapshots are (the relabel rule it once fed is gone: calendar.py).

GATE. A function that passes or fails the report against stated thresholds. In the M1 job a
failing gate stops the build before option_quotes is written (docs/architecture/out/
data_flow.mmd: "fail -> back to the loader"). The thresholds were set on 2026-10-29 AFTER looking at the full-data report
(docs/milestones/01-data-layer.md, "Measured results"): each sits beyond the worst source-year
seen, with headroom, so the gate passes today's data and fails a file that is clearly worse.
It is a tripwire for a broken download or a broken loader, not a statement that the data is good.

A missing source fails it too. Until the M1 review (R2) every check was "no row is worse
than X", so a report with no rows at all, no DoltHub, or OptionsDX cut to one year passed.
Now each source must be present and cover its expected years with enough snapshot dates. The
minimum per year follows the source's sampling regime (round 2 of the review: DoltHub's 120 a
year was set on its Mon/Wed/Fri years, so a daily year could lose half its dates and pass).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from volbt.data.flags import FLAG_NAMES

# Max share of a source-year's rows that may carry the flag. Flags that describe the market
# rather than a broken feed (ZERO_BID, LOCKED, WIDE, STALE, VOLUME_UNRELIABLE, EXPIRY_DAY) have no
# limit. In brackets: the worst source-year in the full build of 2026-10-29
# (`uv run python tools/build_data.py`, report table quality_flag_counts).
GATE_MAX_SHARE: dict[tuple[str, str], float] = {
    ("optionsdx", "BID_NULL"): 0.05,              # [3.02%, 2010]
    ("optionsdx", "ASK_NULL"): 0.05,              # [3.02%, 2010]
    ("optionsdx", "CROSSED"): 0.01,               # [0.38%, 2017]
    ("optionsdx", "VENDOR_IV_INVALID"): 0.12,     # [8.42%, 2016; null only, before 2026-10-29: 7.57%, 2023]
    ("optionsdx", "UNDERLYING_MISMATCH"): 0.08,   # [3.99%, 2013]
    ("dolthub", "BID_NULL"): 0.01,                # [0.00%]
    ("dolthub", "ASK_NULL"): 0.01,                # [0.00%]
    ("dolthub", "CROSSED"): 0.01,                 # [0.07%, 2026]
    ("dolthub", "VENDOR_IV_INVALID"): 0.01,       # [0.17%, 2021: zero vols]
}
# Every source must be in the report and cover its expected years: at least `minimum` snapshot
# dates in EACH year of a span, by the source's sampling regime, and GATE_MIN_DATES in all.
# Each minimum is about 80% of the fewest dates measured in its regime. DoltHub's spans start in
# 2020: in 2019 it has weekly Saturday snapshots, which the calendar drops. The last row is a
# partial year, and a new year needs a new row: the spans are edited by hand as the data grows.
# (source, first year, last year, minimum in each year, regime)  [measured 2026-10-29]
GATE_DATES_PER_YEAR = (
    ("optionsdx", 2010, 2023, 230, "daily"),                          # [245-252, fewest 245 in 2011]
    ("dolthub", 2020, 2023, 120, "Mon/Wed/Fri"),                      # [143-145, fewest 143 in 2021]
    ("dolthub", 2024, 2024, 140, "Mon/Wed/Fri to 09-09 with no dates 07-30 to 08-09, then daily"),  # [173 = 97 + 76]
    ("dolthub", 2025, 2025, 200, "daily"),                            # [248 of 250 sessions]
    ("dolthub", 2026, 2026, 160, "daily, a partial year: the export ends on 2026-10-26"),  # [198 of 205 sessions]
)
GATE_SOURCES = ("optionsdx", "dolthub")
GATE_MIN_DATES = {"optionsdx": 3300, "dolthub": 1000}             # [3,496 and 1,196]
# A source must have at least this many rows on every date it lists (DoltHub from 2020-01-06,
# after its 2019 weekly snapshots). [OptionsDX min 1,790 on 2010-01-19; DoltHub min 60, Jan-2020]
GATE_MIN_ROWS_PER_DATE = {"optionsdx": 1000, "dolthub": 40}
# The calendar may drop at most this many vendor dates. [OptionsDX 12; DoltHub 103]
GATE_MAX_DROPPED_DATES = {"optionsdx": 15, "dolthub": 130}
# |UNDERLYING_LAST - SPY close| in cents: the 99th percentile over OptionsDX dates. [24 cents]
GATE_MAX_UNDERLYING_P99_CENTS = 50
# Where DoltHub's rows-per-date check starts: the cross-vendor window (ADR-0009 §5).
DOLTHUB_CHECKED_FROM = date(2020, 1, 6)


def flag_counts(clean: pd.DataFrame) -> pd.DataFrame:
    """One row per (source, year): rows, then one column per flag with the number of rows carrying it."""
    flags = np.asarray(clean["quality_flags"], dtype=np.int64)
    frame = pd.DataFrame({"source": np.asarray(clean["source"]), "year": np.asarray(clean["year"])})
    for bit, name in enumerate(FLAG_NAMES):
        frame[name] = ((flags >> bit) & 1).astype(np.int64)
    counts = frame.groupby(["source", "year"], sort=True).sum()
    counts.insert(0, "rows", frame.groupby(["source", "year"], sort=True).size())
    return counts.reset_index()


def calendar_counts(date_map: pd.DataFrame) -> pd.DataFrame:
    """Per (source, action): vendor dates and rows. Action is session or drop."""
    frame = date_map.assign(rows=pd.to_numeric(date_map["rows"]).fillna(0).astype("int64"))
    return (frame.groupby(["source", "action"], sort=True)
            .agg(dates=("vendor_date", "size"), rows=("rows", "sum")).reset_index())


def underlying_check(clean: pd.DataFrame) -> pd.DataFrame:
    """Per OptionsDX quote date: UNDERLYING_LAST, the SPY close, and the difference in cents and bp."""
    rows = clean[clean["source"] == "optionsdx"][["quote_date", "underlying_last", "spy_close"]]
    per_date = rows.drop_duplicates("quote_date").sort_values("quote_date").reset_index(drop=True)
    diff = np.rint(per_date["underlying_last"].to_numpy(float) * 100) - np.rint(per_date["spy_close"].to_numpy(float) * 100)
    per_date["diff_cents"] = diff.astype(np.int64)
    per_date["diff_bp"] = (per_date["underlying_last"] / per_date["spy_close"] - 1) * 1e4
    return per_date


def non_session_check(date_map: pd.DataFrame) -> pd.DataFrame:
    """Per dropped vendor date: its UNDERLYING_LAST against the previous session's SPY close.

    A diagnostic only: it says whether a closure-dated snapshot carries the last close (all 12
    OptionsDX ones do, to the cent), and nothing is moved on the strength of it. Columns:
    source, vendor_date, rows, underlying_last, prev_session, prev_close,
    underlying_minus_prev_close_cents (null when the vendor gives no underlying, as DoltHub, or
    there is no earlier session), and prev_session_has_snapshot (the source has its own
    snapshot on prev_session).
    """
    kept = date_map[date_map["action"] == "session"]
    have = set(zip(kept["source"], kept["vendor_date"]))
    dropped = date_map[date_map["action"] == "drop"].sort_values(["source", "vendor_date"])
    out = dropped[["source", "vendor_date", "rows", "underlying_last", "prev_session", "prev_close"]].reset_index(drop=True)
    underlying = pd.to_numeric(out["underlying_last"]).to_numpy(dtype=float, na_value=np.nan)
    prev_close = pd.to_numeric(out["prev_close"]).to_numpy(dtype=float, na_value=np.nan)
    out["underlying_minus_prev_close_cents"] = pd.array(np.rint(underlying * 100) - np.rint(prev_close * 100),
                                                        dtype="Float64").round().astype("Int64")
    out["prev_session_has_snapshot"] = [(s, p) in have for s, p in zip(out["source"], out["prev_session"])]
    return out


def rows_per_date(clean: pd.DataFrame) -> pd.DataFrame:
    return (clean.groupby(["source", "quote_date"], sort=True).size()
            .rename("rows").reset_index())


def report(clean: pd.DataFrame, date_map: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "quality_flag_counts": flag_counts(clean),
        "quality_calendar": calendar_counts(date_map),
        "quality_underlying": underlying_check(clean),
        "quality_rows_per_date": rows_per_date(clean),
        "quality_non_session_dates": non_session_check(date_map),
    }


@dataclass
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)


def gate(tables: dict[str, pd.DataFrame], dolthub_from: date = DOLTHUB_CHECKED_FROM) -> GateResult:
    """Check the report against the thresholds above. Every failure is listed, not just the first."""
    failures = []
    counts = tables["quality_flag_counts"]
    per_date = tables["quality_rows_per_date"]
    for source in GATE_SOURCES:
        if not (counts["source"] == source).any() or not (per_date["source"] == source).any():
            failures.append(f"{source}: no rows in the report")
    for row in counts.to_dict("records"):
        for (source, name), limit in GATE_MAX_SHARE.items():
            if row["source"] == source and row["rows"] and row[name] / row["rows"] > limit:
                failures.append(f"{source} {row['year']}: {name} on {row[name] / row['rows']:.2%} of rows "
                                f"(limit {limit:.0%})")
    # Whatever date type the table carries (date objects, arrow dates, timestamps read back).
    day = pd.to_datetime(per_date["quote_date"])
    for source, minimum in GATE_MIN_ROWS_PER_DATE.items():
        mine = per_date["source"] == source
        if source == "dolthub" and dolthub_from is not None:
            mine &= day >= pd.Timestamp(dolthub_from)
        thin = per_date[mine & (per_date["rows"] < minimum)]
        if len(thin):
            failures.append(f"{source}: {len(thin)} dates with fewer than {minimum} rows "
                            f"(first {thin['quote_date'].iloc[0]})")
    for source in GATE_SOURCES:
        years = day[per_date["source"] == source].dt.year
        if len(years) < GATE_MIN_DATES[source]:
            failures.append(f"{source}: {len(years)} snapshot dates in all (minimum {GATE_MIN_DATES[source]})")
    for source, first, last, minimum, regime in GATE_DATES_PER_YEAR:
        per_year = day[per_date["source"] == source].dt.year.value_counts()
        short = [(year, int(per_year.get(year, 0))) for year in range(first, last + 1)
                 if per_year.get(year, 0) < minimum]
        if short:
            span = f"the years {first}-{last}" if last > first else f"the year {first}"
            failures.append(f"{source}: {len(short)} of {span} ({regime}) have fewer than {minimum} "
                            f"snapshot dates (first {short[0][0]}: {short[0][1]})")
    calendar = tables["quality_calendar"]
    for source, limit in GATE_MAX_DROPPED_DATES.items():
        dropped = calendar[(calendar["source"] == source) & (calendar["action"] == "drop")]["dates"].sum()
        if dropped > limit:
            failures.append(f"{source}: the calendar dropped {dropped} vendor dates (limit {limit})")
    underlying = tables["quality_underlying"]
    if not len(underlying):
        failures.append("optionsdx: no dates to compare UNDERLYING_LAST with the SPY close")
    else:
        p99 = float(np.percentile(np.abs(underlying["diff_cents"]), 99))
        if p99 > GATE_MAX_UNDERLYING_P99_CENTS:
            failures.append(f"optionsdx: p99 |UNDERLYING_LAST - close| is {p99:.0f} cents "
                            f"(limit {GATE_MAX_UNDERLYING_P99_CENTS})")
    return GateResult(passed=not failures, failures=failures)
