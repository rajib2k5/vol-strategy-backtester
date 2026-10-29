"""ADR-0009 tests 3 and 4: one fixture row per flag, each setting exactly the stated bits.

Every row goes through the real cleaning step (quotes.clean_quotes), so the test covers the
wiring as well as the rule. The baseline row is clean on purpose: OptionsDX, a 2022 session,
volume and vendor IV known, UNDERLYING_LAST equal to the SPY close, not an expiry day. A
flag test then changes one thing and expects one bit.
"""

from datetime import date

import pandas as pd
import pytest

from volbt.data import flags, quotes

D = date
MON, TUE, WED = D(2022, 3, 14), D(2022, 3, 15), D(2022, 3, 16)
SESSIONS = pd.DataFrame({
    "date": [D(2020, 12, 31), D(2021, 1, 4), MON, TUE, WED],
    "close": [301.22, 296.54, 420.00, 420.00, 420.00],
})


def row(**changes):
    base = {"source": "optionsdx", "vendor_date": MON, "expiry": D(2022, 4, 14), "strike": 420.0,
            "call_put": "C", "bid": 1.00, "ask": 1.10, "last": 1.05, "volume": 10.0,
            "bid_size": 5, "ask_size": 5, "vendor_iv": 0.20, "vendor_delta": 0.5,
            "vendor_gamma": 0.01, "vendor_vega": 0.3, "vendor_theta": -0.1, "vendor_rho": 0.1,
            "underlying_last": 420.00}
    base.update(changes)
    return base


def flags_of(*rows, sessions=SESSIONS):
    clean, _ = quotes.clean_quotes(pd.DataFrame(list(rows)), sessions)
    return clean.sort_values(["quote_date", "osi_symbol"])["quality_flags"].tolist()


def test_the_bit_positions():
    assert [flags.FLAG_BITS[name] for name in flags.FLAG_NAMES] == list(range(13))
    assert flags.FLAG_NAMES[:3] == ("BID_NULL", "ASK_NULL", "ZERO_BID")
    assert flags.EXPIRY_DAY == 1 << 12
    assert flags.flag_names(flags.NON_SESSION_DATE | flags.RELABELLED) == ["NON_SESSION_DATE", "RELABELLED"]


def test_the_baseline_row_sets_no_bit():
    assert flags_of(row()) == [0]


# ADR-0009 test 3, the table, and one row for every other flag.
@pytest.mark.parametrize("changes, bits", [
    ({"bid": 0.00, "ask": 0.05}, [2]),                         # ZERO_BID only (not also WIDE)
    ({"bid": 1.10, "ask": 1.00}, [3]),                         # CROSSED
    ({"bid": 2.00, "ask": 2.00}, [4]),                         # LOCKED
    ({"bid": 0.10, "ask": 0.40}, [5]),                         # WIDE: spread 0.30 > mid 0.25 (120%)
    ({"bid": 0.10, "ask": 0.30}, []),                          # exactly 100%: not WIDE (strict >)
    ({"bid": None, "ask": 1.00}, [0]),                         # BID_NULL
    ({"bid": 1.00, "ask": None}, [1]),                         # ASK_NULL
    ({"bid": None, "ask": None}, [0, 1]),
    ({"bid": 0.00, "ask": 0.00}, [2]),                         # zero/zero is not LOCKED (needs > 0)
    ({"volume": None}, [9]),                                   # VOLUME_UNRELIABLE: null volume
    ({"vendor_iv": None}, [11]),                               # VENDOR_IV_INVALID: null
    ({"vendor_iv": 0.0}, [11]),                                # ... zero (5,984 OptionsDX rows, 70 DoltHub)
    ({"vendor_iv": -0.0005}, [11]),                            # ... negative: OptionsDX's lowest
    ({"vendor_iv": -0.00001}, [11]),                           # ... and its least negative
    ({"vendor_iv": 0.00001}, []),                              # the smallest positive IV is valid
    ({"vendor_iv": 6.0}, []),                                  # IV above 5 is extreme but not flagged
    ({"expiry": MON}, [12]),                                   # EXPIRY_DAY: tau = 0
])
def test_one_row_per_flag(changes, bits):
    assert flags_of(row(**changes)) == [sum(1 << b for b in bits)]


@pytest.mark.parametrize("underlying, mismatch", [
    (420.43, True),    # |420.43/420 - 1| = 0.1024% > 0.10%
    (419.57, True),
    (420.42, False),   # exactly 0.10%: not a mismatch (strict >)
    (420.00, False),
])
def test_underlying_mismatch(underlying, mismatch):
    assert flags_of(row(underlying_last=underlying)) == [flags.UNDERLYING_MISMATCH if mismatch else 0]


@pytest.mark.parametrize("vendor_date, unreliable", [
    (D(2020, 12, 31), True),   # OptionsDX before 2021-01-04: volume under-counted
    (D(2021, 1, 4), False),    # the first reliable day
])
def test_volume_era(vendor_date, unreliable):
    close = SESSIONS.set_index("date")["close"][vendor_date]
    got = flags_of(row(vendor_date=vendor_date, expiry=D(2021, 2, 19), underlying_last=close))
    assert got == [flags.VOLUME_UNRELIABLE if unreliable else 0]


def test_a_dolthub_row_is_always_volume_unreliable_and_has_no_underlying_check():
    dolt = row(source="dolthub", volume=None, last=None, bid_size=None, ask_size=None, underlying_last=None)
    assert flags_of(dolt) == [flags.VOLUME_UNRELIABLE]


def test_a_closure_row_never_reaches_the_table_so_bits_7_and_8_stay_clear():
    # RELABELLED (bit 8) is reserved and never set since the relabel rule was removed (M1 review,
    # round 2), and every NON_SESSION_DATE row is dropped. The row below is the old relabel case.
    sessions = pd.DataFrame({"date": [D(2022, 6, 16), D(2022, 6, 17), D(2022, 6, 21)],
                             "close": [301.37, 302.11, 311.48]})
    got = flags_of(row(vendor_date=D(2022, 6, 16), expiry=D(2022, 7, 15), underlying_last=301.37),
                   row(vendor_date=D(2022, 6, 20), expiry=D(2022, 7, 15), underlying_last=302.11),
                   sessions=sessions)
    assert got == [0]
    assert flags.FLAG_BITS["RELABELLED"] == 8 and flags.RELABELLED == 256      # the number stays reserved


# --- ADR-0009 test 4: STALE ------------------------------------------------------------------

def stale_pair(close_mon, close_tue, tue_changes=None):
    sessions = pd.DataFrame({"date": [MON, TUE], "close": [close_mon, close_tue]})
    first = row(vendor_date=MON, underlying_last=close_mon)
    second = row(vendor_date=TUE, underlying_last=close_tue, **(tue_changes or {}))
    return flags_of(first, second, sessions=sessions)


def test_stale_when_spot_moves_one_percent_and_the_quote_does_not():
    assert stale_pair(400.00, 404.00) == [0, flags.STALE]


def test_not_stale_when_spot_moves_a_quarter_percent():
    assert stale_pair(400.00, 401.00) == [0, 0]


@pytest.mark.parametrize("close_tue, stale", [(402.00, True), (401.99, False), (396.00, True), (398.00, True)])
def test_the_half_percent_threshold_is_inclusive_and_two_sided(close_tue, stale):
    assert stale_pair(400.00, close_tue) == [0, flags.STALE if stale else 0]


def test_not_stale_when_the_quote_moved():
    assert stale_pair(400.00, 404.00, {"ask": 1.11}) == [0, 0]
    assert stale_pair(400.00, 404.00, {"bid": 0.99}) == [0, 0]


def test_stale_compares_with_the_contract_s_own_previous_snapshot():
    # Quoted Monday and Wednesday, absent on Tuesday: Wednesday is compared with Monday.
    sessions = pd.DataFrame({"date": [MON, TUE, WED], "close": [400.00, 402.00, 404.00]})
    other = row(vendor_date=TUE, strike=500.0, underlying_last=402.00)   # keeps Tuesday a snapshot date
    got = flags_of(row(vendor_date=MON, underlying_last=400.00), other,
                   row(vendor_date=WED, underlying_last=404.00), sessions=sessions)
    assert got == [0, 0, flags.STALE]


def test_stale_is_per_contract_not_per_strike():
    # The put at the same strike is a different contract: no previous snapshot, so no STALE.
    sessions = pd.DataFrame({"date": [MON, TUE], "close": [400.00, 404.00]})
    got = flags_of(row(vendor_date=MON, underlying_last=400.00),
                   row(vendor_date=TUE, call_put="P", underlying_last=404.00), sessions=sessions)
    assert got == [0, 0]


def test_stale_is_per_expiry_too():
    # Same source, side and strike but another expiry: a different contract, so no previous
    # snapshot. (A LAG window partitioned without the expiry would compare it with Monday's quote.)
    sessions = pd.DataFrame({"date": [MON, TUE], "close": [400.00, 404.00]})
    got = flags_of(row(vendor_date=MON, underlying_last=400.00),
                   row(vendor_date=TUE, expiry=D(2022, 5, 20), underlying_last=404.00), sessions=sessions)
    assert got == [0, 0]


def test_null_quotes_are_not_stale():
    assert stale_pair(400.00, 404.00, {"bid": None}) == [0, flags.BID_NULL]
