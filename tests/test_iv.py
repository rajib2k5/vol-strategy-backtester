"""The IV solver (ADR-0008 §7): bounds first, Newton, then bisection. ADR-0008 tests 3 and 4.

The M2 review's cases (code claim 2) are here too: a price far below any absolute tolerance must
come back with its true sigma or a fail code, never with the clipped start guess, and an ITM price
one float step above its lower bound cannot be resolved at all.
"""

import numpy as np
import pytest

from volbt.pricing import black76, iv


def test_round_trip_of_adr_0008_test_3():
    out = iv.implied_vol(9.148603, 400, 400, 30 / 365, 0.0, True)
    assert float(out["iv"]) == pytest.approx(0.200000, abs=1e-6)
    assert int(out["fail"]) == iv.FAIL_NONE and int(out["solver"]) == iv.SOLVER_NEWTON
    # Converged means the price is repriced to 1e-10 of itself.
    assert abs(float(black76.price(400, 400, 30 / 365, 0.0, out["iv"], True)) / 9.148603 - 1) <= iv.PRICE_RTOL


def test_a_call_above_its_upper_bound_is_iv_fail_not_an_exception_nor_5():
    # ADR-0008 test 4: DF F + 0.01.
    rate, tau, forward = 0.05, 30 / 365, 400.0
    upper = np.exp(-rate * tau) * forward
    out = iv.implied_vol(upper + 0.01, forward, 380, tau, rate, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_ABOVE_BOUND
    assert int(out["solver"]) == iv.SOLVER_NONE


def test_a_put_below_its_intrinsic_value_is_iv_fail():
    rate, tau = 0.05, 30 / 365
    lower = np.exp(-rate * tau) * (420 - 400)        # DF max(K - F, 0)
    out = iv.implied_vol(lower - 0.01, 400, 420, tau, rate, False)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_BELOW_BOUND


def test_a_price_exactly_on_a_bound_is_iv_fail():
    # A zero price for an OTM option sits exactly on its lower bound: no sigma gives it.
    out = iv.implied_vol([0.0, 400.0], 400, [420, 380], 30 / 365, 0.0, [True, True])
    assert list(out["fail"]) == [iv.FAIL_BELOW_BOUND, iv.FAIL_ABOVE_BOUND]


def test_a_price_whose_sigma_is_above_5_has_no_root():
    price = float(black76.price(400, 400, 30 / 365, 0.0, 6.0, True))
    out = iv.implied_vol(price, 400, 400, 30 / 365, 0.0, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_NO_ROOT


def test_a_price_whose_sigma_is_below_the_floor_has_no_root():
    # The no-root pre-check: inside the bounds, but only a sigma below 1e-4 gives it.
    price = float(black76.price(400, 400, 30 / 365, 0.0, 5e-5, True))
    out = iv.implied_vol(price, 400, 400, 30 / 365, 0.0, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_NO_ROOT


def test_a_nan_price_is_a_failure_not_an_exception():
    out = iv.implied_vol(np.nan, 400, 400, 30 / 365, 0.0, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_BELOW_BOUND


def test_bisection_takes_over_when_newton_leaves_the_bracket():
    # A far OTM put at a high vol: the guess is clipped at 0.01, where vega is ~0, so the first
    # Newton step jumps far outside [1e-4, 5].
    price = float(black76.price(400, 200, 30 / 365, 0.0, 1.8, False))
    out = iv.implied_vol(price, 400, 200, 30 / 365, 0.0, False)
    assert int(out["solver"]) == iv.SOLVER_BISECTION
    assert float(out["iv"]) == pytest.approx(1.8, abs=1e-6)


@pytest.mark.parametrize("days", [7, 10, 14])
def test_a_tiny_otm_price_gets_its_true_sigma_not_the_clipped_guess(days):
    # Code claim 2's cases: K = 500, F = 442, sigma 0.12. At 7 and 10 days the prices (6e-14 and
    # 4e-10) are below the old absolute 1e-8 tolerance, which returned the clipped guess 0.01
    # after 0 iterations; at 14 days it returned 0.11973.
    price = float(black76.price(442.0, 500.0, days / 365, 0.05, 0.12, True))
    out = iv.implied_vol(price, 442.0, 500.0, days / 365, 0.05, True)
    assert int(out["fail"]) == iv.FAIL_NONE
    assert float(out["iv"]) == pytest.approx(0.12, abs=1e-6)
    assert int(out["iterations"]) > 0


def test_an_itm_price_one_float_step_above_its_lower_bound_is_unresolved():
    # The true root is 0.0233 (mpmath, code claim 2), but the time value is one ulp of a $20
    # price: float64 cannot tell it from 0, and the old solver returned 0.0319.
    rate, tau, forward = 0.05, 30 / 365, 400.0
    lower, _ = black76.price_bounds(forward, 380.0, tau, rate, True)
    out = iv.implied_vol(np.nextafter(float(lower), 1e9), forward, 380.0, tau, rate, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_UNRESOLVED


def test_an_itm_price_is_solved_on_its_otm_side():
    # A deep ITM call with a small time value: solved as the OTM put of the same strike, it comes
    # back to 1e-8; as C - DF (F - K) it would have lost most of its digits.
    rate, tau, forward = 0.05, 30 / 365, 400.0
    price = float(black76.price(forward, 300.0, tau, rate, 0.25, True))
    out = iv.implied_vol(price, forward, 300.0, tau, rate, True)
    assert int(out["fail"]) == iv.FAIL_NONE and float(out["iv"]) == pytest.approx(0.25, abs=1e-8)


def test_a_price_float_cannot_resolve_is_unresolved_not_a_number():
    # 5e-324 is the smallest float: Black-76 is 0 below some sigma and above it beyond it, so no
    # sigma reprices it (the old solver returned 0.01).
    out = iv.implied_vol(5e-324, 400.0, 420.0, 30 / 365, 0.05, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_UNRESOLVED


def test_a_price_on_a_flat_stretch_is_unresolved_not_converged_far_from_its_root():
    # A 30-year ATM call at sigma 3 is within 1e-14 of its upper bound DF F: the old solver
    # "converged" at 2.43 (and a relative price tolerance alone at 2.37); the root is 3.03.
    price = float(black76.price(400, 400, 30.0, 0.03, 3.0, True))
    out = iv.implied_vol(price, 400.0, 400.0, 30.0, 0.03, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_UNRESOLVED


def test_tau_zero_is_no_root_without_a_warning():
    with np.errstate(all="raise"):
        out = iv.implied_vol(21.0, 400.0, 380.0, 0.0, 0.05, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_NO_ROOT


# ADR-0008 test 3's property test: 5,000 cases over sigma in [0.05, 2], k in [-0.5, 0.3],
# tau in [1/365, 1], solved on the OTM side (puts for k < 0, calls for k >= 0), as the build does.
RNG = np.random.default_rng(8)
N = 5000
SIGMA = RNG.uniform(0.05, 2.0, N)
LOG_K = RNG.uniform(-0.5, 0.3, N)
TAU = RNG.uniform(1 / 365, 1.0, N)
RATE = RNG.uniform(0.0, 0.06, N)
FORWARD = 400.0
STRIKE = FORWARD * np.exp(LOG_K)
IS_CALL = LOG_K >= 0
PRICE = black76.price(FORWARD, STRIKE, TAU, RATE, SIGMA, IS_CALL)


def test_property_every_price_inside_the_bounds_converges_to_its_sigma():
    out = iv.implied_vol(PRICE, FORWARD, STRIKE, TAU, RATE, IS_CALL)
    lower, upper = black76.price_bounds(FORWARD, STRIKE, TAU, RATE, IS_CALL)
    inside = (PRICE > lower) & (PRICE < upper)
    # Every case whose price is above float's smallest normal number is solved, and solved to
    # its sigma: 1e-8 relative, whatever the size of the price (no absolute price tolerance).
    representable = inside & (PRICE > 1e-300)
    assert representable.sum() > 0.98 * N
    assert np.all(out["fail"][representable] == iv.FAIL_NONE)
    assert np.max(np.abs(out["iv"][representable] / SIGMA[representable] - 1)) < 1e-8
    # Some are tiny: the old absolute tolerance passed every one of these at the clipped guess.
    assert (representable & (PRICE < 1e-8)).sum() >= 10
    # Both solvers take part; the ones outside the bounds are the underflowed prices only.
    assert {iv.SOLVER_NEWTON, iv.SOLVER_BISECTION} <= set(np.unique(out["solver"][inside]).tolist())
    assert np.all(PRICE[~inside] < 1e-300)


def test_property_a_newton_answer_reprices_to_1e_10_of_its_price():
    # The documented stopping rule, with a literal bound (an assertion on iv.PRICE_RTOL would move
    # with the constant it checks): every Newton answer reprices to 1e-10 of the price.
    out = iv.implied_vol(PRICE, FORWARD, STRIKE, TAU, RATE, IS_CALL)
    newton = out["solver"] == iv.SOLVER_NEWTON
    repriced = black76.price(FORWARD, STRIKE[newton], TAU[newton], RATE[newton], out["iv"][newton], IS_CALL[newton])
    assert newton.sum() > 1000
    assert np.max(np.abs(repriced / PRICE[newton] - 1)) <= 1e-10


def test_property_newton_stops_within_50_iterations():
    out = iv.implied_vol(PRICE, FORWARD, STRIKE, TAU, RATE, IS_CALL)
    newton = out["solver"] == iv.SOLVER_NEWTON
    assert out["iterations"][newton].max() <= iv.NEWTON_MAX_ITER


def test_property_itm_prices_on_their_otm_side():
    # The same cases, priced as the ITM option of each strike: the same sigma comes back, or the
    # time value is too small for float64 and the answer is "unresolved", never a wrong number.
    itm = ~IS_CALL
    price = black76.price(FORWARD, STRIKE, TAU, RATE, SIGMA, itm)
    out = iv.implied_vol(price, FORWARD, STRIKE, TAU, RATE, itm)
    solved = out["fail"] == iv.FAIL_NONE
    assert solved.sum() > 0.9 * N
    assert np.max(np.abs(out["iv"][solved] / SIGMA[solved] - 1)) < 1e-6
    assert set(np.unique(out["fail"][~solved]).tolist()) <= {iv.FAIL_UNRESOLVED, iv.FAIL_BELOW_BOUND}


def test_a_price_pinned_only_to_5e_6_of_sigma_is_unresolved():
    # A 30-year ATM call at sigma 2.5: float64's rounding of the price, over vega, is 4.9e-6 of
    # sigma, so the price cannot pin sigma to the 1e-6 the solver promises (mutant R23 loosened the
    # check to 1e-2 and survived: the existing flat-stretch case is beyond 1e-2 too).
    price = float(black76.price(400.0, 400.0, 30.0, 0.03, 2.5, True))
    ratio = float(iv.price_rounding(400.0, 400.0, 30.0, 0.03, 2.5, True) / (2.5 * black76.vega(400.0, 400.0, 30.0, 0.03, 2.5)))
    assert 1e-6 < ratio < 1e-2
    out = iv.implied_vol(price, 400.0, 400.0, 30.0, 0.03, True)
    assert np.isnan(out["iv"]) and int(out["fail"]) == iv.FAIL_UNRESOLVED


def test_property_near_the_upper_bound_sigma_is_within_1e_6_and_mostly_1e_10():
    # OTM calls up to 30 years and sigma 2.4, many close to their upper bound DF F, where a price
    # matched to 1e-10 of itself can sit far from the root. Every solved sigma is within the pinned
    # check's 1e-6 of the truth; where float64 pins it to 1e-10, it is there (mutant R24, a Newton
    # step tolerance of 1e-4, returned sigmas 1e-4 off and survived the old suite).
    rng = np.random.default_rng(3)
    n = 20000
    sigma, tau = rng.uniform(0.5, 2.4, n), rng.uniform(1.0, 30.0, n)
    strike = 400.0 * np.exp(rng.uniform(0.0, 0.5, n))
    price = black76.price(400.0, strike, tau, 0.03, sigma, True)
    out = iv.implied_vol(price, 400.0, strike, tau, 0.03, True)
    solved = out["fail"] == iv.FAIL_NONE
    error = np.abs(out["iv"][solved] / sigma[solved] - 1)
    assert solved.sum() > 0.99 * n and error.max() < 1e-6
    pinned_1e10 = (iv.price_rounding(400.0, strike, tau, 0.03, sigma, True)
                   <= 1e-10 * sigma * black76.vega(400.0, strike, tau, 0.03, sigma))[solved]
    assert pinned_1e10.sum() > 0.9 * solved.sum() and error[pinned_1e10].max() < 2e-10


def test_an_itm_price_whose_sigma_float_pins_is_solved_not_unresolved():
    # The review's case (code claim 4): time value 4.17e-10 of the price, below the old fixed cut of
    # 1e-9, so "unresolved"; yet float64 pins its sigma to well under 1e-6.
    forward, strike, tau, rate, sigma = 442.0, 272.5216, 118.01 / 365, 0.0021, 0.15307
    price = float(black76.price(forward, strike, tau, rate, sigma, True))
    lower, _ = black76.price_bounds(forward, strike, tau, rate, True)
    assert (price - float(lower)) / price < 1e-9
    out = iv.implied_vol(price, forward, strike, tau, rate, True)
    assert int(out["fail"]) == iv.FAIL_NONE and abs(float(out["iv"]) / sigma - 1) < 1e-6


# ITM prices whose time value carries more rounding than an estimate from the OTM side's terms
# admits (found on the review's random ITM sweep, round 2): counted from the OTM terms or from the
# bound alone (round-2 drafts, mutants E13a and E13e), each was "solved" up to 1.5e-6 off.
ITM_ROUNDING_CASES = [  # strike, tau, rate, sigma, is_call (F = 442)
    (454.8667268341328, 0.14732552000879554, 0.030291808612668197, 0.012839142961170679, False),
    (459.2542857580274, 0.1163763488686183, 0.05065801865032897, 0.019255331790226544, False),
    (426.14966751047245, 0.11632518927146261, 0.05966225938191227, 0.018394466914824367, True),
    (439.58957805577796, 0.0030648292715677876, 0.025331149228620432, 0.01787864558319331, True),
]


@pytest.mark.parametrize("strike, tau, rate, sigma, is_call", ITM_ROUNDING_CASES)
def test_an_itm_answer_is_within_1e_6_of_sigma_or_unresolved(strike, tau, rate, sigma, is_call):
    price = float(black76.price(442.0, strike, tau, rate, sigma, is_call))
    assert float(black76.price_bounds(442.0, strike, tau, rate, is_call)[0]) > 0          # in the money
    out = iv.implied_vol(price, 442.0, strike, tau, rate, is_call)
    assert int(out["fail"]) == iv.FAIL_UNRESOLVED or abs(float(out["iv"]) / sigma - 1) < 1e-6


def test_property_every_solved_itm_price_is_within_1e_6_of_sigma():
    # 200,000 random ITM prices (sigma 0.01-4, tau 1 day to 3 years, r -1% to 7%): the pinned check
    # with the time value's inherited rounding keeps every answer within 1e-6 (measured max 4.6e-8).
    rng = np.random.default_rng(31)
    n = 200000
    k = rng.uniform(-1.0, 0.6, n)
    tau, sigma = np.exp(rng.uniform(np.log(1 / 365), np.log(3.0), n)), np.exp(rng.uniform(np.log(0.01), np.log(4.0), n))
    rate, strike, call = rng.uniform(-0.01, 0.07, n), 442.0 * np.exp(k), k < 0
    out = iv.implied_vol(black76.price(442.0, strike, tau, rate, sigma, call), 442.0, strike, tau, rate, call)
    solved = out["fail"] == iv.FAIL_NONE
    assert solved.sum() > 0.45 * n
    assert np.max(np.abs(out["iv"][solved] / sigma[solved] - 1)) < 1e-6


def test_scalar_and_array_inputs_give_the_same_answer():
    many = iv.implied_vol(PRICE[:5], FORWARD, STRIKE[:5], TAU[:5], RATE[:5], IS_CALL[:5])["iv"]
    one = [float(iv.implied_vol(PRICE[i], FORWARD, STRIKE[i], TAU[i], RATE[i], IS_CALL[i])["iv"]) for i in range(5)]
    assert np.allclose(many, one, rtol=0, atol=0, equal_nan=True)


def test_the_fail_names_cover_every_code():
    assert len(iv.FAIL_NAMES) == iv.FAIL_AMERICAN_BAD_INPUT + 1 == 12 and iv.FAIL_NAMES[0] == ""
    assert iv.FAIL_NAMES[iv.FAIL_AMERICAN_UNIDENTIFIED] == "american_unidentified"
    assert len(set(iv.FAIL_NAMES)) == len(iv.FAIL_NAMES)
