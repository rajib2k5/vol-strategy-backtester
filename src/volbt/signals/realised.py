"""Realised variance from daily bars (milestone 4, plan section 4).

    total_log_returns(bars, dividends)   (dates, r): r_i = ln((C_i + D_i) / C_{i-1}), close to close
    window_variance(r, n)                the mean of r^2 over each window of n returns, ending at each index
    window_mean(v, n)                    the same over values already squared (HAR's v_i = r_i^2)

C is the UNADJUSTED close and D the dividend per share with ex-date i, both read through the view (the view serves
no adjusted close: its level on day t is scaled by every dividend paid after t). Adding the dividend back makes the
return a total return, so an ex-date's price drop is not counted as variance. A weekend or a holiday counts as one
return, close to close.

A dividend whose ex-date is not a bar date (none in the store: every SPY ex-date is a session) is added to the first
bar after it, the session whose close shows the drop (default taken 2026-11-09, owner can override). One dated before
the first bar has no return to join and is dropped.

May import (volbt): pricing, view. numpy only.
"""

from __future__ import annotations

import numpy as np


def as_days(values) -> np.ndarray:
    """Dates from a view's frame (Timestamps or dates) as numpy datetime64[D]."""
    return np.asarray(values).astype("datetime64[D]")


def total_log_returns(bars, dividends) -> tuple[np.ndarray, np.ndarray]:
    """(dates, r) for every bar after the first: dates as datetime64[D], r_i = ln((C_i + D_i) / C_{i-1}).

    `bars` has `date` and `close` (view.spy_bars()), sorted by date; `dividends` has `ex_date` and `amount`
    (view.dividends()).
    """
    days = as_days(bars["date"])
    close = np.asarray(bars["close"], dtype=float)
    added = np.zeros(close.size)
    if len(dividends):
        ex = as_days(dividends["ex_date"])
        amount = np.asarray(dividends["amount"], dtype=float)
        at = np.searchsorted(days, ex, "left")          # the ex-date's bar, or the first bar after it
        keep = (at > 0) & (at < days.size)
        np.add.at(added, at[keep], amount[keep])
    if close.size < 2:
        return days[1:], np.zeros(0)
    return days[1:], np.log((close[1:] + added[1:]) / close[:-1])


def window_variance(r, n: int) -> np.ndarray:
    """Element i: the mean of r^2 over r[i-n+1 .. i]; NaN for i < n - 1."""
    return window_mean(np.asarray(r, dtype=float) ** 2, n)


def window_mean(v, n: int) -> np.ndarray:
    """Element i: the mean of v[i-n+1 .. i]; NaN for i < n - 1.

    A direct sum per window (np.convolve), so each element depends only on its own n values: the same element is
    bit-identical whatever comes after it (a cumulative sum would not be).
    """
    v = np.asarray(v, dtype=float)
    out = np.full(v.size, np.nan)
    if n >= 1 and v.size >= n:
        out[n - 1:] = np.convolve(v, np.ones(n), "valid") / n
    return out
