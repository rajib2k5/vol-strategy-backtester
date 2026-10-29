"""ADR-0009 test 2: the trading calendar comes from SPY bars, and every non-session row is dropped.

The rule (ADR-0009 §1, as changed in round 2 of the M1 review): a chain row dated on a
non-session gets NON_SESSION_DATE in the date map and is dropped from the clean table. It is
never moved, not even onto an empty previous session whose close its underlying matches: that
was the relabel rule, and the one date it moved (OptionsDX 2022-06-20 -> 06-17) held 06-20's
contract list. The match is still reported, as a diagnostic (quality.non_session_check).
"""

from datetime import date

import pandas as pd
import pytest

from volbt.data import calendar, flags, quality, quotes

D = date


def bars(*pairs):
    return pd.DataFrame({"date": [d for d, _ in pairs], "close": [c for _, c in pairs]})


# SPY sessions around Juneteenth and Independence Day 2022. Neither 06-20 nor 07-04 is a session.
SESSIONS = bars((D(2022, 6, 16), 301.37), (D(2022, 6, 17), 302.11), (D(2022, 6, 21), 311.48),
                (D(2022, 7, 1), 318.52), (D(2022, 7, 5), 319.07))


def snapshots(*rows):
    return pd.DataFrame(rows, columns=["source", "vendor_date", "underlying_last"])


def one(frame, **match):
    rows = frame
    for column, value in match.items():
        rows = rows[rows[column] == value]
    assert len(rows) == 1, rows
    return rows.iloc[0]


def test_sessions_map_to_themselves_with_no_flags():
    date_map = calendar.build_date_map(snapshots(("optionsdx", D(2022, 6, 16), 301.37)), SESSIONS)
    row = one(date_map, vendor_date=D(2022, 6, 16))
    assert (row["action"], row["quote_date"], row["flags"]) == ("session", D(2022, 6, 16), 0)


def test_the_2022_06_20_row_is_dropped_although_06_17_has_no_snapshot():
    # 06-17 has no snapshot of its own and the row's underlying equals the 06-17 close: the case
    # the relabel rule moved. The row is dropped, and the date map keeps the session before it.
    date_map = calendar.build_date_map(snapshots(
        ("optionsdx", D(2022, 6, 16), 301.37), ("optionsdx", D(2022, 6, 20), 302.11),
        ("optionsdx", D(2022, 6, 21), 311.48)), SESSIONS)
    row = one(date_map, vendor_date=D(2022, 6, 20))
    assert (row["action"], row["flags"]) == ("drop", flags.NON_SESSION_DATE)
    assert pd.isna(row["quote_date"])
    assert (row["prev_session"], row["prev_close"]) == (D(2022, 6, 17), 302.11)
    assert set(date_map["action"]) == {"session", "drop"}


def test_the_2022_07_04_row_is_flagged_and_dropped():
    date_map = calendar.build_date_map(snapshots(
        ("optionsdx", D(2022, 7, 1), 318.52), ("optionsdx", D(2022, 7, 4), 318.52),
        ("optionsdx", D(2022, 7, 5), 319.07)), SESSIONS)
    row = one(date_map, vendor_date=D(2022, 7, 4))
    assert row["action"] == "drop"
    assert pd.isna(row["quote_date"])
    assert row["flags"] == flags.NON_SESSION_DATE


@pytest.mark.parametrize("underlying", [302.11, 302.13, 302.09, 302.14, 302.08, None])
def test_no_underlying_moves_a_row(underlying):
    # The old $0.02 tolerance, from both sides, and no underlying at all: always a drop.
    date_map = calendar.build_date_map(snapshots(("optionsdx", D(2022, 6, 20), underlying)), SESSIONS)
    assert one(date_map, vendor_date=D(2022, 6, 20))["action"] == "drop"


def test_a_row_without_an_underlying_is_dropped():
    date_map = calendar.build_date_map(snapshots(("dolthub", D(2022, 6, 20), None)), SESSIONS)
    row = one(date_map, source="dolthub")
    assert (row["action"], row["flags"]) == ("drop", flags.NON_SESSION_DATE)


def test_a_date_before_the_first_session_is_dropped_with_no_previous_session():
    date_map = calendar.build_date_map(snapshots(("optionsdx", D(2022, 6, 12), 301.0)), SESSIONS)
    row = one(date_map, vendor_date=D(2022, 6, 12))
    assert row["action"] == "drop" and row["prev_session"] is None and pd.isna(row["prev_close"])


def test_two_closure_dates_in_a_row_are_both_dropped():
    # Sandy: 2012-10-29 and 10-30 were both closures; 10-26 is the session before both.
    sessions = bars((D(2012, 10, 26), 128.46), (D(2012, 10, 31), 128.46))
    date_map = calendar.build_date_map(snapshots(
        ("optionsdx", D(2012, 10, 29), 128.46), ("optionsdx", D(2012, 10, 30), 128.46)), sessions)
    assert list(date_map["action"]) == ["drop", "drop"]
    assert list(date_map["prev_session"]) == [D(2012, 10, 26)] * 2


# --- the diagnostic that replaced the relabel rule ---------------------------------------------

def test_the_non_session_check_reports_the_gap_to_the_previous_close():
    date_map = calendar.build_date_map(snapshots(
        ("optionsdx", D(2022, 6, 16), 301.37), ("optionsdx", D(2022, 6, 20), 302.11),
        ("optionsdx", D(2022, 7, 1), 318.52), ("optionsdx", D(2022, 7, 4), 318.48),
        ("dolthub", D(2022, 6, 20), None)), SESSIONS)
    check = quality.non_session_check(date_map)
    got = {(r.source, r.vendor_date): (r.underlying_minus_prev_close_cents, r.prev_session_has_snapshot)
           for r in check.itertuples()}
    assert got[("optionsdx", D(2022, 6, 20))] == (0, False)        # the 06-17 close, and 06-17 has no snapshot
    assert got[("optionsdx", D(2022, 7, 4))] == (-4, True)          # 4 cents under the 07-01 close
    assert pd.isna(got[("dolthub", D(2022, 6, 20))][0])             # DoltHub has no underlying
    assert len(check) == 3                                          # the dropped dates only


# --- the same rule, through the clean table --------------------------------------------------

def raw(vendor_date, underlying, strike=320.0, call_put="C"):
    return {"source": "optionsdx", "vendor_date": vendor_date, "expiry": D(2022, 7, 15), "strike": strike,
            "call_put": call_put, "bid": 5.0, "ask": 5.1, "last": 5.05, "volume": 100.0,
            "bid_size": 10, "ask_size": 10, "vendor_iv": 0.25, "vendor_delta": 0.4,
            "vendor_gamma": 0.01, "vendor_vega": 0.3, "vendor_theta": -0.2, "vendor_rho": 0.1,
            "underlying_last": underlying}


def test_through_the_clean_table_every_closure_row_is_gone():
    rows = pd.DataFrame([raw(D(2022, 6, 16), 301.37), raw(D(2022, 6, 20), 302.11),
                         raw(D(2022, 7, 1), 318.52), raw(D(2022, 7, 4), 318.52)])
    clean, date_map = quotes.clean_quotes(rows, SESSIONS)
    assert sorted(clean["quote_date"]) == [D(2022, 6, 16), D(2022, 7, 1)]   # 2022-06-17 stays missing
    assert set(clean["vendor_quote_date"]) == {D(2022, 6, 16), D(2022, 7, 1)}
    assert (clean["quality_flags"] & (flags.NON_SESSION_DATE | flags.RELABELLED) == 0).all()
    assert one(date_map, vendor_date=D(2022, 6, 20))["rows"] == 1   # counted, then dropped
    assert one(date_map, vendor_date=D(2022, 7, 4))["rows"] == 1
