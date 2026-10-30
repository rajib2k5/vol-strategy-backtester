"""The parity forward, its fallback, the day count, the dividend schedule and de-Americanisation.

ADR-0008 tests 2, 5, 6, 7 and 8. Test 8 builds a synthetic American chain on a truth lattice of
N = 2,000 steps (an N = 200 truth fails the test's own bound, ADR-0008 round 2) and runs the
procedure under test, which keeps N = 200. The M2 review's clean long-dated chains (design claim
3) are here too: §3a's first rule (sigma_0 from the raw mid) settled 101 bp low on them, with 120
of 130 quotes PARITY_OUTLIER; the American-IV rule that replaced it must not.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from volbt.pricing import chain, dividends, forward, iv, lattice


def test_parity_forward_of_adr_0008_test_2():
    df = forward.discount_factor(0.0521594, 29 / 365)
    assert float(df) == pytest.approx(0.995864, abs=5e-7)
    assert float(forward.strike_forwards(443, 5.560, 6.315, df)) == pytest.approx(442.2419, abs=5e-5)


def test_the_forward_is_the_median_of_the_5_strikes_nearest_k_star():
    strikes = np.array([430, 435, 440, 445, 450, 455, 460], dtype=float)
    # F_K = K + (C - P) with DF = 1. K* is 445 (C = P there); the 5 nearest are 435..455. 460's
    # F_K is wild, and the median of the five ignores it anyway.
    # At 445 C = P, so its F_K is 445 itself, an outlier the median also ignores.
    fk = np.array([440.9, 441.2, 441.0, 445.0, 441.4, 441.1, 470.0])
    call = np.full(7, 10.0)
    put = call - (fk - strikes)
    out = forward.parity_forward(strikes, call, put, 1.0)
    assert out["k_star"] == 445
    assert sorted(out["used"].tolist()) == [1, 2, 3, 4, 5]
    assert out["forward"] == pytest.approx(441.2)     # median of 441.2, 441.0, 445.0, 441.4, 441.1
    # |F_K - F| = 0, 0.2, 3.8, 0.2, 0.1: the median deviation is 0.2.
    assert out["mad_rel"] == pytest.approx(0.2 / 441.2)


def test_a_tie_for_the_nearest_strikes_goes_to_the_lower_strike():
    assert forward.nearest(np.array([1.0, 2.0, 3.0, 4.0]), 2.5, 1).tolist() == [1]


def test_fewer_than_3_pairs_give_no_parity_forward():
    assert forward.parity_forward([440.0, 445.0], [5.0, 3.0], [4.0, 6.0], 1.0) is None


def test_fallback_forward_of_adr_0008_test_7():
    assert forward.carry_forward(450, 0.05, 30 / 365, [10 / 365], [1.80]) == pytest.approx(450.048, abs=5e-4)


def test_day_count_across_the_dst_change_of_adr_0008_test_5():
    quote, expiry = date(2024, 3, 8), date(2024, 3, 15)
    assert forward.tau_years(quote, expiry) == 7 / 365
    # The vendor-style difference of two 16:00 New York stamps is shorter: DST began on 03-10.
    new_york = ZoneInfo("America/New_York")
    stamps = [datetime(d.year, d.month, d.day, 16, tzinfo=new_york).timestamp() for d in (quote, expiry)]
    assert (stamps[1] - stamps[0]) / 86400 == pytest.approx(6.9583, abs=5e-5)


def test_on_the_expiry_date_tau_is_0_and_no_iv_is_solved():
    # ADR-0008 test 6: tau = 0, value = intrinsic, and the solver is not called.
    assert forward.tau_years(date(2024, 3, 15), date(2024, 3, 15)) == 0
    out = chain.price_chain(450.0, 0.05, [0.0], np.zeros((1, 0)), np.zeros((1, 0)), [0, 0], [440.0, 460.0],
                            [True, False], [10.02, 10.01], [True, True])
    assert out["expiries"]["method"][0] == chain.METHOD_EXPIRY_DAY
    assert out["expiries"]["forward"][0] == 450.0
    assert np.all(np.isnan(out["quotes"]["iv"])) and np.all(out["quotes"]["iterations"] == -1)


def test_the_slope_of_f_k_against_k():
    assert forward.slope_per_strike([436.0, 437.0, 438.0], [442.376, 442.340, 442.304]) == pytest.approx(-0.036)
    assert np.isnan(forward.slope_per_strike([436.0, 437.0], [442.0, 441.9]))


# --- the dividend schedule --------------------------------------------------------------------

def test_third_fridays():
    assert dividends.third_friday(2023, 6) == date(2023, 6, 16)
    assert dividends.third_friday(2012, 9) == date(2012, 9, 21)     # Sep 1 2012 was a Saturday


def test_a_holiday_friday_moves_to_the_session_before():
    # Juneteenth 2026 is the third Friday of June: SPY went ex on Thursday 2026-06-18.
    sessions = [date(2026, 6, 17), date(2026, 6, 18), date(2026, 6, 22)]
    assert dividends.projected_ex_dates(date(2026, 6, 1), date(2026, 6, 30), sessions) == [date(2026, 6, 18)]


def test_the_schedule_uses_the_last_paid_amount_and_only_later_ex_dates():
    paid = [date(2023, 3, 17), date(2023, 6, 16)]
    amounts = [1.506, 1.638]
    sessions = [date(2023, 6, 15), date(2023, 6, 16), date(2023, 9, 15)]
    # On 06-15 the June dividend is not paid yet: its date is projected, at March's amount.
    times, amts = dividends.schedule(paid, amounts, date(2023, 6, 15), date(2023, 7, 14), sessions)
    assert amts == [1.506]
    # The ex-date is tomorrow, so the drop comes just after today's close: before any lattice step.
    assert times == [dividends.DROP_AFTER_CLOSE] and 0 < times[0] < 1e-6
    # On 06-16 itself the close is already ex-dividend: nothing until September.
    assert dividends.schedule(paid, amounts, date(2023, 6, 16), date(2023, 7, 14), sessions) == ([], [])
    assert dividends.schedule(paid, amounts, date(2023, 6, 16), date(2023, 9, 15), sessions)[1] == [1.638]


def test_the_drop_comes_after_the_close_of_the_day_before_the_ex_date():
    assert dividends.drop_time(date(2023, 6, 1), date(2023, 6, 16)) == pytest.approx(14 / 365)


def test_an_otm_call_on_the_eve_of_an_ex_date_has_no_premium_with_the_drop_after_the_close():
    # The eve of an ex-date that is also the expiry: S = 396 cum-dividend, D = 1.506, a 400 call.
    # It cannot be exercised for the dividend (S < K at the only close before the drop), so its
    # premium is ~0. Timing the drop at the ex-date instead lets the lattice exercise a diffused
    # cum-dividend stock and prices a premium of tens of cents into it.
    spot, tau, rate = 396.0, 1 / 365, 0.045
    after_close = lattice.early_exercise_premium(spot, 400, tau, rate, 0.25, True,
                                                 [[dividends.drop_time(date(2023, 3, 16), date(2023, 3, 17))]], [[1.506]])
    at_ex_date = lattice.early_exercise_premium(spot, 400, tau, rate, 0.25, True, [[1 / 365]], [[1.506]])
    assert float(after_close[0]) < 1e-6 and float(at_ex_date[0]) > 0.1


def test_no_dividend_paid_yet_means_no_schedule():
    assert dividends.schedule([date(2023, 6, 16)], [1.6], date(2023, 1, 3), date(2023, 12, 29), []) == ([], [])


# --- ADR-0008 test 8: de-Americanisation removes the forward bias ------------------------------

SPOT, TAU, DIVIDEND, SIGMA = 442.61, 29 / 365, 1.638367, 0.12
STRIKES = np.arange(418.0, 468.0)                   # S +- 25, every dollar
TRUTH_STEPS = 2000


def american_chain(rate):
    """(strikes, is_call, American prices on the N = 2,000 truth lattice, true forward)."""
    strikes = np.concatenate([STRIKES, STRIKES])
    calls = np.r_[np.ones(STRIKES.size, bool), np.zeros(STRIKES.size, bool)]
    prices = lattice.crr(SPOT, strikes, TAU, rate, SIGMA, calls, [[1 / 365]], [[DIVIDEND]], steps=TRUTH_STEPS)["price"]
    true_forward = (SPOT - DIVIDEND * np.exp(-rate / 365)) * np.exp(rate * TAU)
    return strikes, calls, prices, true_forward


def run_procedure(rate, deamericanise=True):
    strikes, calls, prices, true_forward = american_chain(rate)
    out = chain.price_chain(SPOT, rate, [TAU], [[1 / 365]], [[DIVIDEND]], np.zeros(strikes.size, int), strikes,
                            calls, prices, np.ones(strikes.size, bool), deamericanise=deamericanise)
    q = out["quotes"]
    forward_bp = (out["expiries"]["forward"][0] / true_forward - 1) * 1e4
    max_iv_error_pts = np.max(np.abs(q["iv"][q["is_otm"]] - SIGMA)) * 100
    return forward_bp, max_iv_error_pts, out, true_forward


def test_de_americanisation_removes_the_forward_bias_at_5_22_percent():
    forward_bp, iv_pts, out, true_forward = run_procedure(0.0521594)
    assert true_forward == pytest.approx(442.8031, abs=5e-5)
    assert abs(forward_bp) < 0.039                        # measured +0.0308 bp x 1.25 (the ADR's gate: 0.1 bp)
    assert iv_pts < 0.01                                  # ADR: within 0.01 vol points (measured 0.0060)
    assert out["expiries"]["n_deamericanised"][0] == 20   # 10 strikes x call and put
    assert out["expiries"]["forward_raw"][0] < true_forward


def test_the_mutant_without_de_americanisation_fails_the_same_bounds():
    # ADR-0008 test 8's mutant check: the same test must fail with §3a disabled. Measured in the
    # ADR: F = 442.6122 (-4.3 bp), maximum IV error 0.19 vol points.
    forward_bp, iv_pts, _, _ = run_procedure(0.0521594, deamericanise=False)
    assert forward_bp < -4.0 and iv_pts > 0.15


def test_at_a_quarter_percent_both_versions_pass_and_differ_by_under_0_1_bp():
    # F bounds: the measured value x 1.25, or the ADR's 0.1 bp where that is tighter (fix4/f3/other_bounds.out):
    # with +0.00606 bp, without -0.08682, apart 0.09288.
    with_bp, with_iv, _, _ = run_procedure(0.0025)
    without_bp, without_iv, _, _ = run_procedure(0.0025, deamericanise=False)
    assert abs(with_bp) < 0.0076 and abs(without_bp) < 0.1
    assert with_iv < 0.01 and without_iv < 0.01
    assert abs(with_bp - without_bp) < 0.1


def test_at_60_days_with_a_dividend_inside_the_bias_is_removed_too():
    # ADR-0008 round 2's harder case: r = 5%, sigma 0.20, 60 days, a dividend at 30 days. The raw
    # forward is 7.2 bp low (the ADR measured -7.4 bp on its strikes); after §3a it is within
    # 0.1 bp (measured +0.042). The maximum OTM IV error is 0.0109 vol points here, a little above
    # the 0.010 the ADR's round 2 measured at 60 days on its own strikes, so the bound is 0.015.
    # It is the procedure's lattice's own error: with the procedure on N = 200, 500, 1,000 and
    # 2,000 steps it is 0.0109, 0.0047, 0.0032 and 0.0029 (measured 2026-10-29, fix3/e9_sixty.out;
    # M2 round 2, design claim 7: the 0.0043 once quoted here was the old sigma_0 method's).
    spot, rate, tau, sigma, dividend = 442.61, 0.05, 60 / 365, 0.20, 1.638367
    strikes = np.arange(410.0, 476.0)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    prices = lattice.crr(spot, both, tau, rate, sigma, calls, [[30 / 365]], [[dividend]], steps=TRUTH_STEPS)["price"]
    truth = (spot - dividend * np.exp(-rate * 30 / 365)) * np.exp(rate * tau)
    errors = {}
    for deamericanise in (True, False):
        out = chain.price_chain(spot, rate, [tau], [[30 / 365]], [[dividend]], np.zeros(both.size, int), both, calls,
                                prices, np.ones(both.size, bool), deamericanise=deamericanise)
        q = out["quotes"]
        errors[deamericanise] = ((out["expiries"]["forward"][0] / truth - 1) * 1e4,
                                 np.max(np.abs(q["iv"][q["is_otm"]] - sigma)) * 100)
    assert abs(errors[True][0]) < 0.053 and errors[True][1] < 0.015   # F: measured +0.0421 bp x 1.25
    assert errors[False][0] < -7.0 and errors[False][1] > 0.2


# The clean long-dated chains (M2 review, design claim 3; round 2, code claim 2 and decision E3; round 3,
# decisions F3 and F4). Every $2 strike from 332 to 574, the truth on an N = 2,000 lattice, the
# procedure on the build's N = 200: (dividends, rate, days, sigma, F bound in bp, OTM IV bound in vol
# points). Each bound is the value measured on 2026-10-29 (scratchpad fix4/f3/measure_listed.out),
# shown after it, times 1.25, rounded up at two significant digits. The bounds hold on THESE chains
# only, not on a region of (r, tau, sigma): the low-sigma, 8% and 10% cases keep a few bp of the
# N = 200 lattice's own error (truth on the procedure's lattice: 0.000 bp, test below), and none is
# flagged. The last eight were added in round 3: the reviewer's two (r 8% at 700 days sigma 0.12 had
# 2 IV_FAIL and 4 PARITY_OUTLIER before F3; r 8% at 365 days sigma 0.08) and six of the 29 chains
# of a 160-chain grid (r 0.25-10%, 365-700 days, sigma 0.08-0.20, one or quarterly dividends) that the
# round-2 code failed above half a tick; after F3 one of the 160 still fails (test below).
CLEAN_CHAINS = [
    ("one", 0.0521594, 365, 0.12, 0.18, 0.016),       # -0.1405 bp, 0.0126 points
    ("one", 0.0521594, 365, 0.15, 0.036, 0.016),      # -0.0283, 0.0124
    ("one", 0.0521594, 365, 0.20, 0.0037, 0.018),     # +0.0029, 0.0140
    ("one", 0.0521594, 540, 0.12, 0.49, 0.018),       # -0.3867, 0.0139
    ("one", 0.0521594, 540, 0.15, 0.29, 0.017),       # -0.2245, 0.0136
    ("one", 0.0521594, 540, 0.20, 0.12, 0.019),       # +0.0883, 0.0146
    ("one", 0.0521594, 700, 0.12, 0.4, 0.017),        # -0.3140, 0.0135
    ("one", 0.0521594, 700, 0.15, 0.018, 0.017),      # +0.0140, 0.0133
    ("one", 0.0521594, 700, 0.20, 0.3, 0.023),        # -0.2390, 0.0177
    ("one", 0.0521594, 700, 0.08, 4.8, 0.061),        # -3.7621, 0.0482: was -74 bp, 198 of 244 flagged
    ("quarterly", 0.0521594, 700, 0.08, 1.8, 0.072),  # 8 dividends: -1.4235, 0.0572 (was -5.6 bp)
    ("one", 0.0521594, 700, 0.10, 1.1, 0.079),        # -0.8736, 0.0628 (was -4.1 bp, 2 flagged)
    ("quarterly", 0.0521594, 700, 0.10, 0.99, 0.021),  # -0.7872, 0.0162
    ("quarterly", 0.0521594, 540, 0.12, 0.78, 0.014),  # 6 dividends: -0.6240, 0.0110
    ("one", 0.08, 365, 0.12, 0.25, 0.04),             # -0.1928, 0.0315
    ("quarterly", 0.08, 450, 0.12, 0.26, 0.031),      # 5 dividends: -0.2027, 0.0247
    ("quarterly", 0.08, 700, 0.15, 1.1, 0.076),       # 8 dividends: -0.8227, 0.0608
    ("one", 0.10, 365, 0.12, 2.8, 0.057),             # -2.1701, 0.0452 (was -31.8 bp, 6 flagged)
    ("quarterly", 0.10, 450, 0.12, 4.3, 0.075),       # -3.4151, 0.0595
    ("quarterly", 0.10, 700, 0.15, 9.7, 0.12),        # -7.7273, 0.0940 (was -53 bp, 174 flagged)
    ("one", 0.08, 700, 0.12, 7.5, 0.098),             # -5.9395, 0.0782 (round 3: 2 IV_FAIL, 4 flagged before F3)
    ("one", 0.08, 365, 0.08, 2.2, 0.044),             # -1.6903, 0.0348; 10 IV_FAIL, all below half a tick
    ("one", 0.10, 700, 0.12, 9.4, 0.17),              # -7.5148, 0.1345 (8 IV_FAIL, 16 flagged before F3)
    ("one", 0.10, 540, 0.10, 6.1, 0.14),              # -4.8488, 0.1055 (5, 10 before F3)
    ("quarterly", 0.10, 700, 0.10, 9.6, 0.2),         # -7.6027, 0.1556 (8, 16 before F3)
    ("quarterly", 0.08, 700, 0.08, 7.5, 0.14),        # -5.9611, 0.1094 (4, 8 before F3)
    ("one", 0.08, 540, 0.10, 4.9, 0.078),             # -3.8472, 0.0621 (1, 2 before F3)
    ("quarterly", 0.10, 365, 0.08, 2.7, 0.063),       # -2.1445, 0.0501; 12 IV_FAIL below half a tick (1, 2 above before F3)
]


# The smallest mid the store can hold is half a tick: a zero bid with a $0.01 ask (a valid quote, bid
# $0.01 or more, has a mid of at least $0.01). Below it a synthetic chain prices deep-OTM puts at
# $2e-5 to $5e-4, where a 1e-6 bump of sigma moves the price by less than the solve's 1e-8 USD
# tolerance: such a quote is american_unidentified, and so is its deep-ITM partner call. No market
# quote is that small, so the IV_FAIL and IV-error tests below count only mids of $0.005 or more.
MARKET_MID_MIN = 0.005


def clean_chain(dividends_kind, rate, days, sigma, truth_steps=2000):
    """(price_chain's output, the true forward, the number of dividends, the mids)."""
    tau = days / 365
    when = np.arange(1, days, 91) / 365 if dividends_kind == "quarterly" else np.array([1 / 365])
    amounts = np.full(when.size, DIVIDEND)
    strikes = np.arange(332.0, 575.0, 2.0)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    prices = lattice.crr(SPOT, both, tau, rate, sigma, calls, [when], [amounts], steps=truth_steps)["price"]
    truth = (SPOT - (amounts * np.exp(-rate * when)).sum()) * np.exp(rate * tau)
    out = chain.price_chain(SPOT, rate, [tau], [when], [amounts], np.zeros(both.size, int), both, calls, prices,
                            np.ones(both.size, bool))
    return out, truth, when.size, prices


@pytest.mark.parametrize("kind, rate, days, sigma, f_bound_bp, iv_bound_pts", CLEAN_CHAINS,
                         ids=[f"{c[0]}-r{c[1]:.3f}-{c[2]}d-s{c[3]:.2f}" for c in CLEAN_CHAINS])
def test_a_clean_long_dated_american_chain_is_not_a_parity_outlier(kind, rate, days, sigma, f_bound_bp, iv_bound_pts):
    out, truth, n_dividends, mid = clean_chain(kind, rate, days, sigma)
    q = out["quotes"]
    market = mid >= MARKET_MID_MIN
    failed = (q["iv_flags"] & chain.IV_FAIL) != 0
    assert kind == "one" or 4 <= n_dividends <= 8                            # 4 at 365 days, 8 at 700
    assert chain.METHOD_NAMES[out["expiries"]["method"][0]] == "parity_median5_deam"
    assert abs(out["expiries"]["forward"][0] / truth - 1) * 1e4 < f_bound_bp
    assert ((q["iv_flags"] & chain.PARITY_OUTLIER) != 0).sum() == 0
    assert (failed & market).sum() == 0
    assert (q["fail"][failed] == iv.FAIL_AMERICAN_UNIDENTIFIED).all()         # below half a tick only (above)
    assert np.max(np.abs(q["iv"][q["is_otm"] & market] - sigma)) * 100 < iv_bound_pts
    # The raw forward is far off (-83 to -601 bp): the test would fail without de-Americanisation.
    assert out["expiries"]["forward_raw"][0] / truth - 1 < -0.008
    # eep is kept only where it was used: every OTM quote (above half a tick), and the ITM side of the
    # 10 near-K* strikes.
    assert np.isfinite(q["eep"][q["is_otm"] & market]).all()
    assert np.isfinite(q["eep"][~q["is_otm"]]).sum() == 10


@pytest.mark.parametrize("kind, rate, days, sigma", [("one", 0.0521594, 700, 0.08), ("quarterly", 0.0521594, 700, 0.08),
                                                    ("one", 0.0521594, 700, 0.10), ("quarterly", 0.10, 700, 0.15),
                                                    ("quarterly", 0.10, 450, 0.12), ("one", 0.10, 365, 0.12),
                                                    ("one", 0.08, 700, 0.12)])
def test_with_the_truth_on_the_procedure_s_own_lattice_the_hard_chains_are_exact(kind, rate, days, sigma):
    # The few bp left above are the N = 200 lattice's own error, not the procedure's: with the truth
    # on N = 200 the forward is exact (it was -52 bp with 144 flagged at sigma 0.08). The largest
    # error over these 7 chains is 1.549e-05 bp (one dividend, 700 days, sigma 0.10; the others
    # 1.3e-10 to 1.0e-07 bp; fix4/f3/other_bounds.out), so the bound is 2e-5 bp, about 1.25 times it.
    out, truth, _, _ = clean_chain(kind, rate, days, sigma, truth_steps=lattice.DEAM_TREE_STEPS)
    assert abs(out["expiries"]["forward"][0] / truth - 1) * 1e4 < 2e-5
    assert ((out["quotes"]["iv_flags"] & chain.PARITY_OUTLIER) != 0).sum() == 0
    assert out["quotes"]["premium_from_partner"].sum() > 0


def test_the_one_chain_of_the_round_3_grid_that_still_fails_is_pinned_with_its_cause():
    # Round 3 (decision F3): of the 160-chain grid one still fails above half a tick: r 10%, 700
    # days, sigma 0.08, one dividend. The 456 put is flat in sigma (a 1e-6 bump moves A by 3.49e-6,
    # under half the European 8.00e-6). Its partner call has A = E, but the bump moves its $66.10 price
    # by 6.42e-6, below the solve's tolerance 1e-7 x mid = 6.61e-6, so it is unidentified too and
    # cannot price the put's premium (fix4/f3/limit_456.out). The put is IV_FAIL and the pair
    # PARITY_OUTLIER; F is -7.45 bp. Pinned so that a change to it shows; a limit stated in the
    # walkthrough's "Not done", not fixed here (it needs a change to deam.py's identification step).
    out, truth, _, mid = clean_chain("one", 0.10, 700, 0.08)
    q = out["quotes"]
    strikes = np.arange(332.0, 575.0, 2.0)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    failed = (q["iv_flags"] & chain.IV_FAIL) != 0
    flagged = (q["iv_flags"] & chain.PARITY_OUTLIER) != 0
    market = mid >= MARKET_MID_MIN
    assert both[failed & market].tolist() == [456.0] and not calls[failed & market].any()
    assert sorted(zip(both[flagged].tolist(), calls[flagged].tolist())) == [(456.0, False), (456.0, True)]
    assert (q["fail"][failed] == iv.FAIL_AMERICAN_UNIDENTIFIED).all()
    assert (out["expiries"]["forward"][0] / truth - 1) * 1e4 == pytest.approx(-7.454, abs=5e-4)


# --- the dividend amount (M2 review amendment D4) -------------------------------------------------

# A made-up quarterly history with SPY's seasonality: March smallest, December largest, growing
# 10% a year. Two years paid; the third is projected.
SEASONAL = {3: 1.0, 6: 1.2, 9: 1.1, 12: 1.5}
HISTORY = [(dividends.third_friday(year, month), round(SEASONAL[month] * 1.1 ** (year - 2021), 6))
           for year in (2021, 2022) for month in (3, 6, 9, 12)]


def test_the_amount_is_the_same_quarter_a_year_earlier_times_the_trailing_growth():
    days, amounts = [d for d, _ in HISTORY], [a for _, a in HISTORY]
    as_of = date(2023, 1, 10)
    growth = sum(amounts[4:]) / sum(amounts[:4])
    assert growth == pytest.approx(1.1)
    march = dividends.projected_amount(days, amounts, as_of, date(2023, 3, 17))
    assert march == pytest.approx(amounts[4] * growth)            # March 2022 x growth = 1.21, not 1.65
    assert dividends.projected_amount(days, amounts, as_of, date(2023, 12, 15)) == pytest.approx(amounts[7] * growth)
    # More than a year ahead: the latest paid March, grown twice.
    assert dividends.projected_amount(days, amounts, as_of, date(2024, 3, 15)) == pytest.approx(amounts[4] * growth**2)
    # Last paid (the old rule) would say 1.65 for March: 36% too much on this history.
    assert dividends.last_paid(days, amounts, as_of) == pytest.approx(1.65)


def test_the_amount_reads_nothing_after_the_quote_date():
    days, amounts = [d for d, _ in HISTORY], [a for _, a in HISTORY]
    early = dividends.projected_amount(days, amounts, date(2022, 12, 15), date(2023, 3, 17))
    # On 2022-12-15 the December 2022 dividend (ex 12-16) is not paid: 7 known, too few for growth.
    assert early == pytest.approx(amounts[6])
    changed = amounts[:7] + [99.0]
    assert dividends.projected_amount(days, changed, date(2022, 12, 15), date(2023, 3, 17)) == early


def test_the_schedule_projects_the_amount_per_ex_date():
    days, amounts = [d for d, _ in HISTORY], [a for _, a in HISTORY]
    sessions = [date(2023, 1, 10), date(2023, 3, 17), date(2023, 6, 16)]
    _, amts = dividends.schedule(days, amounts, date(2023, 1, 10), date(2023, 6, 30), sessions)
    assert amts == pytest.approx([amounts[4] * 1.1, amounts[5] * 1.1])


def test_past_the_last_session_nyse_holidays_still_move_the_ex_date():
    # Juneteenth 2027 is a Saturday, so NYSE closes Friday 2027-06-18, the third Friday of June:
    # SPY goes ex on Thursday 06-17. Good Friday 2008 (03-21) was a third Friday too.
    sessions = [date(2026, 10, 28)]
    assert dividends.projected_ex_dates(date(2027, 6, 1), date(2027, 6, 30), sessions) == [date(2027, 6, 17)]
    assert dividends.projected_ex_dates(date(2008, 3, 1), date(2008, 3, 31), []) == [date(2008, 3, 20)]
    assert dividends.good_friday(2024) == date(2024, 3, 29) and dividends.good_friday(2027) == date(2027, 3, 26)
    # Before 2022 NYSE traded on Juneteenth: 2021-06-18 (June 19 a Saturday) stays a Friday.
    assert dividends.projected_ex_dates(date(2021, 6, 1), date(2021, 6, 30), []) == [date(2021, 6, 18)]
