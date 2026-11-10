"""Tests for tools/measure_listing.py: the helpers on made-up calendars, and the plan's "M" facts on the real store.

The real-data tests (marked real_data) assert the figures of milestone-4 plan section 1 where they reproduce. Where
the re-measure gave another number, the assertion pins the measured figure and the comment names the plan's row.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import measure_listing  # noqa: E402
from volbt.data.store import Store  # noqa: E402


def weekdays(first, last):
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return [d for d in days if d.weekday() < 5]


def test_window_counts_counts_sessions_after_t_up_to_t_plus_days():
    # From Monday 2021-03-01 the window (t, 03-31] holds Tue 03-02 .. Wed 03-31: 22 weekdays.
    sessions = weekdays(date(2021, 3, 1), date(2021, 4, 30))
    counts = measure_listing.window_counts(sessions, date(2021, 3, 1), date(2021, 3, 1))
    assert counts == {22: 1}
    # From Fri 2021-03-05 the window is 03-08 .. 04-04: 20 weekdays (4 full weeks).
    assert measure_listing.window_counts(sessions, date(2021, 3, 5), date(2021, 3, 5)) == {20: 1}


def test_window_counts_respects_the_bounds_and_the_day_count():
    sessions = weekdays(date(2021, 3, 1), date(2021, 3, 31))
    assert sum(measure_listing.window_counts(sessions, date(2021, 3, 8), date(2021, 3, 12)).values()) == 5
    assert measure_listing.window_counts(sessions, date(2021, 3, 1), date(2021, 3, 1), days=7) == {5: 1}


def test_calendar_monthlies_third_friday_or_the_session_before():
    # 2022-04-15 (Good Friday) is not a session, so April 2022 is Thursday 04-14; March 2022 is Friday 03-18.
    sessions = [d for d in weekdays(date(2022, 3, 1), date(2022, 5, 31)) if d != date(2022, 4, 15)]
    found = measure_listing.calendar_monthlies(sessions, date(2022, 3, 1), date(2022, 5, 31))
    assert found == [date(2022, 3, 18), date(2022, 4, 14), date(2022, 5, 20)]


def test_monthly_listing_classifies_listed_bracketed_and_below_the_front():
    day = date(2022, 3, 1)
    listed = {day: {date(2022, 3, 4), date(2022, 3, 18), date(2022, 4, 29)}}
    # DTE 17 listed; DTE 24 is between listed expiries (bracketed); DTE 2 is below the front; DTE 60 is above the back.
    monthlies = [day + timedelta(days=n) for n in (2, 17, 24, 60)]
    row = measure_listing.monthly_listing(listed, monthlies, 0, 100)
    assert row == {"pairs": 4, "listed": 1, "bracketed": 1, "below_front": 1, "above_back": 1}
    assert measure_listing.monthly_listing(listed, monthlies, 20, 30)["bracketed"] == 1


def test_front_dte_counts_distinguishes_exactly_14_from_at_most_14():
    listed = {date(2022, 3, 1): {date(2022, 3, 15)}, date(2022, 3, 2): {date(2022, 3, 9)},
              date(2022, 3, 3): {date(2022, 3, 31)}}
    assert measure_listing.front_dte_counts(listed) == {"sessions": 3, "front_eq_14": 1, "front_le_14": 2}


# --- the plan's facts on the real store ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def figures():
    store = Store()
    if not store.has("smile_fits"):
        pytest.skip("no built store: run tools/build_data.py and tools/build_pricing.py")
    return measure_listing.measure(store)


@pytest.mark.real_data
def test_spy_bars_and_dividends(figures):
    bars = figures["spy_bars"]
    assert (bars["rows"], str(bars["first"]), str(bars["last"]), bars["before_2010_01_04"]) == \
        (6746, "2000-01-03", "2026-10-28", 2515)
    assert not bars["view_sql_has_adj_close"] and not bars["upto_reads_has_adj_close"]
    div = figures["dividends"]
    assert (div["rows"], div["before_2010"]) == (108, 41)
    assert div["yfinance"] == {"rows": 6746, "split_rows": 0}


@pytest.mark.real_data
def test_sessions_and_the_thirty_day_window(figures):
    assert figures["sessions_per_split"] == {"development": 2516, "validation": 1006, "holdout": 707}
    window = figures["window_30d"]
    assert (min(window), max(window)) == (17, 22)
    assert (window[21], window[20], window[19]) == (1001, 590, 339)


@pytest.mark.real_data
def test_optionsdx_monthly_at_50_60_dte(figures):
    ox = figures["optionsdx_50_60"]
    assert ox["snapshots"] == 2497 and ox["quotes_agree_with_forwards"]
    # Plan row "OptionsDX development snapshots with a standard monthly at 50-60 DTE" says 1,001; the re-measure
    # (inclusive 50..60, standard_monthly on the full SPY calendar) gives 1,010. 1,001 is the count of days with 21
    # sessions in the 30-day window, probably a slip.
    assert ox["with_monthly_50_60"] == 1010


@pytest.mark.real_data
def test_dolthub_front_listed_dte(figures):
    early, late = figures["dolthub"]["2020-22"]["front"], figures["dolthub"]["2023"]["front"]
    # Plan row "DoltHub front listed DTE": 404 of 432 and 120 of 144 reproduce as "nearest listed expiry is exactly 14 DTE".
    assert (early["front_eq_14"], early["sessions"]) == (404, 432)
    assert (late["front_eq_14"], late["sessions"]) == (120, 144)
    assert (early["front_le_14"], late["front_le_14"]) == (418, 144)       # the "at most 14" reading


@pytest.mark.real_data
def test_dolthub_monthly_listing_by_dte(figures):
    def cells(period, band):
        row = figures["dolthub"][period]["bands"][band]
        return row["pairs"], row["listed"], row["bracketed"], row["below_front"]

    assert cells("2020-22", "14") == (31, 31, 0, 0) and cells("2023", "14") == (11, 11, 0, 0)
    assert cells("2020-22", "15-21") == (98, 0, 98, 0) and cells("2023", "15-21") == (31, 0, 31, 0)
    # Plan row, band 10-14: 54.1% for 2020-22; the re-measure is 33 of 62 pairs = 53.2% (no tried band gives 54.1%).
    assert cells("2020-22", "10-14") == (62, 33, 0, 29) and cells("2023", "10-14") == (21, 16, 0, 5)
    assert cells("2020-22", "7") == (34, 0, 0, 34) and cells("2023", "7") == (12, 0, 0, 12)
    assert cells("2020-22", "50-60") == (162, 162, 0, 0) and cells("2023", "50-60") == (54, 54, 0, 0)
    assert cells("2020-22", "36-49") == (202, 65, 137, 0) and cells("2023", "36-49") == (66, 20, 46, 0)
    assert cells("2020-22", "29-35") == (98, 1, 97, 0) and cells("2023", "29-35") == (33, 11, 22, 0)
    assert figures["dolthub"]["2020-22"]["monthly_14_listed_days"] == 31


@pytest.mark.real_data
def test_fingerprint_modules(figures):
    assert figures["fingerprint_modules"] == ("__init__.py", "build.py", "config.py", "view.py", "data/__init__.py",
                                              "data/flags.py", "data/store.py", "pricing/*.py")
