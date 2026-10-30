"""Early exercise of American SPY options: the call closed form and the put lattice rule (ADR-0003).

Calls. A call is worth exercising early only to collect a dividend, so only just before an
ex-date. Exercising pays S - K now; holding keeps a call on the ex-dividend stock S - D. When that
ex-date is the last one before expiry, the held call is European, and European put-call parity
turns "exercise beats holding" into a closed form (ADR-0003, Context):

    exercise  <=>  D > P_E(K) + K (1 - exp(-r tau))

with P_E the European put on the ex-dividend stock and tau from the ex-date to expiry. In words:
the dividend must beat what holding is still worth, the put's insurance plus the interest on K.

Puts. A deep in-the-money put is worth exercising early to earn interest on K sooner, but the
mirror image of the call rule is only NECESSARY, not sufficient: it ignores the right to exercise
later, and the option to wait for an ex-date (the put gains D when the stock goes ex). So:

1. Pre-filter: K (1 - exp(-r tau)) > C_E(K) + PV(dividends before expiry), with C_E the
   Black-76 call. A put that fails it cannot be optimal to exercise, and the lattice is skipped.
2. Decision: a CRR lattice at N = 500 (lattice.py). Exercise iff the value of waiting,
   continuation - (K - S), is at most exercise_tol = $0.005 per share.

The margin continuation - (K - S) is returned with every decision, so the engine can store it
(`expiry_events.threshold_value`, ADR-0003).
"""

from __future__ import annotations

import numpy as np

from volbt.pricing.black76 import price as b76_price
from volbt.pricing.forward import carry_forward
from volbt.pricing.lattice import EXERCISE_TREE_STEPS, crr

EXERCISE_TOL = 0.005         # USD per share: the boundary's tolerance (ADR-0003 Decision 5)


def call_exercises_before_ex(spot, strike, dividend, rate, sigma, tau_after):
    """True where an ITM call is exercised just before an ex-date with dividend D.

    `tau_after` runs from the ex-date to expiry; P_E is priced on the ex-dividend stock S - D,
    with no later dividend (the closed form is exact only then). At tau_after = 0 the put is worth
    its intrinsic value and the interest term is 0, so any dividend above max(K - S + D, 0)
    triggers it (ADR-0003 test 5).
    """
    spot, strike, dividend, rate, sigma, tau_after = (np.asarray(x, dtype=float)
                                                      for x in (spot, strike, dividend, rate, sigma, tau_after))
    ex_stock = spot - dividend
    safe_tau = np.where(tau_after > 0, tau_after, 1.0)
    put = np.where(tau_after > 0,
                   b76_price(ex_stock * np.exp(rate * safe_tau), strike, safe_tau, rate, sigma, False),
                   np.maximum(strike - ex_stock, 0.0))
    interest = strike * (1 - np.exp(-rate * tau_after))
    return (spot > strike) & (dividend > put + interest)


def put_prefilter(spot: float, strike: float, rate: float, sigma: float, tau: float,
                  div_times=(), div_amounts=()) -> tuple[bool, float, float]:
    """(fires, lhs, rhs) of K (1 - exp(-r tau)) > C_E(K) + sum D_i exp(-r tau_i). Necessary, not sufficient.

    C_E is Black-76 on the carry forward of the same spot and dividends (forward.carry_forward).
    ADR-0003 test 7a: K = 450, S = 420, r = 5%, sigma 0.20, 30 days gives 1.8455 > 1.6026.
    """
    times, amounts = np.asarray(div_times, dtype=float), np.asarray(div_amounts, dtype=float)
    paid = (times > 0) & (times <= tau)
    forward = carry_forward(spot, rate, tau, times, amounts)
    call = float(b76_price(forward, strike, tau, rate, sigma, True))
    lhs = strike * (1 - np.exp(-rate * tau))
    rhs = call + float((amounts[paid] * np.exp(-rate * times[paid])).sum())
    return bool(lhs > rhs), float(lhs), float(rhs)


def put_early_exercise(spot: float, strike: float, rate: float, sigma: float, tau: float,
                       div_times=(), div_amounts=(), steps: int = EXERCISE_TREE_STEPS,
                       tol: float = EXERCISE_TOL) -> dict:
    """ADR-0003's put rule for one ITM put lot.

    Returns {exercise, method, margin}: method is "prefilter" when the necessary condition fails
    (margin None: the lattice was not run) or "lattice"; margin = continuation - (K - S).
    """
    fires, _, _ = put_prefilter(spot, strike, rate, sigma, tau, div_times, div_amounts)
    if not fires:
        return {"exercise": False, "method": "prefilter", "margin": None}
    times = np.atleast_2d(np.asarray(div_times, dtype=float)) if len(div_times) else None
    amounts = np.atleast_2d(np.asarray(div_amounts, dtype=float)) if len(div_amounts) else None
    root = crr(spot, strike, tau, rate, sigma, False, times, amounts, steps)
    margin = float(root["continuation"][0] - (strike - spot))
    return {"exercise": margin <= tol, "method": "lattice", "margin": margin}
