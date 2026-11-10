"""Returns and their summary metrics, ADR-0007 §6 (milestone 4, plan section 2; PSR and DSR are milestone 6).

    daily_returns(nav)              r_t = NAV_t / NAV_{t-1} - 1 for every session after the first
    riskfree_returns(rates, days)   rf_t = e^(r_{t-1} d_t / 365) - 1, d_t the calendar days since the previous session
    sharpe(excess)                  sqrt(252) mean / std (ddof = 1)
    sortino(excess)                 sqrt(252) mean / the downside deviation, sqrt(mean(min(x, 0)^2)) over all n values
    max_drawdown(nav)               the most negative NAV / running peak - 1 (0.0 for a NAV that never falls)
    cagr(nav, days)                 (NAV_last / NAV_first)^(365 / D) - 1, D the calendar days from first to last
    calmar(nav, days)               cagr / |max_drawdown|

`nav` is NAV_mid by session (ADR-0007 §6; max_drawdown takes NAV_liq as well), `rates` the continuous rate r_cc of each
session (the ledger's `rate` column), and `days` the session dates (dates or datetime64), aligned with them. The first
session has no return, so daily_returns and riskfree_returns give n - 1 values, aligned with sessions 1..n-1, and the
excess return is their difference. riskfree_returns is the engine's `rf_return` (volbt.engine.loop, step 7): the
previous session's rate, over the calendar days since it, so Friday to Monday earns three days.

Conventions (each a default taken 2026-11-09, owner can override): the downside deviation divides by all n values,
not by the count of negative ones; a year is 365 calendar days in cagr, as in ADR-0007 §2's accrual; sharpe and sortino
are NaN with fewer than two values or a zero denominator, cagr is NaN over zero days and -1.0 when NAV_last <= 0, and
calmar is NaN when the NAV never falls.

May import (volbt): config, pricing. numpy only.
"""

from __future__ import annotations

import math

import numpy as np

SESSIONS_PER_YEAR = 252
DAYS_PER_YEAR = 365


def as_days(values) -> np.ndarray:
    """Dates (date, Timestamp or datetime64) as numpy datetime64[D]."""
    return np.asarray(values).astype("datetime64[D]")


def daily_returns(nav) -> np.ndarray:
    """NAV_t / NAV_{t-1} - 1 for t = 1..n-1. ADR-0007 test 7: 1,000,000 -> 1,004,287 is 0.4287%."""
    nav = np.asarray(nav, dtype=float)
    return nav[1:] / nav[:-1] - 1.0


def riskfree_returns(rates, days) -> np.ndarray:
    """e^(r_{t-1} d_t / 365) - 1 for t = 1..n-1, d_t = days[t] - days[t-1] in calendar days."""
    rates = np.asarray(rates, dtype=float)
    dates = as_days(days)
    if dates.size != rates.size:
        raise ValueError(f"rates ({rates.size}) and days ({dates.size}) are not aligned")
    return np.expm1(rates[:-1] * np.diff(dates).astype(float) / DAYS_PER_YEAR)


def sharpe(excess) -> float:
    """sqrt(252) mean / std(ddof=1). ADR-0007 test 8: [0.01, -0.01, 0.02, 0.00] gives 6.148, and so does twice it."""
    x = np.asarray(excess, dtype=float)
    if x.size < 2:
        return float("nan")
    std = float(np.std(x, ddof=1))
    return math.sqrt(SESSIONS_PER_YEAR) * float(x.mean()) / std if std > 0 else float("nan")


def sortino(excess) -> float:
    """sqrt(252) mean / sqrt(mean(min(x, 0)^2)), over all n values. [0.01, -0.01, 0.02, 0.00] gives sqrt(252)."""
    x = np.asarray(excess, dtype=float)
    if x.size < 2:
        return float("nan")
    downside = math.sqrt(float(np.mean(np.minimum(x, 0.0) ** 2)))
    return math.sqrt(SESSIONS_PER_YEAR) * float(x.mean()) / downside if downside > 0 else float("nan")


def max_drawdown(nav) -> float:
    """min over t of NAV_t / max(NAV_0..NAV_t) - 1: <= 0. [100, 120, 90, 130, 117] gives -0.25."""
    nav = np.asarray(nav, dtype=float)
    if nav.size == 0:
        return float("nan")
    return float(np.min(nav / np.maximum.accumulate(nav) - 1.0))


def cagr(nav, days) -> float:
    """(NAV_last / NAV_first)^(365 / D) - 1, D = days[-1] - days[0] in calendar days. 100 -> 121 over 730 days: 10%."""
    nav = np.asarray(nav, dtype=float)
    span = as_days(days)
    if nav.size != span.size:
        raise ValueError(f"nav ({nav.size}) and days ({span.size}) are not aligned")
    elapsed = int((span[-1] - span[0]).astype(int)) if span.size else 0
    if elapsed <= 0:
        return float("nan")
    if nav[-1] <= 0:
        return -1.0
    return float((nav[-1] / nav[0]) ** (DAYS_PER_YEAR / elapsed) - 1.0)


def calmar(nav, days) -> float:
    """cagr(nav, days) / |max_drawdown(nav)|; NaN when the NAV never falls."""
    drawdown = max_drawdown(nav)
    return cagr(nav, days) / abs(drawdown) if drawdown < 0 else float("nan")
