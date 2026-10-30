"""The CRR lattice (ADR-0003, ADR-0008 §3a and §8): hand values, convergence, the premium's sign."""

import numpy as np
import pytest

from volbt.pricing import black76, lattice


def test_the_american_mark_of_adr_0008_test_9():
    # Put, S = K = 450, r = 5%, sigma 0.15, 30 days, no dividend: N = 500 gives 6.9574, not the
    # Black-76 price 6.8162 (on F = S e^(r tau)).
    american = lattice.crr(450, 450, 30 / 365, 0.05, 0.15, False, steps=500)["price"]
    assert float(american[0]) == pytest.approx(6.9574, abs=5e-5)
    forward = 450 * np.exp(0.05 * 30 / 365)
    assert float(black76.price(forward, 450, 30 / 365, 0.05, 0.15, False)) == pytest.approx(6.8162, abs=5e-5)


@pytest.mark.parametrize("is_call", [True, False])
def test_with_no_rate_and_no_dividend_the_lattice_converges_to_black_scholes(is_call):
    # r = 0 and no dividend: nothing is gained by exercising early, so American = European, and both
    # converge to Black-76 (= Black-Scholes, F = S) as the steps grow. CRR's error shrinks like 1/N.
    strikes = np.array([380.0, 400.0, 425.0])
    exact = black76.price(400, strikes, 0.25, 0.0, 0.25, is_call)
    errors = []
    for steps in (100, 400, 1600):
        american = lattice.crr(400, strikes, 0.25, 0.0, 0.25, is_call, steps=steps)["price"]
        european = lattice.crr_european(400, strikes, 0.25, 0.0, 0.25, is_call, steps=steps)
        assert np.allclose(american, european, atol=1e-10)
        errors.append(np.max(np.abs(american - exact)))
    assert errors[0] > errors[1] > errors[2]
    assert errors[2] < 0.005


def test_with_a_dividend_the_european_lattice_converges_to_black_76_on_the_carry_forward():
    # Escrowed dividend: the European price is Black-76 on F = (S - PV(D)) e^(r tau).
    spot, rate, tau, dividend, when = 440.0, 0.05, 0.5, 1.7, 0.2
    forward = (spot - dividend * np.exp(-rate * when)) * np.exp(rate * tau)
    strikes = np.array([400.0, 440.0, 480.0])
    for is_call in (True, False):
        exact = black76.price(forward, strikes, tau, rate, 0.2, is_call)
        approx = lattice.crr_european(spot, strikes, tau, rate, 0.2, is_call, [[when]], [[dividend]], steps=2000)
        assert np.max(np.abs(approx - exact)) < 0.005


def test_the_closed_european_sum_equals_the_backward_walk():
    strikes = np.array([400.0, 440.0, 480.0, 520.0])
    for is_call in (True, False):
        walked = lattice.crr(440, strikes, 0.3, 0.04, 0.22, is_call, [[0.1, 0.35]], [[1.6, 1.7]],
                             steps=300, american=False)["price"]
        summed = lattice.crr_european(440, strikes, 0.3, 0.04, 0.22, is_call, [[0.1, 0.35]], [[1.6, 1.7]], steps=300)
        assert np.allclose(walked, summed, rtol=0, atol=1e-10)


def test_the_premium_is_never_negative_and_grows_with_the_put_s_moneyness():
    strikes = np.linspace(380, 520, 15)
    eep = lattice.early_exercise_premium(440, strikes, 60 / 365, 0.05, 0.2, False)
    assert np.all(eep >= 0)
    assert np.all(np.diff(eep) >= -1e-12)           # deeper in the money, more to gain from exercising


def test_a_call_has_a_premium_only_because_of_a_dividend():
    no_div = lattice.early_exercise_premium(460, 400, 30 / 365, 0.05, 0.2, True)
    with_div = lattice.early_exercise_premium(460, 400, 30 / 365, 0.05, 0.2, True, [[10 / 365]], [[3.0]])
    assert float(no_div[0]) == pytest.approx(0.0, abs=1e-10)
    assert float(with_div[0]) > 0.5


def test_a_dividend_after_expiry_or_padding_is_ignored():
    plain = lattice.crr(440, 450, 30 / 365, 0.05, 0.2, False)["price"]
    padded = lattice.crr(440, 450, 30 / 365, 0.05, 0.2, False, [[0.0, 45 / 365]], [[0.0, 1.7]])["price"]
    assert np.allclose(plain, padded, rtol=0, atol=0)


def test_a_dividend_on_the_expiry_date_lowers_the_payoff_stock():
    # Ex on the expiry date: in S0's present value, not in the payoff (the close is ex-dividend).
    on_expiry = lattice.crr_european(440, 440, 30 / 365, 0.0, 0.2, True, [[30 / 365]], [[2.0]], steps=1000)
    forward = 440 - 2.0
    assert float(on_expiry[0]) == pytest.approx(float(black76.price(forward, 440, 30 / 365, 0.0, 0.2, True)), abs=0.01)


def test_the_continuation_value_is_the_unexercised_root():
    # Deep ITM put at 5%: exercising now beats waiting, so the price is the intrinsic value and the
    # continuation value is below it.
    out = lattice.crr(380, 450, 30 / 365, 0.05, 0.2, False, steps=500)
    assert float(out["price"][0]) == pytest.approx(70.0)
    assert float(out["continuation"][0]) < 70.0


# --- the guard on p (M2 review, code claim 3) ----------------------------------------------------

def test_the_up_probability_the_walk_uses_stays_inside_0_1_at_any_sigma():
    # sigma below |r| sqrt(dt) makes p leave (0, 1). The lattice prices at the floor instead; the
    # p tested is the one crr itself walked with (round 2: the old test checked a copy of the formula).
    for rate in (0.10, 0.05, -0.01, -0.05, 0.0):
        for sigma in (1e-6, 1e-4, 0.01, 0.2):
            for steps in (lattice.DEAM_TREE_STEPS, lattice.EXERCISE_TREE_STEPS):
                p = float(lattice.crr(440.0, 430.0, 30 / 365, rate, sigma, False, steps=steps)["up_probability"][0])
                assert 0.2 < p < 0.8, (rate, sigma, steps, p)
                if sigma <= 1e-4 and rate != 0:                    # at the floor: about 0.75, or 0.25 at r < 0
                    assert p == pytest.approx(0.75 if rate > 0 else 0.25, abs=0.002), (rate, sigma, steps, p)
    assert float(lattice.sigma_floor(0.05, 30 / 365)) == pytest.approx(2 * 0.05 * np.sqrt(30 / 365 / 200))


def test_a_sigma_below_the_floor_gives_a_finite_price_not_nonsense():
    # The review's case: sigma 1e-4, K = 430 call, 30 days, 5%: the old walk gave 10.000 (and an
    # overflowed, meaningless European sum, a NaN premium). At the floor the stock is all but
    # certain to grow at r, so the call is worth S - K e^(-r tau) = 11.7635.
    spot, strike, tau, rate = 440.0, 430.0, 30 / 365, 0.05
    deterministic = spot - strike * np.exp(-rate * tau)
    american = float(lattice.crr(spot, strike, tau, rate, 1e-4, True)["price"][0])
    european = float(lattice.crr_european(spot, strike, tau, rate, 1e-4, True)[0])
    premium = lattice.early_exercise_premium(spot, [strike, 450.0], tau, rate, 1e-4, [True, False])
    assert american == pytest.approx(deterministic, abs=1e-3) and european == pytest.approx(deterministic, abs=1e-3)
    assert np.all(np.isfinite(premium)) and np.all(premium >= 0)


def test_a_dividend_exactly_at_a_node_time_has_gone_ex_at_that_node():
    # The escrow rule: at a node at time t the stock carries the dividends with t_D > t, so a
    # dividend exactly at a node's time is no longer in that node's stock (code mutant M5 counted
    # it as still pending). dt = 0.5 / 128 is exact in binary, and t_D = 64 dt.
    spot, strike, tau, rate, sigma, dividend, steps = 100.0, 80.0, 0.5, 0.05, 0.2, 5.0, 128
    dt = tau / steps
    on_node = 64 * dt
    price = {when: float(lattice.crr(spot, strike, tau, rate, sigma, True, [[when]], [[dividend]], steps)["price"][0])
             for when in (on_node - 1e-9, on_node, on_node + 1e-9)}
    # An ITM call worth exercising for a 5.00 dividend: cum at node 64 (t_D just after it) it can
    # be exercised there for the dividend; ex at node 64 (t_D at or just before it) only one step
    # earlier, which costs it 1.6 cents.
    assert price[on_node + 1e-9] - price[on_node - 1e-9] > 0.01
    assert price[on_node] == pytest.approx(price[on_node - 1e-9], abs=1e-6)
