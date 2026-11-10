"""Realised variance and HAR-RV (milestone 4, plan sections 4 and 10, task 3; EGV E1 and E2 of section 7).

Every series here is made up: literals, or seeded draws.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from volbt.signals import har, realised
from volbt.signals.base import RV_FALLBACK, RV_MISSING


def sessions(start: str, n: int) -> np.ndarray:
    """n weekdays from `start`, as datetime64[D]."""
    first = np.datetime64(start, "D")
    days = np.arange(first, first + np.timedelta64(2 * n, "D"))
    return days[np.is_busday(days)][:n]


def bars(days, closes) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(days), "close": closes})


def dividends(rows) -> pd.DataFrame:
    return pd.DataFrame({"ex_date": pd.to_datetime([d for d, _ in rows]), "amount": [a for _, a in rows]})


# --- realised.py ---------------------------------------------------------------------------------------------------

def test_a_total_return_adds_the_ex_date_dividend_back_to_the_unadjusted_close():
    days = ["2017-03-15", "2017-03-16", "2017-03-17"]
    dates, r = realised.total_log_returns(bars(days, [100.0, 101.0, 99.0]), dividends([("2017-03-17", 1.5)]))
    assert list(dates.astype(str)) == days[1:]
    assert r.tolist() == [np.log(101.0 / 100.0), np.log(100.5 / 101.0)]


def test_a_dividend_dated_between_bars_joins_the_next_bar_and_one_before_the_first_bar_is_dropped():
    days = ["2017-03-16", "2017-03-17", "2017-03-20"]     # the 18th is a Saturday
    _, r = realised.total_log_returns(bars(days, [100.0, 100.0, 98.0]),
                                      dividends([("2017-01-02", 9.0), ("2017-03-18", 2.0)]))
    assert r.tolist() == [0.0, np.log(100.0 / 100.0)]


def test_no_dividends_and_a_single_bar():
    _, r = realised.total_log_returns(bars(["2017-01-03", "2017-01-04"], [100.0, 110.0]), dividends([]))
    assert r.tolist() == [np.log(1.1)]
    dates, r = realised.total_log_returns(bars(["2017-01-03"], [100.0]), dividends([]))
    assert dates.size == 0 and r.size == 0


def test_window_mean_is_the_trailing_mean_with_nan_before_the_first_full_window():
    out = realised.window_mean([1.0, 2.0, 3.0, 4.0, 6.0], 3)
    assert np.isnan(out[:2]).all()
    assert out[2:].tolist() == [2.0, 3.0, 13.0 / 3.0]
    assert realised.window_variance([1.0, -2.0, 2.0], 2)[1:].tolist() == [2.5, 4.0]


def test_window_mean_of_an_element_does_not_depend_on_what_follows_it():
    rng = np.random.default_rng(7)
    v = rng.random(300)
    longer = np.concatenate([v, rng.random(200) * 1e3])
    assert realised.window_mean(v, 22).tobytes() == realised.window_mean(longer, 22)[:300].tobytes()


# --- har.py --------------------------------------------------------------------------------------------------------

def test_the_regressors_are_the_day_week_and_month_components():
    v = np.arange(1.0, 31.0)                    # v_i = i + 1
    x = har.regressors(v)
    assert np.isnan(x[:21]).all()
    assert x[21].tolist() == [1.0, 22.0, np.mean(v[17:22]), np.mean(v[0:22])]
    assert x[29].tolist() == [1.0, 30.0, np.mean(v[25:30]), np.mean(v[8:30])]


def test_the_target_is_the_mean_of_the_next_21_values():
    v = np.arange(1.0, 31.0)
    y = har.targets(v)
    assert y[0] == np.mean(v[1:22]) and y[8] == np.mean(v[9:30])
    assert np.isnan(y[9:]).all()


def test_a_fit_uses_only_the_pairs_whose_target_ends_by_the_fit_date():
    days = sessions("2017-01-02", 700)
    v = np.random.default_rng(1).gamma(2.0, 1e-4, size=days.size)
    fit_date = har.as_date(days[600])
    fitted = har.fit(v, days, fit_date)
    assert fitted.fit_date == fit_date and fitted.n_pairs == 601 - 21 - 21
    # The same fit from data cut at F, and from data whose values after F are tripled and reversed.
    later = v.copy()
    later[601:] = (v[601:] * 3)[::-1]
    assert har.fit(v[:601], days[:601], fit_date) == fitted == har.fit(later, days, fit_date)


def test_too_few_pairs_gives_no_fit():
    days = sessions("2017-01-02", 100)
    v = np.full(days.size, 1e-4)
    assert har.fit(v, days, har.as_date(days[-1]), min_pairs=59) is None
    assert har.fit(v, days, har.as_date(days[-1]), min_pairs=58).n_pairs == 58


def test_lstsq_equals_the_normal_equations():
    """E1: numpy.linalg.lstsq(rcond=None) solves the normal equations X'X b = X'y (rtol 1e-10)."""
    days = sessions("2017-01-02", 900)
    v = np.random.default_rng(2).gamma(2.0, 1e-4, size=days.size)
    fitted = har.fit(v, days, har.as_date(days[-1]))
    x, y = har.regressors(v), har.targets(v)
    rows = np.isfinite(x).all(axis=1) & np.isfinite(y)
    normal = np.linalg.solve(x[rows].T @ x[rows], x[rows].T @ y[rows])
    assert np.allclose(fitted.coef, normal, rtol=1e-10, atol=0)


def test_on_rank_deficient_input_lstsq_gives_the_minimum_norm_solution():
    """E1, rank-deficient: with v constant at c every row is [1, c, c, c] and every target c, so the normal
    equations have a line of solutions; the minimum-norm one is c [1, c, c, c] / (1 + 3 c^2)."""
    c = 0.5
    days = sessions("2017-01-02", 600)
    fitted = har.fit(np.full(days.size, c), days, har.as_date(days[-1]))
    expected = c * np.array([1.0, c, c, c]) / (1 + 3 * c * c)
    assert np.allclose(fitted.coef, expected, rtol=1e-10, atol=0)


def test_a_simulated_har_process_is_recovered():
    """E2: v_{i+1} = c + b_d v_i + b_w mean5 + b_m mean22 + noise, fitted at horizon 1 (Corsi 2009's daily HAR-RV),
    gives back (c, b_d, b_w, b_m) within 0.03 on 20,000 seeded sessions."""
    true = np.array([2e-5, 0.35, 0.30, 0.20])
    rng = np.random.default_rng(3)
    n = 20_000
    v = np.full(n, 1e-4)
    for i in range(21, n - 1):
        mean = true @ [1.0, v[i], v[i - 4:i + 1].mean(), v[i - 21:i + 1].mean()]
        v[i + 1] = mean * rng.gamma(4.0, 0.25)       # multiplicative noise with mean 1 keeps v > 0
    first = np.datetime64("1950-01-02", "D")
    days = np.arange(first, first + np.timedelta64(n, "D"))
    fitted = har.fit(v, days, har.as_date(days[-1]), horizon=1)
    assert np.allclose(np.array(fitted.coef[1:]), true[1:], atol=0.03)
    assert abs(fitted.coef[0] - true[0]) < 1e-5


def ar1_variance(n: int, seed: int, c: float = 4e-5, phi: float = 0.8) -> np.ndarray:
    """v_{t+1} = (c + phi v_t) eta_{t+1}, eta ~ Gamma(16, 1/16) iid (mean 1): E[v_{t+k} | v_t] = c (1 - phi^k) /
    (1 - phi) + phi^k v_t, and v has a finite fourth moment (E[(phi eta)^4] = 0.58 < 1)."""
    eta = np.random.default_rng(seed).gamma(16.0, 1 / 16, n)
    v = np.empty(n)
    v[0] = c / (1 - phi)
    for t in range(n - 1):
        v[t + 1] = (c + phi * v[t]) * eta[t + 1]
    return v


def test_the_direct_21_session_fit_recovers_an_exactly_linear_conditional_mean():
    """C6: for the process of ar1_variance, the target y_i = mean v_{i+1..i+21} has E[y_i | past] = A + B v_i exactly,
    B = mean_k phi^k (k = 1..21) and A = c / (1 - phi) (1 - B): linear in the HAR regressors with week and month
    coefficients 0. The horizon-21 fit recovers (A, B, 0, 0), closer on 320,000 sessions than on 20,000."""
    c, phi = 4e-5, 0.8
    b = sum(phi ** k for k in range(1, 22)) / 21
    true = np.array([c / (1 - phi) * (1 - b), b, 0.0, 0.0])
    scale = np.array([true[0], 1.0, 1.0, 1.0])
    first = np.datetime64("1950-01-02", "D")
    errors = []
    for n in (20_000, 320_000):
        days = np.arange(first, first + np.timedelta64(n, "D"))
        fitted = har.fit(ar1_variance(n, seed=7), days, har.as_date(days[-1]))
        errors.append(np.abs((np.array(fitted.coef) - true) / scale))
    assert errors[1].max() < 0.03, errors[1]
    assert errors[1].sum() < errors[0].sum()


def test_naive_rv22_is_the_mean_of_the_last_22_values():
    v = np.arange(1.0, 31.0)
    assert har.naive_rv22(v) == np.mean(v[8:30])
    assert np.isnan(har.naive_rv22(v[:21]))


def test_a_forecast_at_or_below_zero_falls_back_to_the_naive_one():
    v = np.arange(1.0, 31.0)
    negative = har.HarFit(date(2017, 1, 3), (-100.0, 0.0, 0.0, 0.0), 504)
    assert har.har_forecast(negative, v) == (np.mean(v[8:30]), RV_FALLBACK)
    positive = har.HarFit(date(2017, 1, 3), (1.0, 0.5, 0.0, 0.0), 504)
    assert har.har_forecast(positive, v) == (1.0 + 0.5 * 30.0, 0)
    assert har.har_forecast(negative, v[:21])[1] == RV_FALLBACK | RV_MISSING


def test_the_forecaster_refits_on_the_first_session_of_each_month_and_a_mid_month_start_changes_nothing():
    days = sessions("2017-01-02", 760)
    v = np.random.default_rng(4).gamma(2.0, 1e-4, size=days.size)
    from_start, mid_month = har.HarForecaster(), har.HarForecaster()
    first_mid = 700
    assert days[first_mid].astype(object).day > 1 and days[first_mid - 1].astype(object).month == \
        days[first_mid].astype(object).month
    for i in range(600, days.size):
        a = from_start.forecast(v[:i + 1], days[:i + 1])
        t = days[i].astype(object)
        assert a[1] == har.month_start(days[:i + 1], t)                 # the fit of t's month's first session
        assert a[1].month == t.month and a[1] <= t
        if i >= first_mid:
            assert mid_month.forecast(v[:i + 1], days[:i + 1]) == a     # bit-identical
    assert har.month_start(days, date(2017, 4, 18)) == date(2017, 4, 3)


def test_the_forecaster_has_no_value_before_504_pairs():
    days = sessions("2017-01-02", 560)
    v = np.full(days.size, 1e-4)
    out = har.HarForecaster().forecast(v[:540], days[:540])
    assert np.isnan(out[0]) and out[1:] == (None, RV_MISSING)
    assert har.HarForecaster(min_pairs=400).forecast(v[:540], days[:540])[2] == 0


@pytest.mark.parametrize("forecast", [0.0, -1e-12, -0.5, -0.999])
def test_a_finite_forecast_in_minus_1_to_0_falls_back(forecast):
    """Item 8: the fallback is for every forecast <= 0, not only below -1 (an orchestrator's mutant survived)."""
    v = np.arange(1.0, 31.0)
    fit = har.HarFit(date(2017, 1, 3), (forecast, 0.0, 0.0, 0.0), 504)
    assert har.har_forecast(fit, v) == (np.mean(v[8:30]), RV_FALLBACK)


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_a_non_finite_forecast_falls_back_too(bad):
    v = np.arange(1.0, 31.0)
    fit = har.HarFit(date(2017, 1, 3), (bad, 0.0, 0.0, 0.0), 504)
    assert har.har_forecast(fit, v) == (np.mean(v[8:30]), RV_FALLBACK)
