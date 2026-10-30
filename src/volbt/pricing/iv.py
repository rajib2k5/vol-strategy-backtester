"""Implied volatility: the sigma at which Black-76 returns a given price (ADR-0008 §7).

The price of an option rises with sigma, from its discounted intrinsic value (sigma -> 0) to its
upper bound (sigma -> infinity), so each price inside the bounds has exactly one sigma. Finding it
is a one-dimensional root search, done in four stages for a whole chain at once:

1. Bounds first. A call needs DF max(F - K, 0) < C < DF F, a put DF max(K - F, 0) < P < DF K
   (black76.price_bounds). A price on or outside them has no IV: IV_FAIL, never an exception and
   never a clipped sigma like 5.0 (ADR-0008 test 4). So does a price inside the bounds whose
   sigma lies outside the search range [1e-4, 5] ("no_root").
2. The OTM side. By put-call parity an in-the-money price is its lower bound plus the price of the
   out-of-the-money option at the same strike, so the solver always searches on that OTM price,
   the TIME VALUE price - lower. Black-76 computes a small OTM price to many significant digits,
   while the ITM price minus its lower bound keeps only the digits the two share: the time value
   carries the rounding of the ITM price (a few epsilons of its Black-76 terms) and of its bound.
   Stage 5 counts that rounding (M2 round 2, code claim 4: a fixed cut at 1e-9 of the price called
   ITM prices unresolved whose sigma float64 pins, and solved others only to 2e-7).
3. Newton-Raphson on sigma: sigma <- sigma - (B(sigma) - target) / vega(sigma), from the
   Brenner-Subrahmanyam guess sqrt(2 pi / tau) V / (DF F) (exact at the money to first order),
   clipped to [0.01, 3]. It stops when |B - target| <= 1e-10 x target AND the step it would take
   next, |B - target| / vega, is below 1e-10 of sigma: tolerances on the price RELATIVE to itself
   and on sigma, so a price of 1e-13 is not "converged" at whatever sigma the guess was clipped to
   (the M2 review: an absolute 1e-8 USD tolerance returned 0.01 after 0 steps for any price below
   1e-8), and a price on a flat stretch is not "converged" far from its root.
4. Bisection on [1e-4, 5] for every quote where Newton cannot be trusted: a step that leaves the
   bracket, a vega below 1e-8, or no convergence in 50 steps. It halves the bracket until it is
   narrower than 1e-10 of sigma.
5. Every answer, from either solver, must be PINNED: float64's rounding of the price at it (a few
   epsilons of Black-76's two terms, plus a few of the smallest normal float, plus for an ITM
   price the rounding of the ITM price and of its bound, which its time value inherits), divided
   by vega, must be below 1e-6 of sigma. A price float cannot resolve fails it: where Black-76 underflows
   (no sigma reprices 5e-324), and near the upper bound, where the price is flat in sigma and a
   match to 1e-10 can still sit far from the root (a 30-year call at sigma 3 "converged" at
   2.37). "Unresolved", never a number. (It also covers the reprice check bisection once had:
   a bracket 1e-10 sigma wide that does not reprice the target to 1e-6 is one where Black-76
   underflows, which this check refuses first.)

WHERE 1e-10 HOLDS. Newton stops at a step below 1e-10 of sigma and bisection at a bracket that
narrow, so sigma is within 1e-10 of itself of the true sigma wherever float64's rounding of the
price, over vega, is below 1e-10 of sigma: every OTM price of the review's domain (sigma 0.01-4,
tau 1 day to 3 years) came back within 9.99e-11. Elsewhere the price itself pins sigma only to
that rounding over vega, which the pinned check keeps below 1e-6 of sigma: near the upper bound
(OTM calls of 1-30 years at sigma 0.5-2.4, up to 4.6e-8 measured) and for every ITM price, whose
time value carries the ITM price's rounding (up to 4.6e-8 on the review's 200,000 random ITM
cases). data/logs/report_m2.txt, block "IV solver accuracy", has the counts. An ITM answer is never
claimed to 1e-10.

What comes back, per quote: the IV (NaN when there is none), which solver found it, how many
iterations it took, and why it failed. The codes are small integers so a whole chain fits in
numpy arrays; SOLVER_NAMES and FAIL_NAMES turn them into the strings volbt.build stores. The
"american_*" codes belong to the American IV solve of deam.py; they share this one list so that
quote_iv.iv_fail_reason has one vocabulary.
"""

from __future__ import annotations

import numpy as np

from scipy.special import ndtr

from volbt.pricing.black76 import d1_d2, price_bounds, vega as b76_vega
from volbt.pricing.black76 import price as b76_price

PRICE_RTOL = 1e-10            # Newton has converged when |B - target| <= this x target...
NEWTON_SIGMA_RTOL = 1e-10     # ...and its next step |B - target| / vega is below this x sigma
SIGMA_RTOL = 1e-10            # bisection has converged when the bracket is narrower than this x sigma
RESOLVE_SIGMA_RTOL = 1e-6     # and float's rounding of B, over vega, must pin sigma to this x sigma
ROUNDING_ULPS = 8             # the rounding of a Black-76 price: this many epsilons of its two terms
NEWTON_MAX_ITER = 50
BISECTION_MAX_ITER = 100      # 5 / 2^100 is far below float precision in sigma: always enough
SIGMA_LO, SIGMA_HI = 1e-4, 5.0  # the search range, and Newton's bracket
GUESS_LO, GUESS_HI = 0.01, 3.0  # where the starting guess is clipped
VEGA_MIN = 1e-8

SOLVER_NONE, SOLVER_NEWTON, SOLVER_BISECTION = 0, 1, 2
SOLVER_NAMES = ("", "newton", "bisection")
(FAIL_NONE, FAIL_BELOW_BOUND, FAIL_ABOVE_BOUND, FAIL_NO_ROOT, FAIL_UNRESOLVED,
 FAIL_AMERICAN_BELOW_FLOOR, FAIL_AMERICAN_ABOVE_CAP, FAIL_AMERICAN_NO_CONVERGENCE, FAIL_AMERICAN_UNIDENTIFIED,
 FAIL_AMERICAN_NO_MID, FAIL_AMERICAN_EXPIRED, FAIL_AMERICAN_BAD_INPUT) = range(12)
FAIL_NAMES = ("", "below_lower_bound", "above_upper_bound", "no_root", "unresolved",
              "american_below_floor", "american_above_cap", "american_no_convergence", "american_unidentified",
              "american_no_mid", "american_expired", "american_bad_input")


def price_rounding(forward, strike, tau, rate, sigma, is_call):
    """How far float64 can be off in a Black-76 price: ROUNDING_ULPS epsilons of its two terms.

    B = DF [F N(d1) - K N(d2)] (a call) is a difference of two terms; when they nearly cancel, as for
    a price close to its upper bound, the rounding is set by the terms, not by B. Near float64's
    smallest normal number the rounding is absolute, so a few of it are added.
    """
    d1, d2 = d1_d2(forward, strike, tau, sigma)
    df = np.exp(-np.asarray(rate, dtype=float) * np.asarray(tau, dtype=float))
    terms = np.where(is_call, forward * ndtr(d1) + strike * ndtr(d2), strike * ndtr(-d2) + forward * ndtr(-d1))
    # Below float64's smallest normal number (2.2e-308) precision is absolute, not relative.
    return ROUNDING_ULPS * (np.finfo(float).eps * df * terms + np.finfo(float).tiny)


def brenner_subrahmanyam(price, forward, tau, rate):
    """The starting guess sqrt(2 pi / tau) V / (DF F), clipped to [0.01, 3]."""
    df = np.exp(-rate * tau)
    guess = np.sqrt(2 * np.pi / tau) * price / (df * forward)
    return np.clip(guess, GUESS_LO, GUESS_HI)


def implied_vol(price, forward, strike, tau, rate, is_call):
    """Solve Black-76 for sigma, quote by quote. Arrays broadcast; every input needs tau > 0.

    Returns {"iv": float array (NaN where no IV), "solver": SOLVER_* codes, "iterations": ints,
    "fail": FAIL_* codes}. Never raises on a bad price: a price with no IV gets a fail code.
    """
    arrays = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in (price, forward, strike, tau, rate)),
                                 np.asarray(is_call, dtype=bool))
    price, forward, strike, tau, rate = (a.astype(float).ravel() for a in arrays[:5])
    is_call = arrays[5].ravel()
    n = price.size
    iv = np.full(n, np.nan)
    solver = np.zeros(n, dtype=np.int8)
    iterations = np.zeros(n, dtype=np.int16)
    fail = np.zeros(n, dtype=np.int8)

    # 1. Bounds. A NaN price fails both comparisons, so it is caught as "below"; so is a NaN input.
    with np.errstate(invalid="ignore"):
        lower, upper = price_bounds(forward, strike, tau, rate, is_call)
    fail[~(price > lower)] = FAIL_BELOW_BOUND
    fail[(price > lower) & ~(price < upper)] = FAIL_ABOVE_BOUND
    fail[(fail == FAIL_NONE) & ~(tau > 0)] = FAIL_NO_ROOT          # at expiry there is no sigma to find
    # 2. The OTM side: the time value is the OTM option's price at the same strike (put-call parity).
    otm_call = strike >= forward
    target = price - lower                      # > 0 wherever price > lower: IEEE subtraction of two
                                                # different finite floats is never 0
    # Inside the bounds but outside what sigma in [1e-4, 5] can produce: no root to find.
    todo = np.flatnonzero(fail == FAIL_NONE)
    args = (forward[todo], strike[todo], tau[todo], rate[todo])
    at_lo = b76_price(*args, SIGMA_LO, otm_call[todo])
    at_hi = b76_price(*args, SIGMA_HI, otm_call[todo])
    no_root = (target[todo] < at_lo) | (target[todo] > at_hi)
    fail[todo[no_root]] = FAIL_NO_ROOT
    todo = todo[~no_root]

    # 3. Newton from the Brenner-Subrahmanyam guess, on the time value.
    sigma = brenner_subrahmanyam(price[todo], forward[todo], tau[todo], rate[todo])
    active = np.arange(todo.size)               # positions in `todo` still iterating
    to_bisect = []
    for step in range(1, NEWTON_MAX_ITER + 1):
        if active.size == 0:
            break
        where = todo[active]
        model = b76_price(forward[where], strike[where], tau[where], rate[where], sigma[active], otm_call[where])
        error = model - target[where]
        slope = b76_vega(forward[where], strike[where], tau[where], rate[where], sigma[active])
        # Converged: the price matches to 1e-10 of itself AND the Newton step it would take next,
        # error / vega, is below 1e-10 of sigma (a flat price can match at the wrong sigma).
        done = (np.abs(error) <= PRICE_RTOL * target[where]) & (np.abs(error) <= NEWTON_SIGMA_RTOL * sigma[active] * slope)
        iv[where[done]] = sigma[active][done]
        solver[where[done]] = SOLVER_NEWTON
        iterations[where[done]] = step - 1
        keep = ~done
        active, error, slope = active[keep], error[keep], slope[keep]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            proposal = sigma[active] - error / slope
        unsafe = (slope < VEGA_MIN) | ~np.isfinite(proposal) | (proposal < SIGMA_LO) | (proposal > SIGMA_HI)
        to_bisect.append(active[unsafe])
        sigma[active[~unsafe]] = proposal[~unsafe]
        active = active[~unsafe]
    # Not converged within NEWTON_MAX_ITER steps: bisection too.
    to_bisect.append(active)
    stuck = todo[np.concatenate(to_bisect)] if to_bisect else np.array([], dtype=int)

    # 4. Bisection on [SIGMA_LO, SIGMA_HI] for the rest, to a bracket of 1e-10 sigma.
    if stuck.size:
        lo = np.full(stuck.size, SIGMA_LO)
        hi = np.full(stuck.size, SIGMA_HI)
        open_ = np.arange(stuck.size)
        for step in range(1, BISECTION_MAX_ITER + 1):
            if open_.size == 0:
                break
            where = stuck[open_]
            mid = 0.5 * (lo[open_] + hi[open_])
            error = b76_price(forward[where], strike[where], tau[where], rate[where], mid, otm_call[where]) - target[where]
            high = error > 0                     # the model price is too high: sigma is too high
            hi[open_[high]] = mid[high]
            lo[open_[~high]] = mid[~high]
            narrow = (hi[open_] - lo[open_]) <= SIGMA_RTOL * hi[open_]
            iv[where[narrow]] = 0.5 * (lo[open_][narrow] + hi[open_][narrow])
            solver[where[narrow]] = SOLVER_BISECTION
            iterations[where[narrow]] = step
            open_ = open_[~narrow]
        fail[stuck[open_]] = FAIL_NO_ROOT       # never seen; kept so a non-convergence cannot pass silently
    # 5. Every answer, Newton's or bisection's: float's rounding of the price, divided by vega, must pin
    # sigma. Near the upper bound B is flat in sigma (a 30-year call at sigma 3 is within 1e-14 of DF F),
    # so a relative price match there says nothing about sigma.
    found = np.flatnonzero(np.isfinite(iv))
    with np.errstate(divide="ignore", invalid="ignore", under="ignore"):
        rounding = price_rounding(forward[found], strike[found], tau[found], rate[found], iv[found], otm_call[found])
        # An ITM price's time value, price - lower, inherits the rounding of the ITM price itself (a few
        # epsilons of ITM Black-76's two terms, which near the money are far larger than the price) and
        # of its bound. An OTM price has lower = 0 and nothing to add.
        itm = lower[found] > 0
        inherited = price_rounding(forward[found], strike[found], tau[found], rate[found], iv[found], is_call[found])
        rounding = rounding + np.where(itm, inherited + ROUNDING_ULPS * np.finfo(float).eps * lower[found], 0.0)
        slope = b76_vega(forward[found], strike[found], tau[found], rate[found], iv[found])
        pinned = rounding <= RESOLVE_SIGMA_RTOL * iv[found] * slope
    bad = found[~pinned]
    iv[bad] = np.nan
    solver[bad] = SOLVER_NONE
    iterations[bad] = 0
    fail[bad] = FAIL_UNRESOLVED
    return {"iv": iv.reshape(arrays[0].shape), "solver": solver.reshape(arrays[0].shape),
            "iterations": iterations.reshape(arrays[0].shape), "fail": fail.reshape(arrays[0].shape)}
