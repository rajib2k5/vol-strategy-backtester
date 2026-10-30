"""Early exercise (ADR-0003 tests 5, 6 and 7): the call closed form and the put lattice rule."""

import numpy as np
import pytest

from volbt.pricing import exercise, lattice


def test_early_call_assignment_when_the_ex_date_is_the_expiry_date():
    # ADR-0003 test 5: D = 1.80, short 440 call, S = 450, r = 5%, tau from ex-date to expiry = 0.
    # K (1 - e^0) = 0, and the European put at tau = 0 is worth its intrinsic value, 0: 0 < 1.80.
    assert bool(exercise.call_exercises_before_ex(450, 440, 1.80, 0.05, 0.20, 0.0))


def test_no_early_call_assignment_with_30_days_left_after_the_ex_date():
    # ADR-0003 test 6: the interest term is 440 (1 - e^(-0.05 x 30/365)) = 1.8045 and the European
    # put adds to it, so 1.80 does not beat them.
    interest = 440 * (1 - np.exp(-0.05 * 30 / 365))
    assert interest == pytest.approx(1.8045, abs=5e-5)
    assert not bool(exercise.call_exercises_before_ex(450, 440, 1.80, 0.05, 0.20, 30 / 365))


def test_an_out_of_the_money_call_is_never_exercised():
    assert not bool(exercise.call_exercises_before_ex(430, 440, 50.0, 0.05, 0.20, 0.0))


def boundary(decide, low, high):
    """The spot where `decide` switches from False to True, by bisection to a tenth of a cent."""
    while high - low > 0.001:
        middle = (low + high) / 2
        low, high = (low, middle) if decide(middle) else (middle, high)
    return (low + high) / 2


def test_the_call_closed_form_agrees_with_the_lattice_within_5_cents():
    # ADR-0003 test 6: K = 450, sigma 0.20, r = 5%, 7 days after the ex-date, D = 1.70. The closed
    # form fires from S = 462.60 and the lattice optimum from 462.61.
    k, sigma, rate, tau, dividend = 450.0, 0.20, 0.05, 7 / 365, 1.70
    closed = boundary(lambda s: bool(exercise.call_exercises_before_ex(s, k, dividend, rate, sigma, tau)), 451, 480)

    def lattice_exercises(spot):
        # The root is the instant before the ex-date: the dividend goes ex a hair later, and after
        # it the call is European (no later dividend), so the root decision is the whole question.
        root = lattice.crr(spot, k, tau, rate, sigma, True, [[1e-9]], [[dividend]], steps=500)
        return root["continuation"][0] <= spot - k

    tree = boundary(lattice_exercises, 451, 480)
    assert closed == pytest.approx(462.60, abs=0.01)
    assert abs(closed - tree) < 0.05


# ADR-0003 test 7: K = 450, 30 days, sigma 0.20, N = 500, tol $0.005.
CASES = {  # case: (spot, rate, dividend times, dividend amounts, LHS, RHS, margin, assigned)
    "a": (420.0, 0.05, (), (), 1.8455, 1.6026, 0.5201, False),
    "b": (400.0, 0.05, (), (), 1.8455, 0.2159, -0.0037, True),
    "c": (395.0, 0.05, (10 / 365,), (1.70,), 1.8455, 1.7919, 1.0986, False),
    "d": (390.0, 0.0025, (), (), 0.0925, 0.0493, 0.0167, False),
}
MARGINS_AT_2000 = {"a": 0.5187, "b": -0.0009, "c": 1.0997, "d": 0.0169}


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_deep_itm_put_table(case):
    spot, rate, times, amounts, lhs, rhs, margin, assigned = CASES[case]
    fires, got_lhs, got_rhs = exercise.put_prefilter(spot, 450, rate, 0.20, 30 / 365, times, amounts)
    assert fires and got_lhs == pytest.approx(lhs, abs=5e-5) and got_rhs == pytest.approx(rhs, abs=5e-5)
    decision = exercise.put_early_exercise(spot, 450, rate, 0.20, 30 / 365, times, amounts)
    assert decision["method"] == "lattice"
    assert decision["margin"] == pytest.approx(margin, abs=5e-5)
    assert decision["exercise"] is assigned


@pytest.mark.parametrize("case", sorted(CASES))
def test_each_decision_is_stable_at_2000_steps(case):
    spot, rate, times, amounts, *_, assigned = CASES[case]
    decision = exercise.put_early_exercise(spot, 450, rate, 0.20, 30 / 365, times, amounts, steps=2000)
    assert decision["margin"] == pytest.approx(MARGINS_AT_2000[case], abs=5e-5)
    assert decision["exercise"] is assigned


def test_the_prefilter_skips_the_lattice_when_the_necessary_condition_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(exercise, "crr", lambda *a, **k: calls.append(a) or lattice.crr(*a, **k))
    decision = exercise.put_early_exercise(430.0, 450, 0.05, 0.20, 30 / 365)
    assert decision == {"exercise": False, "method": "prefilter", "margin": None}
    assert calls == []
    exercise.put_early_exercise(400.0, 450, 0.05, 0.20, 30 / 365)
    assert len(calls) == 1


def test_the_tolerance_is_half_a_cent():
    # At S = 409.50 waiting is worth 0.0031 more than exercising: inside the $0.005 tolerance, so
    # the put is exercised, though not at a zero tolerance. At 409.80 (0.0054) it is not. The rule
    # fires below about 409.75 rather than at the optimum near 408.8 (ADR-0003, Consequences).
    inside = exercise.put_early_exercise(409.50, 450, 0.05, 0.20, 30 / 365)
    assert 0 < inside["margin"] <= exercise.EXERCISE_TOL and inside["exercise"]
    assert not exercise.put_early_exercise(409.50, 450, 0.05, 0.20, 30 / 365, tol=0.0)["exercise"]
    outside = exercise.put_early_exercise(409.80, 450, 0.05, 0.20, 30 / 365)
    assert outside["margin"] > exercise.EXERCISE_TOL and not outside["exercise"]
