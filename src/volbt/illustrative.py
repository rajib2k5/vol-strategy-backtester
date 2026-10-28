"""Illustrative SSVI implied-vol surface for the milestone-0 3D hero.

ILLUSTRATIVE SHAPE, NOT MARKET DATA. It exists only so the app has a believable
surface to draw before any real data is loaded. Milestone 2 (the pricing core:
forwards, implied vols, fitted smiles) replaces it with surfaces built from real
SPY option chains; milestone 1 only loads and cleans the data.

Model: SSVI, "surface SVI" (Gatheral & Jacquier, 2014, "Arbitrage-free SVI
volatility surfaces", Quantitative Finance 14(1)). Vocabulary:

    k      log-moneyness, ln(K/F): strike K vs forward F. k < 0 is a put-side
           (low-strike) option, k > 0 a call-side (high-strike) option.
    T      time to expiry in years (here DTE / 365).
    w      total variance, sigma_implied^2 * T.
    theta  ATM total variance, theta(T) = w(k=0, T) = sigma_atm(T)^2 * T.
    rho    skew: rho < 0 means low strikes have higher vol (equity-index shape).
    phi    how fast the smile bends away from the money, phi(theta) = eta/sqrt(theta).

Why total variance and not vol: the no-arbitrage rules (a long-dated option
cannot be cheaper than a short-dated one with the same strike) are simple
statements about w, not about vol.
"""

from __future__ import annotations

import numpy as np

# ATM vol goes in a straight line from 16% at 7 days to 20% at 365 days. Equity
# index vol is normally a little higher further out; the exact numbers are a
# choice made for looks.
SIGMA_ATM_SHORT = 0.16
SIGMA_ATM_LONG = 0.20
# Skew and curvature. rho = -0.7 is a typical equity-index skew; eta = 1.0 keeps
# the smile well inside the no-arbitrage limits (see no_arbitrage_checks).
RHO = -0.7
ETA = 1.0
# The grid the app draws: 20 expiries from 7 to 365 days, 26 log-moneyness points
# from -0.30 to +0.20 (steps of 0.02, so k = 0 is exactly on the grid).
DTE_MIN, DTE_MAX, N_DTE = 7, 365, 20
K_MIN, K_MAX, N_K = -0.30, 0.20, 26
DAYS_PER_YEAR = 365
# The log-moneyness points where the calendar check compares expiries. Wider than the
# drawn grid (-0.30..0.20) on purpose: arbitrage hides in the wings, not where we draw.
# Rounded for the same reason as the drawn grid (linspace float noise).
CALENDAR_CHECK_K = np.round(np.linspace(-1.0, 1.0, 201), 10)


def sigma_atm(dte, sigma_short=SIGMA_ATM_SHORT, sigma_long=SIGMA_ATM_LONG):
    """ATM vol at `dte` days: a straight line from `sigma_short` (at DTE_MIN) to `sigma_long` (at DTE_MAX)."""
    fraction = (np.asarray(dte, dtype=float) - DTE_MIN) / (DTE_MAX - DTE_MIN)
    return sigma_short + (sigma_long - sigma_short) * fraction


def atm_total_variance(dte, sigma_short=SIGMA_ATM_SHORT, sigma_long=SIGMA_ATM_LONG):
    """theta(T) = sigma_atm(T)^2 * T, with T = dte / 365 years."""
    years = np.asarray(dte, dtype=float) / DAYS_PER_YEAR
    return sigma_atm(dte, sigma_short, sigma_long) ** 2 * years


def phi(theta, eta=ETA):
    """How fast the smile bends away from the money: phi(theta) = eta / sqrt(theta)."""
    return eta / np.sqrt(theta)


def total_variance(k, theta, rho=RHO, eta=ETA):
    """SSVI total variance w(k, theta) = theta/2 * (1 + rho*phi*k + sqrt((phi*k + rho)^2 + 1 - rho^2))."""
    phi_k = phi(theta, eta) * k
    # At k = 0 this collapses to theta/2 * (1 + sqrt(rho^2 + 1 - rho^2)) = theta,
    # which is why theta is "the ATM total variance".
    return theta / 2 * (1 + rho * phi_k + np.sqrt((phi_k + rho) ** 2 + 1 - rho**2))


def iv_grid(rho=RHO, eta=ETA, sigma_short=SIGMA_ATM_SHORT, sigma_long=SIGMA_ATM_LONG):
    """Return (k_grid, dte_grid, iv) with iv[i_dte][j_k] as a decimal (0.20 = 20%)."""
    # Round away float noise: linspace gives -0.27999999999999997 where we mean -0.28.
    k_grid = np.round(np.linspace(K_MIN, K_MAX, N_K), 10)
    # Whole days: the app labels expiries as "30d", not "30.4d".
    dte_grid = np.round(np.linspace(DTE_MIN, DTE_MAX, N_DTE)).astype(int)
    # Column vectors (shape (N_DTE, 1)) so numpy broadcasts them against the k
    # row (shape (N_K,)) into a full (N_DTE, N_K) table: one row per expiry.
    theta = atm_total_variance(dte_grid, sigma_short, sigma_long)[:, None]
    years = (dte_grid / DAYS_PER_YEAR)[:, None]
    w = total_variance(k_grid, theta, rho, eta)
    # w = sigma^2 * T, so sigma = sqrt(w / T).
    return k_grid, dte_grid, np.sqrt(w / years)


def butterfly_conditions(theta, rho=RHO, eta=ETA):
    """The two SSVI butterfly conditions, as a pure function of the arrays `theta`, `rho`, `eta`.

    butterfly_1: theta*phi*(1+|rho|) < 4      (strict)
    butterfly_2: theta*phi^2*(1+|rho|) <= 4   (not strict)
        Together they rule out negative option-price curvature in strike, i.e.
        a butterfly spread (long wings, short the middle) with negative cost.
        Gatheral & Jacquier, Theorem 4.2. Each condition must hold at EVERY theta
        passed in; the one expiry that breaks it fails the whole surface.

    Kept free of the term structure and the grid so a test can feed it exact values
    and probe each boundary (equal to 4, just above, just below).

    The theorem asks for the conditions at EVERY theta > 0, but we only see the thetas passed
    in. For phi = eta/sqrt(theta), theta*phi*(1+|rho|) = eta*sqrt(theta)*(1+|rho|) keeps growing
    with theta, so the surface can be certified only up to a maximum expiry (Gatheral &
    Jacquier, Remark 4.4: t*_0, where that product reaches 4). The shipped surface ends far
    short of it.
    """
    theta = np.asarray(theta, dtype=float)
    phi_theta = phi(theta, eta)
    one_plus_abs_rho = 1 + abs(rho)
    return {
        "butterfly_1": bool(np.all(theta * phi_theta * one_plus_abs_rho < 4)),
        "butterfly_2": bool(np.all(theta * phi_theta**2 * one_plus_abs_rho <= 4)),
    }


def calendar_condition(theta, w):
    """No calendar-spread arbitrage on a total-variance table: nothing shrinks as expiry grows.

    `theta` is the ATM total variance per expiry (ascending expiry) and `w[i][j]` the total
    variance at expiry i and log-moneyness j. A longer-dated option cannot be cheaper than a
    shorter-dated one at the same strike, which in w means w(k, T) never decreases in T at
    ANY k, not just at the money. Equal values are allowed.
    """
    theta = np.asarray(theta, dtype=float)
    w = np.asarray(w, dtype=float)
    return bool(np.all(np.diff(theta) >= 0) and np.all(np.diff(w, axis=0) >= 0))


def no_arbitrage_checks(
    dte,
    rho=RHO,
    eta=ETA,
    sigma_short=SIGMA_ATM_SHORT,
    sigma_long=SIGMA_ATM_LONG,
    k=CALENDAR_CHECK_K,
):
    """Check the SSVI no-arbitrage conditions over the expiries in `dte` (ascending).

    butterfly_1, butterfly_2: see `butterfly_conditions`.
    calendar: `calendar_condition` on the total variance w(k, T) actually computed for these
        expiries over the log-moneyness points `k`, plus theta(T) non-decreasing. The ATM term
        structure (`sigma_short` -> `sigma_long`) is a parameter, so an inverted term structure
        (short-dated vol far above long-dated, theta falling with T) really does fail.

    What this does and does not prove about calendar arbitrage. Gatheral & Jacquier,
    Theorem 4.1: SSVI is free of calendar-spread arbitrage if and only if theta is
    non-decreasing in T (checked here) and 0 <= d(theta*phi)/d(theta) <= (1 + sqrt(1 - rho^2)) / rho^2 * phi
    for all theta > 0 (the upper bound is infinite when rho = 0).
    For phi = eta / sqrt(theta) we have theta*phi = eta*sqrt(theta), so
    d(theta*phi)/d(theta) = eta / (2*sqrt(theta)) = phi/2, and the condition reads
        0 <= phi/2 <= (1 + sqrt(1 - rho^2)) / rho^2 * phi.
    That holds for every theta, eta and |rho| < 1, because
    rho^2/2 <= 1/2 < 1 <= 1 + sqrt(1 - rho^2).
    So for this phi the theorem reduces to "theta non-decreasing"; the w-grid comparison is
    a second, direct check on the numbers we actually draw. It samples finitely many k, so
    it can miss a violation between the points; the analytic argument covers every k.
    """
    theta = np.atleast_1d(atm_total_variance(dte, sigma_short, sigma_long))
    # (n_expiries, n_k) table: expiries down the rows, strikes across the columns.
    w = total_variance(np.asarray(k, dtype=float)[None, :], theta[:, None], rho, eta)
    return {
        **butterfly_conditions(theta, rho, eta),
        "calendar": calendar_condition(theta, w),
    }
