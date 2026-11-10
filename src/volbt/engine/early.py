"""Early exercise and assignment, decided at step 10 of day t, booked at the start of t + 1 (ADR-0003 §5).

Common inputs, the same in quote and surface mode: S_t, the rate dated strictly before t (ADR-0008
amendment 3), sigma = the day's SURFACE IV at the lot's log-moneyness for its expiry (never a market mid;
for an ITM put that node is the OTM call at the same strike), and the dividends PROJECTED from those paid by
t (ADR-0008 amendment 4): the dividend that goes ex at t + 1 is not known at t, and is never read.

    calls   when t + 1 is a projected ex-date: an ITM call (S_t > K) is exercised iff
            D > P_E(K) + K (1 - e^(-r tau)), tau from the ex-date to expiry (pricing.exercise's closed form,
            exact when that ex-date is the last before expiry). With a further ex-date before expiry: the
            CRR lattice with the call payoff, exercise iff continuation - (S - K) <= tol.
    puts    every day, each ITM put (K > S_t): the necessary pre-filter, then the N = 500 lattice with its
            $0.005 tolerance (pricing.exercise.put_early_exercise); the lattice is never called when the
            pre-filter fails.

Shorts are assigned on EVERY qualifying contract; longs we exercise ourselves. Each decision keeps its
method, sigma and margin for expiry_events (decision_method, decision_iv, threshold_value).
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volbt.pricing import dividends, exercise, lattice
from volbt.pricing.black76 import price as b76_price

DAYS_PER_YEAR = 365


def call_threshold(spot: float, strike: float, dividend: float, rate: float, sigma: float, tau_after: float) -> float:
    """P_E(K) + K (1 - e^(-r tau)) on the ex-dividend stock: the value a dividend must beat (ADR-0003)."""
    ex_stock = spot - dividend
    if tau_after > 0:
        put = float(b76_price(ex_stock * np.exp(rate * tau_after), strike, tau_after, rate, sigma, False))
    else:
        put = max(strike - ex_stock, 0.0)
    return put + strike * (1 - np.exp(-rate * tau_after))


def decide_lot(lot, t: date, t_next: date, spot: float, rate: float, sigma: float, paid, calendar, cfg) -> dict | None:
    """The early-exercise decision for one open lot, or None when its rule does not apply today."""
    strike = lot.strike
    if lot.right == "C":
        if not spot > strike or not dividends.projected_ex_dates(t, t_next, calendar)[-1:] == [t_next]:
            return None
        amount = dividends.projected_amount(paid[0], paid[1], t, t_next)
        if amount is None:
            return None
        later = [d for d in dividends.projected_ex_dates(t_next, lot.expiry, calendar) if d > t_next]
        if not later:
            tau_after = (lot.expiry - t_next).days / DAYS_PER_YEAR
            fires = bool(exercise.call_exercises_before_ex(spot, strike, amount, rate, sigma, tau_after))
            return {"exercise": fires, "method": "call_closed_form", "sigma": sigma, "dividend": amount,
                    "threshold": call_threshold(spot, strike, amount, rate, sigma, tau_after), "ex_date": t_next}
        times, amounts = dividends.schedule(paid[0], paid[1], t, lot.expiry, calendar)
        tau = (lot.expiry - t).days / DAYS_PER_YEAR
        root = lattice.crr(spot, strike, tau, rate, sigma, True, np.atleast_2d(times), np.atleast_2d(amounts),
                           cfg.exercise_tree_steps)
        margin = float(root["continuation"][0] - (spot - strike))
        return {"exercise": margin <= cfg.exercise_tol, "method": "crr", "sigma": sigma, "dividend": amount,
                "threshold": margin, "ex_date": t_next}
    if not strike > spot:
        return None
    times, amounts = dividends.schedule(paid[0], paid[1], t, lot.expiry, calendar)
    tau = (lot.expiry - t).days / DAYS_PER_YEAR
    result = exercise.put_early_exercise(spot, strike, rate, sigma, tau, times, amounts, cfg.exercise_tree_steps,
                                         cfg.exercise_tol)
    return {"exercise": result["exercise"], "method": "crr" if result["method"] == "lattice" else "prefilter",
            "sigma": sigma, "dividend": None, "threshold": result["margin"], "ex_date": None}


def event_type(qty: int) -> str:
    return "early_exercised" if qty > 0 else "early_assigned"
