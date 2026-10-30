"""Black-76: European option prices and greeks on a FORWARD, not on the spot (ADR-0008 §1).

Why the forward. SPY pays a discrete quarterly dividend, and an option's value depends on the
price the stock is expected to have AT EXPIRY: the forward F. Put-call parity gives F straight
from the market's own quotes (forward.py), dividend included, so no dividend yield q is needed.
Black-76 is Black-Scholes written in F:

    d1 = (ln(F/K) + sigma^2 tau / 2) / (sigma sqrt(tau)),   d2 = d1 - sigma sqrt(tau)
    C  = DF [F N(d1) - K N(d2)]
    P  = DF [K N(-d2) - F N(-d1)]                       with DF = exp(-r tau)

Vocabulary. K strike, tau years to expiry (calendar days / 365, forward.tau_years), r the
continuous rate (DGS3MO, ADR-0007), sigma the implied vol as a decimal (0.20 = 20%), N the
standard normal CDF and n its density.

Greeks, per share and per unit of each input (ADR-0008 §1; the USD units of ADR-0006 are in
greeks_usd below):

    spot delta  dV/dS = DF (F/S) N(d1)  (call),  -DF (F/S) N(-d1)  (put)
    gamma       d2V/dS2 = DF F n(d1) / (S^2 sigma sqrt(tau))        (same for calls and puts)
    vega        dV/dsigma = DF F n(d1) sqrt(tau)                     (same for calls and puts)
    theta       dV/dt = r V - DF F n(d1) sigma / (2 sqrt(tau))      (per year of calendar time)

The spot greeks treat F as proportional to S (F/S held fixed when S moves), which is what the
spot delta of ADR-0008 §1 says. Theta holds F, K, sigma and r fixed and lets one unit of time
pass: tau shrinks, so dV/dt = -dV/dtau.

Every function takes numpy arrays (or plain floats) and broadcasts, so one call prices a whole
chain. Pure: no I/O, no clock.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr

# 1 / sqrt(2 pi), for the normal density n(x) = exp(-x^2 / 2) / sqrt(2 pi).
INV_SQRT_2PI = 1.0 / np.sqrt(2.0 * np.pi)
# ADR-0006 units: one SPY contract is 100 shares, gamma per 1% move, vega per 1 vol point, theta
# per calendar day.
CONTRACT_MULTIPLIER = 100
ONE_PERCENT = 0.01
ONE_VOL_POINT = 0.01
DAYS_PER_YEAR = 365


def normal_pdf(x):
    """n(x), the standard normal density."""
    return INV_SQRT_2PI * np.exp(-0.5 * np.asarray(x, dtype=float) ** 2)


def d1_d2(forward, strike, tau, sigma):
    """(d1, d2). Needs tau > 0 and sigma > 0: at expiry there is no distribution left to integrate."""
    forward, strike, tau, sigma = (np.asarray(x, dtype=float) for x in (forward, strike, tau, sigma))
    spread = sigma * np.sqrt(tau)          # the standard deviation of ln(F_T / F)
    d1 = (np.log(forward / strike) + 0.5 * spread**2) / spread
    return d1, d1 - spread


def price(forward, strike, tau, rate, sigma, is_call):
    """The Black-76 price of a European call (is_call True) or put (False), per share."""
    d1, d2 = d1_d2(forward, strike, tau, sigma)
    df = np.exp(-np.asarray(rate, dtype=float) * np.asarray(tau, dtype=float))
    forward, strike = np.asarray(forward, dtype=float), np.asarray(strike, dtype=float)
    call = df * (forward * ndtr(d1) - strike * ndtr(d2))
    put = df * (strike * ndtr(-d2) - forward * ndtr(-d1))
    return np.where(is_call, call, put)


def intrinsic(spot, strike, is_call):
    """max(S - K, 0) for a call, max(K - S, 0) for a put: the value at expiry (ADR-0008 §5)."""
    spot, strike = np.asarray(spot, dtype=float), np.asarray(strike, dtype=float)
    return np.where(is_call, np.maximum(spot - strike, 0.0), np.maximum(strike - spot, 0.0))


def price_bounds(forward, strike, tau, rate, is_call):
    """(lower, upper): every European price lies strictly between them (ADR-0008 §7).

    A call is worth more than its discounted intrinsic value DF max(F - K, 0) and less than the
    discounted forward DF F; a put more than DF max(K - F, 0) and less than DF K. A price on or
    outside a bound implies no volatility at all, so the IV solver refuses it (IV_FAIL).
    """
    forward, strike = np.asarray(forward, dtype=float), np.asarray(strike, dtype=float)
    df = np.exp(-np.asarray(rate, dtype=float) * np.asarray(tau, dtype=float))
    lower = np.where(is_call, df * np.maximum(forward - strike, 0.0), df * np.maximum(strike - forward, 0.0))
    upper = np.where(is_call, df * forward, df * strike)
    return lower, upper


def vega(forward, strike, tau, rate, sigma):
    """dV/dsigma per share, per 1.00 of vol (ADR-0006's vega_1vol_usd is this x 0.01 x 100 x qty)."""
    d1, _ = d1_d2(forward, strike, tau, sigma)
    df = np.exp(-np.asarray(rate, dtype=float) * np.asarray(tau, dtype=float))
    return df * np.asarray(forward, dtype=float) * normal_pdf(d1) * np.sqrt(np.asarray(tau, dtype=float))


def greeks(spot, forward, strike, tau, rate, sigma, is_call):
    """{price, delta, gamma, vega, theta} per share (formulas in the module docstring).

    delta and gamma are with respect to the SPOT S, holding F/S fixed; theta is per year.
    """
    spot, forward, strike, tau, rate, sigma = (np.asarray(x, dtype=float)
                                               for x in (spot, forward, strike, tau, rate, sigma))
    d1, _ = d1_d2(forward, strike, tau, sigma)
    df = np.exp(-rate * tau)
    density = normal_pdf(d1)
    value = price(forward, strike, tau, rate, sigma, is_call)
    ratio = forward / spot
    return {
        "price": value,
        "delta": np.where(is_call, df * ratio * ndtr(d1), -df * ratio * ndtr(-d1)),
        "gamma": df * forward * density / (spot**2 * sigma * np.sqrt(tau)),
        "vega": df * forward * density * np.sqrt(tau),
        "theta": rate * value - df * forward * density * sigma / (2 * np.sqrt(tau)),
    }


def greeks_usd(quantity, spot, forward, strike, tau, rate, sigma, is_call):
    """ADR-0006's units for `quantity` contracts (positive = long), as USD amounts.

        delta_shares    q 100 delta                      share-equivalent exposure
        delta_usd       delta_shares S                   P&L for a +100% move, to first order
        gamma_1pct_usd  q 100 gamma S^2 0.01             change in delta_usd for a +1% move in S
        vega_1vol_usd   q 100 vega 0.01                  P&L when IV rises by 1 vol point
        theta_1d_usd    q 100 theta / 365                P&L from one calendar day passing

    One long call at S = F = K = 400, sigma 0.20, 30 days, r = 0: $20,457.44, $2,781.94, $45.73
    and -$15.24 (ADR-0006 test 1).
    """
    per_share = greeks(spot, forward, strike, tau, rate, sigma, is_call)
    contracts = np.asarray(quantity, dtype=float) * CONTRACT_MULTIPLIER
    spot = np.asarray(spot, dtype=float)
    delta_shares = contracts * per_share["delta"]
    return {
        "delta_shares": delta_shares,
        "delta_usd": delta_shares * spot,
        "gamma_1pct_usd": contracts * per_share["gamma"] * spot**2 * ONE_PERCENT,
        "vega_1vol_usd": contracts * per_share["vega"] * ONE_VOL_POINT,
        "theta_1d_usd": contracts * per_share["theta"] / DAYS_PER_YEAR,
    }
