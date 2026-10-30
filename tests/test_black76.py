"""Black-76 prices and greeks (ADR-0008 §1) in ADR-0006's units: hand values, parity, finite differences."""

import numpy as np
import pytest

from volbt.pricing import black76

# ADR-0006 test 1 and ADR-0008 test 3: S = F = K = 400, sigma 0.20, 30 days, r = 0.
ATM = dict(spot=400.0, forward=400.0, strike=400.0, tau=30 / 365, rate=0.0, sigma=0.20)


def test_the_atm_call_of_adr_0008_test_3():
    assert float(black76.price(400, 400, 30 / 365, 0.0, 0.20, True)) == pytest.approx(9.148603, abs=5e-7)


def test_hulls_blacks_model_example():
    # Hull's textbook example of Black's model: futures price 20, strike 20, r = 9%, sigma = 25%,
    # 4 months. The European put is 1.12 (to the cent he quotes). Worked by hand: d1 = 0.0722,
    # P = e^(-0.03) x 20 x [N(0.0722) - N(-0.0722)] = 0.97045 x 20 x 0.05755 = 1.117.
    assert float(black76.price(20, 20, 4 / 12, 0.09, 0.25, False)) == pytest.approx(1.117, abs=5e-4)


def test_the_surface_mark_of_adr_0004_test_3():
    assert round(float(black76.price(400, 400, 30 / 365, 0.0, 0.20, True)), 4) == 9.1486


def test_the_call_delta_of_adr_0004_test_8():
    g = black76.greeks(400, 400, 400, 30 / 365, 0.0, 0.20, True)
    assert round(float(g["delta"]), 4) == 0.5114


def test_the_usd_greeks_of_adr_0006_test_1():
    g = black76.greeks_usd(1, **ATM, is_call=True)
    # ADR-0006 test 1 prints $20,457.44; the exact value is 20,457.4301 (100 x N(0.0286691) x 400),
    # so the ADR's last digit is a rounding slip. The other three agree with the ADR to the cent.
    assert float(g["delta_usd"]) == pytest.approx(20457.43, abs=0.005)
    assert float(g["gamma_1pct_usd"]) == pytest.approx(2781.94, abs=0.005)
    assert float(g["vega_1vol_usd"]) == pytest.approx(45.73, abs=0.005)
    assert float(g["theta_1d_usd"]) == pytest.approx(-15.24, abs=0.005)


def test_a_straddle_has_twice_the_gamma_vega_and_theta_of_adr_0006_test_1():
    call = black76.greeks_usd(1, **ATM, is_call=True)
    put = black76.greeks_usd(1, **ATM, is_call=False)
    assert float(call["gamma_1pct_usd"] + put["gamma_1pct_usd"]) == pytest.approx(5563.88, abs=0.005)
    assert float(call["vega_1vol_usd"] + put["vega_1vol_usd"]) == pytest.approx(91.46, abs=0.005)
    assert float(call["theta_1d_usd"] + put["theta_1d_usd"]) == pytest.approx(-30.49, abs=0.005)


def test_a_short_position_flips_every_sign():
    long_ = black76.greeks_usd(2, **ATM, is_call=False)
    short = black76.greeks_usd(-2, **ATM, is_call=False)
    for name in long_:
        assert float(short[name]) == pytest.approx(-float(long_[name]))


RNG = np.random.default_rng(20261029)
N_CASES = 2000
F = RNG.uniform(50, 600, N_CASES)
K = F * np.exp(RNG.uniform(-0.6, 0.4, N_CASES))
TAU = RNG.uniform(1 / 365, 2.0, N_CASES)
R = RNG.uniform(0.0, 0.06, N_CASES)
SIGMA = RNG.uniform(0.05, 1.5, N_CASES)
S = F * np.exp(-RNG.uniform(0.0, 0.05, N_CASES))     # any spot: the greeks hold F/S fixed


def test_put_call_parity_holds_on_2000_random_cases():
    call = black76.price(F, K, TAU, R, SIGMA, True)
    put = black76.price(F, K, TAU, R, SIGMA, False)
    assert np.allclose(call - put, np.exp(-R * TAU) * (F - K), rtol=0, atol=1e-9 * F)


def test_every_price_lies_inside_its_bounds():
    for is_call in (True, False):
        lower, upper = black76.price_bounds(F, K, TAU, R, is_call)
        value = black76.price(F, K, TAU, R, SIGMA, is_call)
        assert np.all(value >= lower - 1e-9) and np.all(value <= upper + 1e-9)


def test_price_rises_with_sigma():
    low = black76.price(F, K, TAU, R, SIGMA, True)
    high = black76.price(F, K, TAU, R, SIGMA + 0.01, True)
    assert np.all(high >= low)


@pytest.mark.parametrize("is_call", [True, False])
def test_greeks_match_central_finite_differences(is_call):
    g = black76.greeks(S, F, K, TAU, R, SIGMA, is_call)
    ratio = F / S                    # F moves with S: the spot greeks hold F/S fixed

    def value(spot=S, sigma=SIGMA, tau=TAU):
        return black76.price(spot * ratio, K, tau, R, sigma, is_call)

    h = 1e-5 * S
    delta = (value(spot=S + h) - value(spot=S - h)) / (2 * h)
    # Gamma as the difference of the analytic delta: a second difference of the price would lose
    # half its digits to rounding on the short-dated cases.
    up = black76.greeks(S + h, (S + h) * ratio, K, TAU, R, SIGMA, is_call)["delta"]
    down = black76.greeks(S - h, (S - h) * ratio, K, TAU, R, SIGMA, is_call)["delta"]
    gamma = (up - down) / (2 * h)
    dv = 1e-5
    vega = (value(sigma=SIGMA + dv) - value(sigma=SIGMA - dv)) / (2 * dv)
    dt = 1e-6
    theta = -(value(tau=TAU + dt) - value(tau=TAU - dt)) / (2 * dt)   # time passing shortens tau
    scale = np.maximum(1.0, np.abs(F))
    assert np.allclose(g["delta"], delta, rtol=1e-6, atol=1e-7)
    assert np.allclose(g["gamma"], gamma, rtol=1e-5, atol=1e-8)
    assert np.allclose(g["vega"], vega, rtol=1e-6, atol=1e-6 * scale)
    assert np.allclose(g["theta"], theta, rtol=1e-5, atol=1e-5 * scale)


def test_intrinsic_at_expiry():
    assert list(black76.intrinsic(450, [440, 460], True)) == [10, 0]
    assert list(black76.intrinsic(450, [440, 460], False)) == [0, 10]


def test_the_vega_function_is_the_greeks_vega_and_the_slope_of_the_price():
    # black76.vega is what the IV solver's Newton step and its resolution check divide by; it must
    # be dV/dsigma itself (the walkthrough's mutant "vega without sqrt tau" survived once the IV
    # tests stopped using it in their own assertions).
    rng = np.random.default_rng(76)
    n = 500
    forward, tau, sigma, rate = 400.0, rng.uniform(2 / 365, 2.0, n), rng.uniform(0.05, 1.0, n), rng.uniform(0, 0.06, n)
    strike = forward * np.exp(rng.uniform(-0.4, 0.3, n))
    analytic = black76.vega(forward, strike, tau, rate, sigma)
    assert np.allclose(analytic, black76.greeks(forward, forward, strike, tau, rate, sigma, True)["vega"], rtol=1e-12, atol=0)
    h = 1e-5
    bumped = (black76.price(forward, strike, tau, rate, sigma + h, True)
              - black76.price(forward, strike, tau, rate, sigma - h, True)) / (2 * h)
    assert np.allclose(analytic, bumped, rtol=1e-5, atol=1e-8)
