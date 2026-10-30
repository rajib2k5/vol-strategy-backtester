"""De-Americanisation: each quote's AMERICAN IV on the CRR lattice, and its early-exercise premium there.

The premium of a quote is EEP = A(sigma) - E(sigma), American minus European on one lattice
(lattice.py). The question is WHICH sigma. ADR-0008 §3a first took sigma_0, the Black-76 IV of the
raw mid. But the raw mid of an American put contains the premium, so sigma_0 is too high, the
premium at sigma_0 is too large, and the error does not shrink with more passes or more steps: on
a clean synthetic 700-day chain at r = 5.22%, sigma 0.12, that rule settled on a forward 101 bp
low and flagged 120 of 130 quotes PARITY_OUTLIER (M2 review, design claim 3).

So the sigma is the quote's own American IV (the M2 review amendment, default taken 2026-10-29):

    sigma_A solves  A(sigma_A) = mid             on the lattice (S, r, tau, the projected dividends)
    premium         = A(sigma_A) - E(sigma_A)    on the same lattice, never negative
    European-equivalent mid = mid - premium      (= E(sigma_A), to the solver's tolerance)

This is self-consistent: the premium is the one the lattice gives the quote at the vol that
reprices it, and it does not depend on the forward, so one pass is the whole procedure.

The solve, for a whole date's quotes at once:

1. The bracket is [sigma_floor, 5] (lattice.sigma_floor keeps the up-probability inside (0, 1)).
2. The start is the Black-76 IV of the mid on the lattice's own forward (S - PV(D)) e^(r tau),
   moved by the lattice's European discretisation error at that sigma (one closed-form sum, no walk).
3. Each iteration prices A at sigma for every open quote (one backward walk for all of them),
   shrinks the quote's bracket, and steps: Newton with the Black-76 vega on the first step, secant
   after it, bisection whenever a step would leave the bracket or the bracket stops halving.
   The PRICE matches when |A(sigma) - mid| <= tol = max(1e-8, 1e-7 mid) USD.
4. Converged means the price matches AND sigma is IDENTIFIED (M2 round 2, code claim 2; decision
   E3). With dA = A(sigma (1 + d)) - A(sigma), d = iv.RESOLVE_SIGMA_RTOL (1e-6), and dE the same
   for the European price on the same lattice (one bump upward: A(sigma) is the price the solve
   accepted, so it costs one walk per quote, not two; about +50% on a date's pricing time with two):
   - dA > tol: the standard iv.py's pinned check applies to Black-76, with the solve's own price
     tolerance as the resolution, so the matched price pins sigma to 1e-6 of itself; and
   - dA >= SENSITIVITY_MIN dE (0.5): the American price moves with sigma at least half as much as
     the European one, so an error in the lattice's American price moves the premium by no more.
   Deep in the money A(sigma) is FLAT or nearly so (exercising at once is optimal at the root, or
   at the first nodes, for a range of sigma): any sigma there "matches", the premium A - E at it is
   not the quote's, and on a clean 700-day chain at sigma 0.08 the procedure settled 74 bp low with
   198 of 244 quotes flagged (round 2). The first test alone fixed that chain when the truth had
   the procedure's own N = 200, but not with a truth of N = 2,000: there A'/E' was 0.15-0.17 on
   the near-K* puts, their sigma_A 0.082-0.095 against 0.08, F 42 bp low; the second test is why.
   Such a quote gets FAIL_AMERICAN_UNIDENTIFIED here; price_chain then prices its premium at its
   partner's identified American IV, or keeps it out of the forward (chain.py, step 3).
5. A mid at or below A(sigma_floor), or at or above A(5), has no American IV: a fail code
   (iv.FAIL_AMERICAN_*), with NaN for the IV and the premium, never a number. So does a quote with
   no positive mid (american_no_mid), tau <= 0 (american_expired) or a non-finite spot, strike,
   rate, tau, dividend time or dividend amount (american_bad_input; at once, before any walk; a NaN
   dividend is never dropped silently).

A call with no dividend before its expiry, at r >= 0, is never exercised early, so A = E exactly:
those quotes are solved on the closed-form European sum (no walk) and their premium is 0.
"""

from __future__ import annotations

import numpy as np

from volbt.pricing import black76, iv, lattice

PRICE_ATOL = 1e-8             # USD: |A(sigma) - mid| below max(this, PRICE_RTOL x mid) is converged
PRICE_RTOL = 1e-7
SIGMA_CAP = 5.0               # the bracket's top, as the Black-76 solver's
MAX_ITER = 40
# Identified also needs A to move with sigma at least half as much as E does: the premium A - E at a
# sigma off by d sigma is off by (E' - A') d sigma, so with A' >= E' / 2 an error eps in the lattice's
# American price (its discretisation, against the market's) moves the premium by at most eps.
SENSITIVITY_MIN = 0.5
STALL_ITER = 2                # bisect after this many steps that did not halve the bracket


def _carry_forward(spot, rate, tau, div_times, div_amounts):
    """(S - PV(dividends before expiry)) e^(r tau): the forward the lattice itself has."""
    live = (div_amounts > 0) & (div_times > 0) & (div_times <= tau[:, None])
    pv = (np.where(live, div_amounts, 0.0) * np.exp(-rate * div_times)).sum(axis=1)
    return (spot - pv) * np.exp(rate * tau), live.any(axis=1)


def american_iv(mid, spot: float, strike, tau, rate: float, is_call, div_times, div_amounts,
                steps: int = lattice.DEAM_TREE_STEPS) -> dict:
    """sigma_A with A(sigma_A) = mid, and premium A - E at it, quote by quote.

    mid, strike, tau, is_call: (n,); div_times, div_amounts: (n, m), zero-padded (lattice.py's
    rules). Returns {"iv", "premium" (NaN where it failed), "fail" (iv.FAIL_* codes),
    "walks" (backward walks spent on the quote)}.
    """
    mid, strike, tau = (np.asarray(x, dtype=float).ravel() for x in (mid, strike, tau))
    is_call = np.broadcast_to(np.asarray(is_call, dtype=bool), mid.shape).ravel()
    n = mid.size
    div_times = np.asarray(div_times, dtype=float).reshape(n, -1) if np.size(div_times) else np.zeros((n, 0))
    div_amounts = np.asarray(div_amounts, dtype=float).reshape(n, -1) if np.size(div_amounts) else np.zeros((n, 0))
    out_iv, premium = np.full(n, np.nan), np.full(n, np.nan)
    fail = np.zeros(n, dtype=np.int8)
    walks = np.zeros(n, dtype=np.int16)
    if n == 0:
        return {"iv": out_iv, "premium": premium, "fail": fail, "walks": walks}
    # 5. Inputs that cannot be priced fail at once, each with its own code (the first that applies).
    bad_input = (~np.isfinite(strike) | ~np.isfinite(tau) | (not np.isfinite(spot)) | (not np.isfinite(rate))
                 | ~np.isfinite(div_times).all(axis=1) | ~np.isfinite(div_amounts).all(axis=1))
    expired = ~bad_input & ~(tau > 0)
    no_mid = ~bad_input & ~expired & ~(np.isfinite(mid) & (mid > 0))
    fail[bad_input], fail[expired], fail[no_mid] = (iv.FAIL_AMERICAN_BAD_INPUT, iv.FAIL_AMERICAN_EXPIRED,
                                                    iv.FAIL_AMERICAN_NO_MID)
    bad = bad_input | expired | no_mid
    if bad.all():
        return {"iv": out_iv, "premium": premium, "fail": fail, "walks": walks}
    # The rest of the solve never sees the bad rows' values (a NaN would only make warnings).
    tau = np.where(bad, 1.0, tau)
    strike = np.where(bad, spot if np.isfinite(spot) else 1.0, strike)
    mid = np.where(bad, 1.0, mid)
    div_times, div_amounts = np.where(bad[:, None], 0.0, div_times), np.where(bad[:, None], 0.0, div_amounts)
    forward, has_dividend = _carry_forward(spot, rate, tau, div_times, div_amounts)
    # A call with nothing to exercise for is European: closed form, premium 0.
    walk = ~(is_call & ~has_dividend & (rate >= 0))
    floor = lattice.sigma_floor(rate, tau, steps)
    tol = np.maximum(PRICE_ATOL, PRICE_RTOL * mid)

    # 2. The start: Black-76 on the lattice's forward, less the lattice's European discretisation error.
    start = iv.implied_vol(mid, forward, strike, np.where(tau > 0, tau, 1.0), rate, is_call)["iv"]
    start = np.where(np.isfinite(start), start, 0.2)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        offset = (lattice.crr_european(spot, strike, tau, rate, start, is_call, div_times, div_amounts, steps)
                  - black76.price(forward, strike, tau, rate, start, is_call))
        nudged = start - offset / black76.vega(forward, strike, tau, rate, start)
    start = np.where(np.isfinite(nudged) & (nudged > floor) & (nudged < SIGMA_CAP), nudged, start)
    sigma = np.clip(start, floor, SIGMA_CAP)

    lo, hi = floor.copy(), np.full(n, SIGMA_CAP)
    lo_seen, hi_seen = np.zeros(n, bool), np.zeros(n, bool)
    prev_sigma, prev_gap = np.full(n, np.nan), np.full(n, np.nan)
    stall = np.zeros(n, dtype=np.int16)
    a_at, e_at = np.full(n, np.nan), np.full(n, np.nan)      # A and E at the accepted sigma
    open_ = np.flatnonzero(~bad)
    for _ in range(MAX_ITER):
        if open_.size == 0:
            break
        a = open_
        price = np.empty(a.size)
        walked = walk[a]
        if walked.any():
            w = a[walked]
            price[walked] = lattice.crr(spot, strike[w], tau[w], rate, sigma[w], is_call[w], div_times[w],
                                        div_amounts[w], steps)["price"]
            walks[w] += 1
        if (~walked).any():
            c = a[~walked]
            price[~walked] = lattice.crr_european(spot, strike[c], tau[c], rate, sigma[c], is_call[c], div_times[c],
                                                  div_amounts[c], steps)
        gap = price - mid[a]
        done = np.abs(gap) <= tol[a]
        if done.any():
            d = a[done]
            european = lattice.crr_european(spot, strike[d], tau[d], rate, sigma[d], is_call[d], div_times[d],
                                            div_amounts[d], steps)
            out_iv[d] = sigma[d]
            premium[d] = np.where(walk[d], np.maximum(price[done] - european, 0.0), 0.0)
            a_at[d], e_at[d] = price[done], european
        # The bracket: A rises with sigma, so a price above the mid caps sigma, one below floors it.
        width_before = hi[a] - lo[a]
        above = gap > 0
        hi[a[above]], hi_seen[a[above]] = sigma[a[above]], True
        lo[a[~above]], lo_seen[a[~above]] = sigma[a[~above]], True
        # 4. At an edge of the bracket and still on the wrong side: there is no American IV.
        below_floor = ~done & above & (sigma[a] <= floor[a])
        above_cap = ~done & ~above & (sigma[a] >= SIGMA_CAP)
        fail[a[below_floor]] = iv.FAIL_AMERICAN_BELOW_FLOOR
        fail[a[above_cap]] = iv.FAIL_AMERICAN_ABOVE_CAP
        keep = ~done & ~below_floor & ~above_cap
        a, gap, width_before = a[keep], gap[keep], width_before[keep]
        # 3. The next sigma: secant after the first step, Newton (Black-76 vega) on it.
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            secant = sigma[a] - gap * (sigma[a] - prev_sigma[a]) / (gap - prev_gap[a])
            newton = sigma[a] - gap / black76.vega(forward[a], strike[a], tau[a], rate, sigma[a])
        step = np.where(np.isfinite(prev_sigma[a]) & np.isfinite(secant), secant, newton)
        # A true bracket (both ends priced) that did not halve: the secant is creeping, so bisect.
        bracketed = lo_seen[a] & hi_seen[a]
        stall[a] = np.where(bracketed & (hi[a] - lo[a] > 0.5 * width_before), stall[a] + 1, 0)
        inside = np.isfinite(step) & (step > lo[a]) & (step < hi[a]) & (stall[a] < STALL_ITER)
        # Outside the bracket: try the edge itself once (it may be where the root is not), else bisect.
        to_floor = ~inside & np.isfinite(step) & (step <= lo[a]) & ~lo_seen[a]
        to_cap = ~inside & np.isfinite(step) & (step >= hi[a]) & ~hi_seen[a]
        bisect = 0.5 * (lo[a] + hi[a])
        stall[a] = np.where(inside | to_floor | to_cap, stall[a], 0)
        prev_sigma[a], prev_gap[a] = sigma[a], gap
        sigma[a] = np.where(inside, step, np.where(to_floor, lo[a], np.where(to_cap, hi[a], bisect)))
        # A bracket closed to float precision: the sigma is as pinned as it can be.
        pinned = lo_seen[a] & hi_seen[a] & (hi[a] - lo[a] <= 1e-12 * hi[a])
        if pinned.any():
            p = a[pinned]
            american = np.where(walk[p], lattice.crr(spot, strike[p], tau[p], rate, sigma[p], is_call[p], div_times[p],
                                                     div_amounts[p], steps)["price"], np.nan)
            european = lattice.crr_european(spot, strike[p], tau[p], rate, sigma[p], is_call[p], div_times[p],
                                            div_amounts[p], steps)
            out_iv[p] = sigma[p]
            premium[p] = np.where(walk[p], np.maximum(american - european, 0.0), 0.0)
            a_at[p], e_at[p] = np.where(walk[p], american, european), european
        open_ = a[~pinned]
    fail[open_] = iv.FAIL_AMERICAN_NO_CONVERGENCE
    # 4. Identified: A(sigma (1 + d)) - A(sigma) clears the price tolerance, and is at least
    # SENSITIVITY_MIN times E(sigma (1 + d)) - E(sigma). One bump, upward, for every matched quote at
    # once: A at sigma itself is the price the solve accepted (one walk, not two, per quote).
    m = np.flatnonzero(np.isfinite(out_iv))
    if m.size:
        bumped = out_iv[m] * (1 + iv.RESOLVE_SIGMA_RTOL)
        up = np.empty(m.size)
        walked = walk[m]
        if walked.any():
            w = m[walked]
            up[walked] = lattice.crr(spot, strike[w], tau[w], rate, bumped[walked], is_call[w], div_times[w],
                                     div_amounts[w], steps)["price"]
            walks[w] += 1
        european_up = lattice.crr_european(spot, strike[m], tau[m], rate, bumped, is_call[m], div_times[m],
                                           div_amounts[m], steps)
        up[~walked] = european_up[~walked]
        spread = up - a_at[m]
        flat = ~((spread > tol[m]) & (spread >= SENSITIVITY_MIN * (european_up - e_at[m])))
        out_iv[m[flat]], premium[m[flat]] = np.nan, np.nan
        fail[m[flat]] = iv.FAIL_AMERICAN_UNIDENTIFIED
    return {"iv": out_iv, "premium": premium, "fail": fail, "walks": walks}
