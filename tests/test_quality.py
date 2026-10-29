"""The quality report counts what it should, and the gate fails on the thresholds it states.

Every limit is written out here, not read from quality.py: a test that took its numbers from the
code under test would move with them, and a mutant such as "DoltHub minimum rows 40 -> 0" would
pass. Each limit is tested from both sides: just past it fails, exactly at it passes.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from volbt.data import flags, quality


def clean(rows_flags, source="optionsdx", year=2022):
    n = len(rows_flags)
    return pd.DataFrame({"source": [source] * n, "year": [year] * n, "quote_date": [date(year, 3, 14)] * n,
                         "quality_flags": rows_flags, "underlying_last": [420.0] * n, "spy_close": [420.0] * n})


def test_flag_counts_count_each_bit_separately():
    counts = quality.flag_counts(clean([flags.ZERO_BID | flags.VENDOR_IV_INVALID, flags.ZERO_BID, 0]))
    row = counts.iloc[0]
    assert (row["rows"], row["ZERO_BID"], row["VENDOR_IV_INVALID"], row["CROSSED"]) == (3, 2, 1, 0)


def test_underlying_check_is_per_date_and_in_cents():
    frame = pd.DataFrame({"source": ["optionsdx"] * 3, "quote_date": [date(2022, 7, 1)] * 2 + [date(2022, 7, 5)],
                          "underlying_last": [318.48, 318.48, 319.07], "spy_close": [318.52, 318.52, 319.07]})
    check = quality.underlying_check(frame)
    assert list(check["diff_cents"]) == [-4, 0]


# --- a healthy report, then one thing broken at a time -------------------------------------------

YEARS = {"optionsdx": range(2010, 2024), "dolthub": range(2020, 2027)}
ROWS_PER_YEAR = 10_000          # per source-year in quality_flag_counts
# Dates a year in the healthy report: comfortably above each regime's minimum, below what it measured.
HEALTHY_DATES = {"optionsdx": dict.fromkeys(range(2010, 2024), 240),
                 "dolthub": {**dict.fromkeys(range(2020, 2024), 140), 2024: 170, 2025: 240, 2026: 195}}


def weekdays(year: int, n: int) -> list[date]:
    days, day = [], date(year, 1, 2)
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def report(dates_per_year=None, rows_per_date=None, flag_counts=None, dropped=None, underlying_cents=None,
           extra_dates=()):
    """A report that passes: both sources, every expected year, every count comfortably inside its limit.

    dates_per_year {(source, year): n} and the other arguments override single entries.
    extra_dates adds (source, date, rows) rows to quality_rows_per_date.
    """
    dates_per_year = {(s, y): HEALTHY_DATES[s][y] for s, ys in YEARS.items() for y in ys} | (dates_per_year or {})
    rows_per_date = {"optionsdx": 2000, "dolthub": 100} | (rows_per_date or {})
    per_date = [(s, d, rows_per_date[s]) for (s, y), n in sorted(dates_per_year.items()) for d in weekdays(y, n)]
    per_date += list(extra_dates)
    counts = []
    for (source, year) in sorted(dates_per_year):
        carrying = (flag_counts or {}).get((source, year), {})
        counts.append({"source": source, "year": year, "rows": ROWS_PER_YEAR,
                       **{name: carrying.get(name, 0) for name in flags.FLAG_NAMES}})
    dropped = {"optionsdx": 11, "dolthub": 103} | (dropped or {})
    return {
        "quality_flag_counts": pd.DataFrame(counts),
        "quality_calendar": pd.DataFrame({"source": list(dropped), "action": ["drop"] * len(dropped),
                                          "dates": list(dropped.values()), "rows": [0] * len(dropped)}),
        "quality_rows_per_date": pd.DataFrame(per_date, columns=["source", "quote_date", "rows"]),
        "quality_underlying": pd.DataFrame({"diff_cents": [3] * 100 if underlying_cents is None else underlying_cents}),
    }


def test_the_healthy_report_passes():
    assert quality.gate(report()) == quality.GateResult(passed=True, failures=[])


def test_the_dates_in_the_report_can_be_timestamps_read_back_from_the_store():
    tables = report()
    tables["quality_rows_per_date"]["quote_date"] = pd.to_datetime(tables["quality_rows_per_date"]["quote_date"])
    assert quality.gate(tables).passed


# Presence: the M1 review's three reports that used to pass.

def test_an_empty_report_fails():
    empty = {name: table.iloc[0:0] for name, table in report().items()}
    result = quality.gate(empty)
    assert not result.passed
    assert "optionsdx: no rows in the report" in result.failures
    assert "dolthub: no rows in the report" in result.failures
    assert "optionsdx: no dates to compare UNDERLYING_LAST with the SPY close" in result.failures


@pytest.mark.parametrize("source", ["optionsdx", "dolthub"])
def test_a_report_without_one_source_fails(source):
    tables = {name: (table[table["source"] != source] if "source" in table else table)
              for name, table in report().items()}
    result = quality.gate(tables)
    assert f"{source}: no rows in the report" in result.failures


def test_optionsdx_cut_to_one_year_fails():
    tables = report(dates_per_year={("optionsdx", y): 0 for y in range(2010, 2024) if y != 2022})
    result = quality.gate(tables)
    assert not result.passed
    assert any(f.startswith("optionsdx: 13 of the years 2010-2023 (daily) have fewer than 230 snapshot dates")
               for f in result.failures), result.failures


# Coverage: dates per year, by sampling regime, and in all. The limits are written out here.

REGIMES = {  # (source, year): (the span of its regime as the failure names it, minimum)
    **{("optionsdx", y): ("the years 2010-2023 (daily)", 230) for y in range(2010, 2024)},
    **{("dolthub", y): ("the years 2020-2023 (Mon/Wed/Fri)", 120) for y in range(2020, 2024)},
    ("dolthub", 2024): ("the year 2024 (Mon/Wed/Fri to 09-09 with no dates 07-30 to 08-09, then daily)", 140),
    ("dolthub", 2025): ("the year 2025 (daily)", 200),
    ("dolthub", 2026): ("the year 2026 (daily, a partial year: the export ends on 2026-10-26)", 160),
}


@pytest.mark.parametrize("source, year", [("optionsdx", 2010), ("optionsdx", 2011), ("optionsdx", 2023),
                                          ("dolthub", 2020), ("dolthub", 2021), ("dolthub", 2023),
                                          ("dolthub", 2024), ("dolthub", 2025), ("dolthub", 2026)])
def test_each_year_needs_its_regime_s_minimum_of_snapshot_dates(source, year):
    span, minimum = REGIMES[(source, year)]
    assert quality.gate(report(dates_per_year={(source, year): minimum})).passed
    result = quality.gate(report(dates_per_year={(source, year): minimum - 1}))
    assert result.failures == [f"{source}: 1 of {span} have fewer than {minimum} snapshot dates "
                               f"(first {year}: {minimum - 1})"]


def test_a_daily_dolthub_year_cannot_lose_half_its_dates():
    # The round-2 finding: 120 a year was set on the Mon/Wed/Fri years, so 2025 (248 dates) could
    # have lost half of them and passed.
    assert not quality.gate(report(dates_per_year={("dolthub", 2025): 124})).passed
    assert not quality.gate(report(dates_per_year={("dolthub", 2026): 120})).passed
    assert quality.gate(report(dates_per_year={("dolthub", 2021): 120})).passed


def test_a_missing_year_fails_and_a_year_outside_the_span_is_not_required():
    tables = report()
    rows = tables["quality_rows_per_date"]
    without_2015 = rows[~((rows["source"] == "optionsdx") & (pd.to_datetime(rows["quote_date"]).dt.year == 2015))]
    result = quality.gate({**tables, "quality_rows_per_date": without_2015})
    assert any("(first 2015: 0)" in f for f in result.failures), result.failures
    # DoltHub's single 2019 date, before its span, changes nothing.
    assert quality.gate(report(extra_dates=[("dolthub", date(2019, 6, 7), 66)])).passed


# Exactly at each total, with every year at or above its own minimum: the totals boundary itself.
AT_THE_TOTAL = {
    "optionsdx": ({("optionsdx", y): 236 if y < 2020 else 235 for y in range(2010, 2024)}, 3300),   # 10 x 236 + 4 x 235
    "dolthub": ({("dolthub", 2020): 140, ("dolthub", 2021): 120, ("dolthub", 2022): 120, ("dolthub", 2023): 120,
                 ("dolthub", 2024): 140, ("dolthub", 2025): 200, ("dolthub", 2026): 160}, 1000),
}


@pytest.mark.parametrize("source, first_year", [("optionsdx", 2010), ("dolthub", 2020)])
def test_each_source_needs_its_minimum_of_dates_in_all(source, first_year):
    at, total = AT_THE_TOTAL[source]
    assert sum(at.values()) == total
    assert quality.gate(report(dates_per_year=at)).passed                       # exactly at the total passes
    one_short = at | {(source, first_year): at[(source, first_year)] - 1}       # still above its year's minimum
    result = quality.gate(report(dates_per_year=one_short))
    assert result.failures == [f"{source}: {total - 1} snapshot dates in all (minimum {total})"]


# Rows per date.

@pytest.mark.parametrize("source, minimum", [("optionsdx", 1000), ("dolthub", 40)])
def test_every_date_needs_its_minimum_of_rows(source, minimum):
    assert quality.gate(report(rows_per_date={source: minimum})).passed
    result = quality.gate(report(rows_per_date={source: minimum - 1}))
    assert not result.passed
    assert result.failures[0].startswith(f"{source}: ") and f"fewer than {minimum} rows" in result.failures[0]


def test_one_thin_dolthub_date_in_the_window_fails():
    # The mutant "DoltHub minimum rows 40 -> 0" passes this report; the real gate must not.
    thin = report(extra_dates=[("dolthub", date(2022, 6, 15), 39)])
    assert quality.gate(thin).failures == ["dolthub: 1 dates with fewer than 40 rows (first 2022-06-15)"]
    assert quality.gate(report(extra_dates=[("dolthub", date(2022, 6, 15), 40)])).passed


def test_a_thin_dolthub_date_before_2020_01_06_is_not_checked():
    assert quality.gate(report(extra_dates=[("dolthub", date(2020, 1, 4), 10)])).passed
    assert not quality.gate(report(extra_dates=[("dolthub", date(2020, 1, 6), 10)])).passed


# Flag shares: every (source, flag) limit. ROWS_PER_YEAR = 10,000, so a limit of 5% is 500 rows.

@pytest.mark.parametrize("source, flag, limit", [
    ("optionsdx", "BID_NULL", 0.05), ("optionsdx", "ASK_NULL", 0.05), ("optionsdx", "CROSSED", 0.01),
    ("optionsdx", "VENDOR_IV_INVALID", 0.12), ("optionsdx", "UNDERLYING_MISMATCH", 0.08),
    ("dolthub", "BID_NULL", 0.01), ("dolthub", "ASK_NULL", 0.01), ("dolthub", "CROSSED", 0.01),
    ("dolthub", "VENDOR_IV_INVALID", 0.01),
])
def test_each_flag_share_limit(source, flag, limit):
    year = min(YEARS[source])
    at = round(limit * ROWS_PER_YEAR)
    assert quality.gate(report(flag_counts={(source, year): {flag: at}})).passed
    result = quality.gate(report(flag_counts={(source, year): {flag: at + 1}}))
    assert result.failures == [f"{source} {year}: {flag} on {(at + 1) / ROWS_PER_YEAR:.2%} of rows (limit {limit:.0%})"]


def test_market_flags_have_no_limit():
    market = {name: ROWS_PER_YEAR for name in ("ZERO_BID", "LOCKED", "WIDE", "STALE", "VOLUME_UNRELIABLE", "EXPIRY_DAY")}
    assert quality.gate(report(flag_counts={("optionsdx", 2010): market, ("dolthub", 2020): market})).passed


# The calendar and the underlying.

@pytest.mark.parametrize("source, limit", [("optionsdx", 15), ("dolthub", 130)])
def test_too_many_dropped_dates_fail(source, limit):
    assert quality.gate(report(dropped={source: limit})).passed
    result = quality.gate(report(dropped={source: limit + 1}))
    assert result.failures == [f"{source}: the calendar dropped {limit + 1} vendor dates (limit {limit})"]


def test_a_wide_underlying_gap_fails():
    assert quality.gate(report(underlying_cents=[50] * 100)).passed
    result = quality.gate(report(underlying_cents=[51] * 100))
    assert result.failures == ["optionsdx: p99 |UNDERLYING_LAST - close| is 51 cents (limit 50)"]


def test_every_failure_is_listed():
    broken = report(flag_counts={("optionsdx", 2012): {"CROSSED": 200, "BID_NULL": 600}}, dropped={"optionsdx": 99})
    assert len(quality.gate(broken).failures) == 3
