"""HAR-RV, the direct 21-session forecast (milestone 4, plan section 4).

The regressors are Corsi's (2009) heterogeneous day, week and month components; Corsi fits the one-day equation. The
direct multi-horizon form used here, the h-session-ahead mean regressed on today's components (h = 21), is that of
Andersen, Bollerslev and Diebold (2007). The inputs are daily squared total returns from closes, not intraday
realised variance, so v is a noisy proxy of the day's variance.

    v_i = r_i^2                                   the daily squared total return (volbt.signals.realised)
    x_i = [1, v_i, mean v_{i-4..i}, mean v_{i-21..i}]   day, week (5) and month (22) components
    y_i = mean v_{i+1..i+21}                      the target: the mean daily variance of the next 21 sessions

    fit(v, dates, fit_date)    OLS of y on x (numpy.linalg.lstsq, rcond=None) over the training pairs whose target
                               ENDS on or before fit_date, at least min_pairs (504) of them; None with fewer
    har_forecast(fit, v)       x_t . coef at the last index; a forecast <= 0 (or not finite) falls back to the naive
                               one, flagged RV_FALLBACK
    naive_rv22(v)              mean v_{t-21..t}, the benchmark
    HarForecaster              the stateful forecaster a signal holds: it refits on the first session of each
                               calendar month and keeps that fit for the month

Causality. A fit dated F uses v up to F only: its last target ends at F. The fit date of the forecast at t is the
first session of t's month, found from the bars the view serves, so a run that starts mid-month fits as of that
month's first session, exactly as a run that started earlier did: a value depends on its date, never on the run's
start. ADR-0001 test 6 (tests/test_signals_causal.py) checks that no value up to t0 moves when the inputs after t0
change.

The fit is in levels, so it can forecast a negative variance after a spike; the fallback count is reported (plan
risk 3). min_pairs = 504 (two years of pairs) makes the signal exist from 2002 on the store's bars, which start
2000-01-03.

May import (volbt): pricing, view. numpy only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from volbt.signals.base import RV_FALLBACK, RV_MISSING
from volbt.signals.realised import window_mean

HORIZON = 21
MIN_PAIRS = 504
WEEK, MONTH = 5, 22


@dataclass(frozen=True)
class HarFit:
    fit_date: date
    coef: tuple[float, float, float, float]     # constant, day, week, month
    n_pairs: int


def as_date(day) -> date:
    """A numpy datetime64 (or a date) as a plain date."""
    day = np.datetime64(day, "D").astype(object)
    return date(day.year, day.month, day.day)


def regressors(v) -> np.ndarray:
    """The rows x_i = [1, v_i, mean v_{i-4..i}, mean v_{i-21..i}] for every i; NaN where the month is not complete."""
    v = np.asarray(v, dtype=float)
    x = np.column_stack([np.ones(v.size), v, window_mean(v, WEEK), window_mean(v, MONTH)])
    x[:MONTH - 1] = np.nan
    return x


def targets(v, horizon: int = HORIZON) -> np.ndarray:
    """y_i = mean v_{i+1..i+horizon}; NaN where the window runs past the data."""
    v = np.asarray(v, dtype=float)
    y = np.full(v.size, np.nan)
    if v.size > horizon:
        y[:v.size - horizon] = window_mean(v, horizon)[horizon:]
    return y


def fit(v, dates, fit_date: date, horizon: int = HORIZON, min_pairs: int = MIN_PAIRS) -> HarFit | None:
    """OLS on the pairs (x_i, y_i) whose target ends on or before fit_date; None with fewer than min_pairs.

    `v` and `dates` (datetime64[D] or dates) are aligned and ascending. Only v up to fit_date enters the fit.
    """
    days = np.asarray(dates).astype("datetime64[D]")
    end = int(np.searchsorted(days, np.datetime64(fit_date, "D"), "right"))   # v[:end] is dated <= fit_date
    v = np.asarray(v, dtype=float)[:end]
    x, y = regressors(v), targets(v, horizon)
    rows = np.flatnonzero(np.isfinite(x).all(axis=1) & np.isfinite(y))
    if rows.size < min_pairs:
        return None
    coef, *_ = np.linalg.lstsq(x[rows], y[rows], rcond=None)
    return HarFit(fit_date, tuple(float(c) for c in coef), int(rows.size))


def naive_rv22(v) -> float:
    """mean v_{t-21..t} (22 squared returns); NaN with fewer."""
    month = window_mean(v, MONTH)
    return float(month[-1]) if month.size else float("nan")


def har_forecast(har: HarFit, v) -> tuple[float, int]:
    """(y^_t, flags): x_t . coef at the last index of v; a forecast <= 0 or not finite gives the naive RV22 and
    RV_FALLBACK (plan section 4)."""
    x = regressors(v)
    if not x.shape[0]:
        return float("nan"), RV_MISSING
    forecast = float(x[-1] @ np.asarray(har.coef))
    if np.isfinite(forecast) and forecast > 0:
        return forecast, 0
    naive = naive_rv22(v)
    return naive, RV_FALLBACK | (0 if np.isfinite(naive) else RV_MISSING)


def month_start(dates, t) -> date:
    """The first of `dates` in t's calendar month (t itself when it is the first)."""
    days = np.asarray(dates).astype("datetime64[D]")
    first = np.datetime64(f"{t.year:04d}-{t.month:02d}-01", "D")
    return as_date(days[int(np.searchsorted(days, first, "left"))])


class HarForecaster:
    """The HAR forecast at t, refitted on the first session of each calendar month (module docstring)."""

    def __init__(self, horizon: int = HORIZON, min_pairs: int = MIN_PAIRS) -> None:
        self.horizon, self.min_pairs = horizon, min_pairs
        self.fit_date: date | None = None      # the month's first session the current fit belongs to
        self.current: HarFit | None = None     # None when that date had too few pairs

    def forecast(self, v, dates) -> tuple[float, date | None, int]:
        """(y^_t, the fit's date, flags) at t = the last of `dates`."""
        t = as_date(np.asarray(dates).astype("datetime64[D]")[-1])
        start = month_start(dates, t)
        if start != self.fit_date:
            self.fit_date = start
            self.current = fit(v, dates, start, self.horizon, self.min_pairs)
        if self.current is None:
            return float("nan"), None, RV_MISSING
        value, flags = har_forecast(self.current, v)
        return value, self.current.fit_date, flags
