"""The cross-vendor arithmetic on hand-made chains whose answer is known exactly."""

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from volbt.data import crossvendor as cv
from volbt.data.flags import VENDOR_IV_INVALID, ZERO_BID

D = date
DAY = D(2022, 3, 14)
NO_DIVIDENDS = pd.DataFrame({"ex_date": [], "amount": []})


def parity_chain(spot, r, days, strikes, dividend=None, iv=0.2):
    """Calls and puts priced so that C - P = DF * (F - K) holds exactly."""
    tau = days / 365
    df = math.exp(-r * tau)
    pv = 0.0
    if dividend:
        ex_date, amount = dividend
        pv = amount * math.exp(-r * (ex_date - DAY).days / 365)
    forward = (spot - pv) / df
    rows = []
    for k in strikes:
        put = 3.0 + abs(k - spot) * 0.01          # any put price; the call follows from parity
        call = put + df * (forward - k)
        expiry = DAY + pd.Timedelta(days=days)
        rows += [{"expiry": expiry.date() if hasattr(expiry, "date") else expiry, "strike": k, "call_put": "C",
                  "bid": call - 0.01, "ask": call + 0.01, "vendor_iv": iv, "quality_flags": 0},
                 {"expiry": expiry.date() if hasattr(expiry, "date") else expiry, "strike": k, "call_put": "P",
                  "bid": put - 0.01, "ask": put + 0.01, "vendor_iv": iv, "quality_flags": 0}]
    return pd.DataFrame(rows)


def test_parity_recovers_the_spot_without_dividends():
    rows = parity_chain(400.0, 0.05, 14, np.arange(390.0, 411.0, 1.0))
    points = cv.common_points(rows, rows)
    spot, expiry = cv.parity_spot(points, DAY, 0.05, NO_DIVIDENDS, "a")
    assert spot == pytest.approx(400.0, abs=1e-9)
    assert expiry == D(2022, 3, 28)


def test_parity_adds_back_the_dividend():
    ex = D(2022, 3, 18)
    rows = parity_chain(400.0, 0.05, 14, np.arange(390.0, 411.0, 1.0), dividend=(ex, 1.5))
    dividends = pd.DataFrame({"ex_date": [ex], "amount": [1.5]})
    spot, _ = cv.parity_spot(cv.common_points(rows, rows), DAY, 0.05, dividends, "a")
    assert spot == pytest.approx(400.0, abs=1e-9)
    # Leaving the dividend out shows up as almost exactly its present value: 1.5 * e^(-0.05 * 4/365).
    wrong, _ = cv.parity_spot(cv.common_points(rows, rows), DAY, 0.05, NO_DIVIDENDS, "a")
    assert 400.0 - wrong == pytest.approx(1.5 * math.exp(-0.05 * 4 / 365), abs=1e-9)


def test_parity_takes_the_median_over_exactly_five_strikes():
    # C and P are closest at K* = 401. The five strikes nearest it are 401, 400, 402, 399 and 403.
    # Make the call 10 cents too dear at 401, at 402 and at every strike outside those five. The
    # median of the five F_K is then exact (three of five are). The median over 1, 2, 3, 4, 6 or
    # 7 strikes is not: at least half of each of those sets is off.
    strikes = np.arange(390.0, 411.0, 1.0)
    rows = parity_chain(400.0, 0.05, 14, strikes)
    off = {401.0, 402.0} | (set(strikes) - {399.0, 400.0, 401.0, 402.0, 403.0})
    dear = (rows["call_put"] == "C") & rows["strike"].isin(off)
    rows.loc[dear, ["bid", "ask"]] += 0.10
    spot, _ = cv.parity_spot(cv.common_points(rows, rows), DAY, 0.05, NO_DIVIDENDS, "a")
    assert spot == pytest.approx(400.0, abs=1e-9)


def test_expiries_under_a_week_are_skipped_for_parity():
    near = parity_chain(400.0, 0.05, 3, np.arange(395.0, 406.0, 1.0))
    far = parity_chain(400.0, 0.05, 14, np.arange(395.0, 406.0, 1.0))
    _, expiry = cv.parity_spot(cv.common_points(pd.concat([near, far]), pd.concat([near, far])),
                               DAY, 0.05, NO_DIVIDENDS, "a")
    assert expiry == D(2022, 3, 28)


def test_iv30_interpolates_in_total_variance():
    # 20 days at 20% and 40 days at 30%. w(30) = (0.04*20 + 0.09*40)/2/365 = 2.2/365, so
    # iv30 = sqrt(2.2/30) = 0.2708013.
    a = parity_chain(400.0, 0.0, 20, [400.0], iv=0.20)
    b = parity_chain(400.0, 0.0, 40, [400.0], iv=0.30)
    rows = pd.concat([a, b], ignore_index=True)
    assert cv.atm_iv30(cv.common_points(rows, rows), DAY, 400.0, "a") == pytest.approx(math.sqrt(2.2 / 30), abs=1e-12)


def test_iv30_uses_the_two_expiries_around_30_days_not_the_outermost():
    # 10 and 20 days below 30, 40 and 60 above. Only 20 days (20%) and 40 days (30%) count, so
    # the answer is the two-expiry one above, sqrt(2.2/30). 10 and 60 days carry vols far off.
    rows = pd.concat([parity_chain(400.0, 0.0, days, [400.0], iv=iv)
                      for days, iv in ((10, 0.50), (20, 0.20), (40, 0.30), (60, 0.90))], ignore_index=True)
    assert cv.atm_iv30(cv.common_points(rows, rows), DAY, 400.0, "a") == pytest.approx(math.sqrt(2.2 / 30), abs=1e-12)


def test_iv30_needs_an_expiry_on_each_side_of_30_days():
    rows = parity_chain(400.0, 0.0, 20, [400.0])
    assert math.isnan(cv.atm_iv30(cv.common_points(rows, rows), DAY, 400.0, "a"))


def iv30_chain_with_a_bad_atm_call(bad_iv, flag):
    """20 and 40 days at 20% on strikes 400 and 401; the 400 call (the ATM strike for spot 400) is `bad_iv`."""
    rows = pd.concat([parity_chain(400.0, 0.0, 20, [400.0, 401.0], iv=0.20),
                      parity_chain(400.0, 0.0, 40, [400.0, 401.0], iv=0.20)], ignore_index=True)
    bad = (rows["strike"] == 400.0) & (rows["call_put"] == "C")
    rows.loc[bad, "vendor_iv"] = bad_iv
    rows.loc[bad, "quality_flags"] = flag
    return rows


@pytest.mark.parametrize("bad_iv", [0.0, -0.0005, math.nan])
def test_iv30_leaves_out_points_with_an_invalid_vendor_iv(bad_iv):
    # Counting the 400 call at 0.0 / -0.0005 would average the ATM node to (bad + 0.20) / 2 and pull
    # iv30 far below 20%. Leaving the flagged point out moves the ATM to 401, where both sides read 20%.
    rows = iv30_chain_with_a_bad_atm_call(bad_iv, VENDOR_IV_INVALID)
    assert cv.atm_iv30(cv.common_points(rows, rows), DAY, 400.0, "a") == pytest.approx(0.20, abs=1e-12)


def test_iv30_leaves_the_point_out_when_only_the_other_vendor_flags_it():
    # Both vendors are measured on the same points: vendor b's invalid IV on the 400 call also takes
    # that point out of a, whose own IV there is a clean 30% (against 20% at 401). Left in, a's ATM
    # would be 400 and its iv30 30%; left out, the ATM moves to 401 and a reads 20%.
    a = pd.concat([parity_chain(400.0, 0.0, days, [400.0], iv=0.30) for days in (20, 40)]
                  + [parity_chain(400.0, 0.0, days, [401.0], iv=0.20) for days in (20, 40)], ignore_index=True)
    b = iv30_chain_with_a_bad_atm_call(0.0, VENDOR_IV_INVALID)
    assert cv.atm_iv30(cv.common_points(a, b), DAY, 400.0, "a") == pytest.approx(0.20, abs=1e-12)


def test_iv30_keeps_points_that_carry_only_other_flags():
    # A zero bid does not make the vendor IV invalid: only the VENDOR_IV_INVALID bit takes a point out.
    # The 400 call (10%) and put (20%) average to 15% at both expiries, so iv30 is 15%.
    rows = iv30_chain_with_a_bad_atm_call(0.10, ZERO_BID)
    assert cv.atm_iv30(cv.common_points(rows, rows), DAY, 400.0, "a") == pytest.approx(0.15, abs=1e-12)


def test_only_points_both_vendors_list_are_compared():
    a = parity_chain(400.0, 0.05, 14, [395.0, 400.0, 405.0])
    b = parity_chain(400.0, 0.05, 14, [400.0, 405.0, 410.0])
    points = cv.common_points(a, b)
    assert sorted(set(points["strike_milli"])) == [400000, 405000]


def test_the_vendor_suffix_selects_the_vendor():
    a = parity_chain(400.0, 0.0, 20, [400.0], iv=0.20)
    b = parity_chain(400.0, 0.0, 20, [400.0], iv=0.25)
    a40, b40 = parity_chain(400.0, 0.0, 40, [400.0], iv=0.20), parity_chain(400.0, 0.0, 40, [400.0], iv=0.25)
    points = cv.common_points(pd.concat([a, a40]), pd.concat([b, b40]))
    assert cv.atm_iv30(points, DAY, 400.0, "a") == pytest.approx(0.20)
    assert cv.atm_iv30(points, DAY, 400.0, "b") == pytest.approx(0.25)


def overlap(iv_diffs, spot_bps, days=None, spot_optionsdx=None):
    n = len(iv_diffs)
    return pd.DataFrame({"quote_date": days or [D(2022, 3, 14)] * n, "iv30_diff_pts": iv_diffs,
                         "spot_dolthub_vs_close_bp": spot_bps,
                         "spot_optionsdx_vs_close_bp": spot_optionsdx or [0.0] * n})


def test_the_shares_inside_the_thresholds_are_measured_not_judged():
    # 1.0 vol point and 25 bp, both inclusive and two-sided; NaN dates are left out of the count.
    shares = cv.within_thresholds(overlap([0.2, -1.0, 1.01, 5.0, math.nan], [3.0, -25.0, 25.01, 40.0, 1.0]))
    assert shares == {"iv30_pts": 1.0, "iv30_dates": 4, "iv30_share_within": 0.5,
                      "spot_bp": 25.0, "spot_dates": 5, "spot_share_within": 0.6}
    # No verdict anywhere: a share of 0 is reported like any other.
    assert cv.within_thresholds(overlap([9.0], [99.0]))["iv30_share_within"] == 0.0


def test_the_shares_and_medians_are_reported_per_year():
    days = [D(2020, 3, 2), D(2020, 3, 4), D(2021, 3, 1), D(2021, 3, 3), D(2021, 3, 5)]
    table = cv.by_year(overlap([0.1, 3.0, 0.1, 0.2, 0.3], [30.0, 5.0, 1.0, 2.0, -40.0], days,
                               spot_optionsdx=[1.0, 2.0, -1.0, -3.0, -2.0]))
    assert table == {"year": [2020, 2021], "dates": [2, 3], "iv30_share_within": [0.5, 1.0],
                     "spot_dolthub_share_within": [0.5, 2 / 3],
                     "spot_dolthub_vs_close_median_bp": [17.5, 1.0],
                     "spot_optionsdx_vs_close_median_bp": [1.5, -2.0]}


def test_rates_are_taken_as_of_the_last_published_day():
    rates = pd.DataFrame({"date": [D(2022, 3, 10), D(2022, 3, 11)], "r_cc": [0.003, 0.004]})
    assert cv.rate_on(rates, D(2022, 3, 13)) == 0.004
    assert math.isnan(cv.rate_on(rates, D(2022, 3, 9)))
