"""The CRR binomial lattice for American and European options with discrete dividends.

What it is for. SPY options are American, but the surface is European-equivalent (ADR-0008 §8).
The lattice measures the difference, the EARLY-EXERCISE PREMIUM

    EEP = American price - European price,     both on the SAME lattice

which de-Americanisation subtracts from a mid (deam.py, ADR-0008 §3a and §7). Taking both prices
from one lattice cancels most of the lattice's own discretisation error, so N = 200 steps is
enough for the premium even where it is not for the price. The same lattice decides early
exercise of puts (exercise.py, ADR-0003), at N = 500.

How it works (Cox, Ross and Rubinstein, 1979). Cut tau into N steps of dt = tau / N. Over one
step the stock moves up by u = exp(sigma sqrt(dt)) or down by d = 1/u, with the risk-neutral
up-probability p = (exp(r dt) - d) / (u - d), so the expected stock grows at the rate r. After i
steps with j ups, the stock is S0 u^j d^(i-j). At expiry the option is worth its payoff; walking
back one step, it is worth the discounted expectation exp(-r dt) [p V_up + (1 - p) V_down], and an
American option is also worth at least what exercising it pays right there.

THE GUARD ON p (M2 review). p is a probability only while d < exp(r dt) < u, that is while
sigma sqrt(dt) > |r| dt, or sigma > |r| sqrt(dt). Below that the "probability" leaves (0, 1) and
the walk returns nonsense (at sigma = 1e-4, r = 5%, 30 days, an ITM call priced at 10.000 against
11.7635, and an overflowed, meaningless European binomial sum). So every lattice here prices at
sigma_eff = max(sigma, sigma_floor(r, tau, N)), with sigma_floor = 2 |r| sqrt(dt) (and never below
1e-4): at the floor p is about 0.75 (0.25 for a negative rate). Below the floor the option is
worth what a deterministic stock gives it, which the floor's lattice prices to within a tick. The
American IV solver (deam.py) never asks for a sigma below the floor: its bracket starts there.

Discrete dividends, ESCROWED. A dividend D paid at time t_D makes the stock drop by D on the
ex-date, which would break the recombining tree. The escrowed model splits the price into the
present value of the dividends still to come and a risky part S* = S - PV(dividends) that moves on
the tree. The price at a node at time t is then S* + sum of D exp(-r (t_D - t)) over the dividends
with t_D > t. A dividend with t_D exactly at expiry is in S0's PV but not in the payoff: the stock
has gone ex by the close of that day.

Inputs are arrays: one lattice per option, all stepped together, so a whole chain is priced in one
call. Dividends come as two (n, m) arrays of times (years from now) and amounts; an amount of 0, a
time <= 0 or a time after the option's expiry is ignored, so rows can be padded.
"""

from __future__ import annotations

import numpy as np
from scipy.special import gammaln

DEAM_TREE_STEPS = 200        # ADR-0008 §3a: the de-Americanisation lattice
EXERCISE_TREE_STEPS = 500    # ADR-0003 Decision 5 and ADR-0008 §8: the early-exercise and model-mark lattice
SIGMA_FLOOR_MARGIN = 2.0     # sigma_floor = margin |r| sqrt(dt): p stays near 0.75, well inside (0, 1)
SIGMA_FLOOR_MIN = 1e-4       # and never below the Black-76 solver's own floor (iv.SIGMA_LO)


def _rows(n: int, values) -> np.ndarray:
    return np.broadcast_to(np.asarray(values, dtype=float), (n,)).astype(float)


def _dividends(n: int, times, amounts) -> tuple[np.ndarray, np.ndarray]:
    """(times, amounts) as (n, m) arrays; m = 0 when there are none."""
    if times is None or np.size(times) == 0:
        return np.zeros((n, 0)), np.zeros((n, 0))
    times = np.atleast_2d(np.asarray(times, dtype=float))
    amounts = np.atleast_2d(np.asarray(amounts, dtype=float))
    return (np.broadcast_to(times, (n, times.shape[1])).astype(float),
            np.broadcast_to(amounts, (n, amounts.shape[1])).astype(float))


def sigma_floor(rate, tau, steps: int = DEAM_TREE_STEPS) -> np.ndarray:
    """The lowest sigma the lattice prices at: SIGMA_FLOOR_MARGIN |r| sqrt(tau / N), at least 1e-4.

    Above it the up-probability p is inside (0, 1) (module docstring, "the guard on p").
    """
    dt = np.asarray(tau, dtype=float) / steps
    return np.maximum(SIGMA_FLOOR_MIN, SIGMA_FLOOR_MARGIN * np.abs(np.asarray(rate, dtype=float)) * np.sqrt(np.maximum(dt, 0.0)))


def crr(spot, strike, tau, rate, sigma, is_call, div_times=None, div_amounts=None,
        steps: int = DEAM_TREE_STEPS, american: bool = True) -> dict:
    """Price options on a CRR lattice. Returns {"price": (n,), "continuation": (n,), "up_probability": (n,)}.

    `continuation` is the value at the root of NOT exercising now: the discounted expectation of
    the next step's values. For an American put, exercise is optimal today iff
    continuation <= K - S (ADR-0003 rule, with its $0.005 tolerance in exercise.py).
    `up_probability` is the p this walk used, returned so a test can check the walk itself (M2
    round 2: a separate up_probability() function was tested instead, a copy of the formula).
    Every option needs tau > 0; sigma is raised to sigma_floor (the guard on p).
    """
    sizes = [np.size(x) for x in (spot, strike, tau, rate, sigma, is_call)]
    n = max(sizes)
    spot, strike, tau, rate, sigma = (_rows(n, x) for x in (spot, strike, tau, rate, sigma))
    sigma = np.maximum(sigma, sigma_floor(rate, tau, steps))
    sign = np.where(np.broadcast_to(np.asarray(is_call, dtype=bool), (n,)), 1.0, -1.0)
    div_t, div_d = _dividends(n, div_times, div_amounts)
    live = (div_d > 0) & (div_t > 0) & (div_t <= tau[:, None])
    div_d = np.where(live, div_d, 0.0)

    dt = tau / steps
    move = sigma * np.sqrt(dt)                   # ln u
    up = np.exp(move)
    growth = np.exp(rate * dt)
    p = (growth - 1 / up) / (up - 1 / up)
    weight_up, weight_down = p / growth, (1 - p) / growth    # the discounted step probabilities
    # The risky part of the stock, S* = S - PV of the dividends paid before expiry.
    risky = spot - (div_d * np.exp(-rate[:, None] * div_t)).sum(axis=1)

    # Layout (node, option): the first i + 1 rows are step i's nodes, one contiguous block, and every
    # step works in place in the same three buffers.
    j = np.arange(steps + 1)
    signed = sign[None, :] * risky[None, :] * np.exp((2 * j[:, None] - steps) * move[None, :])  # +-S* at expiry
    value = np.maximum(signed - sign[None, :] * strike[None, :], 0.0)
    scratch = np.empty_like(value)
    continuation = np.zeros(n)
    for i in range(steps - 1, -1, -1):
        now = value[: i + 1]
        np.multiply(value[1 : i + 2], weight_up, out=scratch[: i + 1])
        np.multiply(now, weight_down, out=now)
        np.add(now, scratch[: i + 1], out=now)          # V_i,j = e^(-r dt) [p V_i+1,j+1 + (1 - p) V_i+1,j]
        if i == 0:
            continuation = now[0].copy()
        if american:
            stock = signed[: i + 1]
            np.multiply(stock, up, out=stock)            # S*_i,j = S*_i+1,j u, with its sign
            t = i * dt
            pending = (div_d * (div_t > t[:, None]) * np.exp(-rate[:, None] * (div_t - t[:, None]))).sum(axis=1)
            # Exercising pays sign (S* + PV of the dividends still to come - K).
            np.add(stock, sign * (pending - strike), out=scratch[: i + 1])
            np.maximum(now, scratch[: i + 1], out=now)
    return {"price": value[0].copy(), "continuation": continuation, "up_probability": p}


def crr_european(spot, strike, tau, rate, sigma, is_call, div_times=None, div_amounts=None,
                 steps: int = DEAM_TREE_STEPS) -> np.ndarray:
    """The European price on the same lattice, in closed form: no backward walk is needed.

    With no early exercise the root value is the discounted payoff averaged over the binomial
    distribution of the number of ups: exp(-r tau) sum_j C(N, j) p^j (1 - p)^(N - j) payoff_j.
    Equal to crr(..., american=False) to rounding (a test checks it), in O(N) instead of O(N^2).
    The same floor on sigma as crr.
    """
    n = max(np.size(x) for x in (spot, strike, tau, rate, sigma, is_call))
    spot, strike, tau, rate, sigma = (_rows(n, x) for x in (spot, strike, tau, rate, sigma))
    sigma = np.maximum(sigma, sigma_floor(rate, tau, steps))
    sign = np.where(np.broadcast_to(np.asarray(is_call, dtype=bool), (n,)), 1.0, -1.0)
    div_t, div_d = _dividends(n, div_times, div_amounts)
    live = (div_d > 0) & (div_t > 0) & (div_t <= tau[:, None])
    risky = spot - (np.where(live, div_d, 0.0) * np.exp(-rate[:, None] * div_t)).sum(axis=1)
    dt = tau / steps
    move = sigma * np.sqrt(dt)
    up = np.exp(move)
    p = (np.exp(rate * dt) - 1 / up) / (up - 1 / up)
    j = np.arange(steps + 1)
    # log of the binomial probabilities, so N = 2,000 does not overflow C(N, j).
    log_pmf = (gammaln(steps + 1) - gammaln(j + 1) - gammaln(steps - j + 1))[None, :] \
        + j[None, :] * np.log(p)[:, None] + (steps - j)[None, :] * np.log1p(-p)[:, None]
    node = risky[:, None] * np.exp((2 * j[None, :] - steps) * move[:, None])
    payoff = np.maximum(sign[:, None] * (node - strike[:, None]), 0.0)
    return np.exp(-rate * tau) * (np.exp(log_pmf) * payoff).sum(axis=1)


def early_exercise_premium(spot, strike, tau, rate, sigma, is_call, div_times=None, div_amounts=None,
                           steps: int = DEAM_TREE_STEPS) -> np.ndarray:
    """American minus European on one lattice, per share: never negative (ADR-0008 §3a step 3)."""
    american = crr(spot, strike, tau, rate, sigma, is_call, div_times, div_amounts, steps)["price"]
    european = crr_european(spot, strike, tau, rate, sigma, is_call, div_times, div_amounts, steps)
    # The two sums differ in their last bits even where the premium is exactly 0.
    return np.maximum(american - european, 0.0)
