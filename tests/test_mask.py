"""ADR-0009 test 7: the DoltHub sampling mask, on a small hand-made chain.

DoltHub lists (expiry, strike) pairs on Mon 2022-06-13 and Wed 2022-06-15, and nothing on Tue
2022-06-14. OptionsDX lists a denser chain on all three days.
"""

from datetime import date

import pandas as pd
import pytest

from volbt.data import mask

D = date
MON, TUE, WED, THU = D(2022, 6, 13), D(2022, 6, 14), D(2022, 6, 15), D(2022, 6, 16)
E1, E2, E3 = D(2022, 7, 1), D(2022, 7, 15), D(2022, 8, 19)
SESSIONS = [MON, TUE, WED, THU]


def chain(day, pairs, sides=("C", "P")):
    return pd.DataFrame([{"quote_date": day, "expiry": e, "strike": k, "call_put": s}
                         for e, k in pairs for s in sides])


DOLTHUB = pd.concat([
    chain(MON, [(E1, 400.0), (E1, 405.0)]),
    # (E2, 415) is listed by DoltHub only: OptionsDX has no such strike, so it cannot survive.
    chain(WED, [(E1, 400.0), (E1, 410.0), (E2, 410.0), (E2, 415.0)], sides=("C",)),
], ignore_index=True)
OPTIONSDX_PAIRS = [(E1, 400.0), (E1, 402.0), (E1, 405.0), (E1, 410.0), (E2, 410.0), (E3, 420.0), (E2, 410.5)]
OPTIONSDX = pd.concat([chain(day, OPTIONSDX_PAIRS) for day in (MON, TUE, WED, THU)], ignore_index=True)


def masked(mask_name, day):
    pairs = mask.build_mask(mask.listed_pairs(DOLTHUB), SESSIONS, mask_name, window=(MON, THU))
    rows = mask.apply_mask(OPTIONSDX, pairs)
    return rows[[q == day for q in rows["quote_date"]]]


def pair_set(rows):
    return {(e, k) for e, k in zip(rows["expiry"], rows["strike"])}


def test_wednesday_keeps_exactly_the_pairs_both_vendors_have():
    rows = masked("dolthub", WED)
    assert pair_set(rows) == {(E1, 400.0), (E1, 410.0), (E2, 410.0)}
    # A pair keeps both sides, although DoltHub listed only the call that day.
    assert sorted(rows["call_put"]) == ["C", "C", "C", "P", "P", "P"]


def test_tuesday_is_empty_under_dolthub():
    assert masked("dolthub", TUE).empty


def test_tuesday_keeps_monday_s_pairs_under_dolthub_daily():
    assert pair_set(masked("dolthub_daily", TUE)) == {(E1, 400.0), (E1, 405.0)}
    pairs = mask.build_mask(mask.listed_pairs(DOLTHUB), SESSIONS, "dolthub_daily", window=(MON, THU))
    assert set(pairs[pairs["quote_date"] == TUE]["listed_on"]) == {MON}


def test_thursday_carries_wednesday_and_the_listed_days_are_unchanged():
    assert pair_set(masked("dolthub_daily", THU)) == {(E1, 400.0), (E1, 410.0), (E2, 410.0)}
    assert pair_set(masked("dolthub_daily", WED)) == pair_set(masked("dolthub", WED))


def test_a_monday_dolthub_lacks_is_not_filled_and_tuesday_carries_the_last_listing():
    # Only Tue/Thu sessions are carried (ADR-0009 §4, M'); a missing Mon/Wed/Fri stays empty.
    # DoltHub lists Friday and Wednesday, not Monday: Monday stays empty, and Tuesday takes the
    # last listing before it, Friday's.
    fri = D(2022, 6, 10)
    dolthub = pd.concat([chain(fri, [(E1, 395.0)]), DOLTHUB[[q != MON for q in DOLTHUB["quote_date"]]]],
                        ignore_index=True)
    pairs = mask.build_mask(mask.listed_pairs(dolthub), [fri, *SESSIONS], "dolthub_daily", window=(fri, THU))
    assert MON not in set(pairs["quote_date"])
    tuesday = pairs[pairs["quote_date"] == TUE]
    assert set(tuesday["listed_on"]) == {fri} and set(tuesday["strike_milli"]) == {395000}


def test_an_expired_pair_is_not_carried():
    # Listed on Monday, expiring on Monday itself: by Tuesday it no longer exists.
    expiring = pd.concat([DOLTHUB, chain(MON, [(MON, 399.0)])], ignore_index=True)
    pairs = mask.build_mask(mask.listed_pairs(expiring), SESSIONS, "dolthub_daily", window=(MON, THU))
    tuesday = pairs[pairs["quote_date"] == TUE]
    assert 399000 not in set(tuesday["strike_milli"])


def test_strikes_match_as_integer_thousandths():
    # 410.5 is not 410 or 411, and a float like 410.50000000001 is still 410.5.
    assert list(mask.strike_milli([410.5, 410.50000000001, 400.0])) == [410500, 410500, 400000]


def test_the_window_bounds_the_mask():
    pairs = mask.build_mask(mask.listed_pairs(DOLTHUB), SESSIONS, "dolthub", window=(TUE, THU))
    assert set(pairs["quote_date"]) == {WED}


def test_unknown_mask_names_are_refused():
    with pytest.raises(ValueError):
        mask.build_mask(mask.listed_pairs(DOLTHUB), SESSIONS, "none")
