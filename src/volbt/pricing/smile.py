"""The smile of one expiry and the surface across expiries, in TOTAL VARIANCE (ADR-0004).

Total variance w = sigma^2 tau is the variance of ln(F_T / F) to expiry. Working in w instead of
sigma makes the rules simple: w must not fall as tau grows at a fixed log-moneyness k = ln(K/F)
(no calendar arbitrage), and in the far wings w can grow at most like 2|k| (Roger Lee's 2004
moment formula). So the smile is stored as nodes (k_i, w_i), and everything is read off them.

THE SMILE MODEL is the one ADR-0004 names: piecewise-linear total variance through the nodes,
which are the de-Americanised OTM quotes (puts for K < F, calls for K >= F) of one expiry. It is
exact at every quoted strike and needs no optimiser, so it cannot fail to converge on a thin
DoltHub smile; an SVI or SSVI fit is deferred (ADR-0004, Alternatives).

Reading an IV at (k, tau), each step that is not a plain interpolation sets a bit:

2. Own expiry, inside its nodes: w linear in k between the two neighbouring nodes.
3. Beyond the last node (SURFACE_EXTRAP_STRIKE): w extended linearly with the slope of the two
   outermost nodes on that side, clipped to [0, 2] in |k|: never falling away from the money,
   never steeper than Lee's bound. Never held flat.
4. Own expiry absent or thin, with an expiry listed on each side (SURFACE_CROSS_EXPIRY): w linear
   in tau at fixed k between the nearest two, each read by steps 2-3.
5. No expiry on one side (SURFACE_EXTRAP_TENOR): IV held constant along k / sqrt(tau) from the
   nearest expiry, sigma(tau, k) = sigma_near(k sqrt(tau_near / tau)). The smile steepens as
   1/sqrt(tau), so reading the near smile at the same k would understate short-dated wings.

THE CALENDAR CONSTRAINT (M2 review amendment D5, default taken 2026-10-29, revised by round 2's
E1 the same day; SURFACE_CALENDAR_ADJUSTED). The market's own smiles can cross: at some k a
longer expiry's w is below a shorter one's, and both step 4 and step 5 would carry that into the
surface (the first export had 17, 18, 2 and 10 grid cells where w fell from one tenor to the next;
round-1 measurement). So surface_iv never returns a w that falls with tau at a fixed k:

- at and between listed expiries it reads calendar_variance's w_i(k) instead of the expiry's own:
  quoted (anchored) values take the running maximum of the quoted values before them, and each
  extrapolated value is held between the quoted floors before and after it, so an extrapolated
  wing never moves a quote (round 2: the first floor, a running maximum over every expiry's w
  INCLUDING extrapolated wings, raised 78.2% of the nodes it moved off a shorter expiry's
  extrapolated wing). Step 4 is linear between two constrained values, so it rises too;
- beyond the back expiry, step 5's w(tau') along k / sqrt(tau') is replaced by its running
  maximum over tau' from the back expiry to tau, and never below the back expiry's constrained
  w(k); before the front expiry, by its running minimum over tau' from tau to the front expiry,
  and never above the front's constrained w(k). Step 5's w is a piecewise-rational function of
  tau', so that maximum (minimum) is found exactly, at the segment ends and stationary points
  (_envelope below).

Each value the constraint moves, up or down, beyond rounding gets the bit. Where step 5 already
rises with tau, as for every smile whose w grows less than quadratically in k, the envelope is
step 5 itself.

An expiry is usable for the surface only with at least MIN_NODES nodes ("thin" otherwise).
"""

from __future__ import annotations

import numpy as np

MIN_NODES = 5                 # ADR-0004 step 2: a smile needs at least 5 valid OTM quotes
LEE_SLOPE_MAX = 2.0           # Lee (2004): w / |k| -> at most 2 in the wings

# position_marks.mark_flags bits for the surface (ADR-0004); the engine (M3) adds its own.
SURFACE_EXTRAP_STRIKE = 1 << 0
SURFACE_CROSS_EXPIRY = 1 << 1
SURFACE_EXTRAP_TENOR = 1 << 2
SURFACE_CALENDAR_ADJUSTED = 1 << 3   # the calendar constraint moved the value, up or down: smiles crossed
SURFACE_FLAG_NAMES = ("SURFACE_EXTRAP_STRIKE", "SURFACE_CROSS_EXPIRY", "SURFACE_EXTRAP_TENOR", "SURFACE_CALENDAR_ADJUSTED")

# smile_fits.fit_flags bits.
SMILE_THIN = 1 << 0           # fewer than MIN_NODES nodes: not used by the surface
SMILE_ATM_OUTSIDE = 1 << 1    # k = 0 lies outside the nodes, so atm_iv is an extrapolation
SMILE_FORWARD_FALLBACK = 1 << 2  # the expiry's forward is the dividend fallback, not parity
SMILE_FORWARD_RAW = 1 << 3    # the forward is raw parity: too few near-K* quotes had an American IV
SMILE_FLAG_NAMES = ("SMILE_THIN", "SMILE_ATM_OUTSIDE", "SMILE_FORWARD_FALLBACK", "SMILE_FORWARD_RAW")


def smile_nodes(log_moneyness, iv, tau: float) -> tuple[np.ndarray, np.ndarray]:
    """(k, w) nodes sorted by k from OTM IVs: w = iv^2 tau. NaN IVs are left out."""
    k, sigma = np.asarray(log_moneyness, dtype=float), np.asarray(iv, dtype=float)
    keep = np.isfinite(k) & np.isfinite(sigma)
    order = np.argsort(k[keep], kind="stable")
    return k[keep][order], (sigma[keep][order] ** 2) * tau


def wing_slope(w_near: float, w_far: float, k_near: float, k_far: float) -> float:
    """The extrapolation slope of w per unit of |k| moving away from the nodes, clipped to [0, 2]."""
    return float(np.clip((w_far - w_near) / abs(k_far - k_near), 0.0, LEE_SLOPE_MAX))


def smile_variance(k, k_nodes, w_nodes) -> tuple[np.ndarray, np.ndarray]:
    """(w at k, True where k is beyond the nodes) for one expiry: steps 2 and 3. Needs 2+ nodes.

    ADR-0004 test 5: IVs 0.22 at k = -0.05 and 0.18 at 0, tau 0.1: w(-0.025) = 0.004040.
    Test 9: IVs 0.22 at -0.10 and 0.20 at -0.05: the slope in |k| is 0.0168 and w(-0.15) = 0.00568.
    """
    k = np.asarray(k, dtype=float)
    kn, wn = np.asarray(k_nodes, dtype=float), np.asarray(w_nodes, dtype=float)
    inside = np.interp(k, kn, wn)                       # linear in w between neighbouring nodes
    left = wn[0] + wing_slope(wn[1], wn[0], kn[1], kn[0]) * (kn[0] - k)
    right = wn[-1] + wing_slope(wn[-2], wn[-1], kn[-2], kn[-1]) * (k - kn[-1])
    w = np.where(k < kn[0], left, np.where(k > kn[-1], right, inside))
    return w, (k < kn[0]) | (k > kn[-1])


def smile_iv(k, tau: float, k_nodes, w_nodes) -> tuple[np.ndarray, np.ndarray]:
    """(sigma, extrapolated) at k for one expiry with time to expiry tau."""
    w, beyond = smile_variance(k, k_nodes, w_nodes)
    return np.sqrt(np.maximum(w, 0.0) / tau), beyond


def _breakpoints(k_nodes, w_nodes) -> np.ndarray:
    """Where w(x) / x^2 can have an extremum: the nodes, and each linear piece's stationary point.

    On a piece w = c + b x, d/dx [(c + b x) / x^2] = -(b x + 2 c) / x^3 vanishes at x = -2c / b.
    """
    kn, wn = np.asarray(k_nodes, dtype=float), np.asarray(w_nodes, dtype=float)
    points = [kn]
    slope_in = np.diff(wn) / np.diff(kn)
    intercept = wn[:-1] - slope_in * kn[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        stationary = -2 * intercept / slope_in
    points.append(stationary[(stationary > kn[:-1]) & (stationary < kn[1:])])
    left, right = wing_slope(wn[1], wn[0], kn[1], kn[0]), wing_slope(wn[-2], wn[-1], kn[-2], kn[-1])
    for slope, c, beyond in ((-left, wn[0] + left * kn[0], lambda x: x < kn[0]),
                             (right, wn[-1] - right * kn[-1], lambda x: x > kn[-1])):
        if slope != 0:
            x = -2 * c / slope
            if beyond(x):
                points.append(np.array([x]))
    return np.concatenate(points)


def _envelope(k, x_end, k_nodes, w_nodes, take_max: bool) -> np.ndarray:
    """max (or min) over x between k and x_end of k^2 w(x) / x^2: step 5's w over a span of tenors.

    Along k / sqrt(tau) from an expiry at tau_e, the total variance at tau' is
    w(x) tau' / tau_e with x = k sqrt(tau_e / tau'), that is k^2 w(x) / x^2. So its running
    maximum (minimum) over a span of tau' is this extremum over the matching span of x. k and
    x_end have the same sign; at k = 0 the span is the single point 0.
    """
    k, x_end = np.asarray(k, dtype=float), np.asarray(x_end, dtype=float)
    lo, hi = np.minimum(k, x_end), np.maximum(k, x_end)
    points = _breakpoints(k_nodes, w_nodes)
    # Candidates per k: the two ends, and the breakpoints strictly between them.
    candidates = np.concatenate([lo[:, None], hi[:, None], np.broadcast_to(points, (k.size, points.size))], axis=1)
    within = np.concatenate([np.ones((k.size, 2), bool), (points[None, :] > lo[:, None]) & (points[None, :] < hi[:, None])],
                            axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = smile_variance(candidates.ravel(), k_nodes, w_nodes)[0].reshape(candidates.shape) * (k[:, None] / candidates) ** 2
    ratio = np.where(within, ratio, -np.inf if take_max else np.inf)
    out = ratio.max(axis=1) if take_max else ratio.min(axis=1)
    # k = 0: w(0) tau' / tau_e at the end of the span (the ratio is 0/0 there).
    return np.where(k == 0, smile_variance(np.zeros(k.size), k_nodes, w_nodes)[0], out)


def calendar_variance(w_own, anchored) -> np.ndarray:
    """The calendar-constrained w of each expiry at each k: rows are expiries in tau order, columns k.

    Quoted values beat extrapolated ones (M2 round 2, design claim 1; decision E1). A row's w(k) is
    ANCHORED where k lies inside that expiry's own nodes (a quote on each side of it).

    (a) An anchored value becomes the running maximum of the anchored values up to it, in tau
        order: two quoted smiles that cross are resolved by raising the longer one, as before.
    (b) An extrapolated value (k beyond that expiry's nodes) is clamped into [the last anchored
        floor before it, the next anchored floor after it]: a shorter expiry's extrapolated wing can
        no longer lift a longer expiry's quoted node (the first floor did: 2020-02-28, a 322-day
        node at k = -1.43 went from 0.515 to 1.242 off the 215-day wing), and it is lowered to the
        next quoted value instead of standing above it.
    (c) A final running maximum. It cannot move an anchored value, whose (a) value already bounds
        every row before it from above; it only orders extrapolated values between two anchors.

    A NaN or infinite w is a missing value (round 3, decision F7: +inf was clipped to the next floor,
    or spread to every later row): it is not an anchor and never spreads to the rows after it
    (np.fmax); the row where it is comes back NaN.
    """
    w_own = np.asarray(w_own, dtype=float)
    missing = ~np.isfinite(w_own)
    w_own = np.where(missing, np.nan, w_own)
    anchor = np.asarray(anchored, dtype=bool) & ~missing
    rows = w_own.shape[0]
    floor = np.fmax.accumulate(np.where(anchor, w_own, -np.inf), axis=0)        # (a), -inf before the first anchor
    before = np.vstack([np.full((1,) + w_own.shape[1:], -np.inf), floor[:-1]])
    # The floor at the next anchor after each row: index of the first anchored row below, +inf if none.
    index = np.where(anchor, np.arange(rows)[:, None], rows)
    following = np.minimum.accumulate(index[::-1], axis=0)[::-1]
    following = np.vstack([following[1:], np.full((1,) + w_own.shape[1:], rows)])
    after = np.where(following < rows, np.take_along_axis(np.vstack([floor, floor[-1:]]), np.minimum(following, rows), 0),
                     np.inf)
    value = np.where(anchor, floor, np.clip(w_own, before, after))              # (b); NaN stays NaN
    final = np.fmax.accumulate(value, axis=0)                                   # (c), NaN skipped
    return np.where(missing, np.nan, final)


def _moved(new, old) -> np.ndarray:
    """True where the calendar constraint moved a value, beyond rounding (1e-12 of it)."""
    with np.errstate(invalid="ignore"):
        return np.abs(new - old) > 1e-12 * np.abs(old)


def surface_iv(k, tau: float, expiries, calendar: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """(sigma, flags) at log-moneyness k (an array) and one tau, from the usable expiries.

    `expiries` is a list of (tau_i, k_nodes, w_nodes), each with at least MIN_NODES nodes; they are
    sorted by tau_i here, and two with the same tau_i (within 1e-12) raise ValueError. Steps 2-5 and the calendar constraint of the module docstring; flags are
    SURFACE_* bits, one int per k. SURFACE_CALENDAR_ADJUSTED is set exactly where the value differs
    from steps 2-5 alone (`calendar=False`, kept to measure the constraint), up or down. At tau <= 0
    there is no implied vol: NaN, never an exception (an option on its expiry date is worth its
    intrinsic value, ADR-0003), and the NaN is returned before the equal-tau check, so equal taus
    raise only at tau > 0.
    ADR-0004 test 10: one expiry at 14/365 with IVs 0.22 at k = -0.05 and 0.18 at 0, read at
    tau = 7/365 and k = -0.025, gives 0.2091 along k/sqrt(tau) (0.2010 at the same k).
    """
    k = np.asarray(k, dtype=float)
    shape = k.shape
    k = k.ravel()
    if not expiries:
        raise ValueError("no usable expiry: the surface needs at least one smile with 5 or more nodes")
    flags = np.zeros(k.size, dtype=np.int32)
    if not (np.isfinite(tau) and tau > 0):
        return np.full(shape, np.nan), flags.reshape(shape)
    expiries = sorted(expiries, key=lambda e: float(e[0]))
    taus = np.array([e[0] for e in expiries], dtype=float)
    # Two smiles at one tau have no order, so which one the constraint raises would depend on the list's
    # order (round 3, decision F7): refused.
    same = np.flatnonzero(np.diff(taus) <= 1e-12)
    if same.size:
        raise ValueError(f"two usable expiries have the same tau ({taus[same[0]]!r} and {taus[same[0] + 1]!r}, within "
                         "1e-12 years): one smile per expiry")
    # Every expiry's own w at k (steps 2-3), and the calendar-constrained one (calendar_variance).
    own = [smile_variance(k, kn, wn) for _, kn, wn in expiries]
    w_own = np.vstack([w for w, _ in own])
    beyond = np.vstack([b for _, b in own])
    w_cal = calendar_variance(w_own, ~beyond) if calendar else w_own

    exact = np.flatnonzero(np.isclose(taus, tau, rtol=0, atol=1e-12))
    below, above = np.flatnonzero(taus < tau), np.flatnonzero(taus > tau)
    if exact.size:                                        # steps 2-3 on the own expiry
        i = exact[0]
        w, plain = w_cal[i], w_own[i]
        flags |= np.where(beyond[i], SURFACE_EXTRAP_STRIKE, 0)
    elif below.size and above.size:                       # step 4: between two expiries
        lo, hi = below[-1], above[0]
        weight = (tau - taus[lo]) / (taus[hi] - taus[lo])
        w = w_cal[lo] + (w_cal[hi] - w_cal[lo]) * weight
        plain = w_own[lo] + (w_own[hi] - w_own[lo]) * weight
        flags |= SURFACE_CROSS_EXPIRY | np.where(beyond[lo] | beyond[hi], SURFACE_EXTRAP_STRIKE, 0)
    else:                                                 # step 5: before the front or past the back
        i = below[-1] if below.size else above[0]
        t_near, k_near, w_near = expiries[i]
        x = k * np.sqrt(t_near / tau)
        plain, outside = smile_variance(x, k_near, w_near)
        plain = plain * tau / t_near
        w = plain
        if calendar and below.size:   # past the back: the running maximum since it, never below its value there
            w = np.maximum(_envelope(k, x, k_near, w_near, take_max=True) * np.where(k == 0, tau / t_near, 1.0), w_cal[i])
        elif calendar:                # before the front: the running minimum up to it, never above its value there
            w = np.minimum(_envelope(k, x, k_near, w_near, take_max=False) * np.where(k == 0, tau / t_near, 1.0), w_cal[i])
        flags |= SURFACE_EXTRAP_TENOR | np.where(outside, SURFACE_EXTRAP_STRIKE, 0)
    flags |= np.where(_moved(w, plain), SURFACE_CALENDAR_ADJUSTED, 0)
    return np.sqrt(np.maximum(w, 0.0) / tau).reshape(shape), flags.reshape(shape)
