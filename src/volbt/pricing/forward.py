"""The forward F of one expiry, from put-call parity on the market's own quotes (ADR-0008 §3).

Put-call parity, for European options on one strike and expiry: C - P = DF (F - K). So every
strike with a valid call AND put quote gives a forward,

    F_K = K + (C_mid - P_mid) / DF,

and they should all agree. They do not quite: quotes are noisy, and American quotes carry an
early-exercise premium (EEP) that European parity does not know about. The procedure:

1. K* is the strike where C and P are closest (|C_mid - P_mid| smallest): the most at-the-money.
2. F is the MEDIAN of F_K over the 5 strikes nearest K*. A median ignores one or two bad quotes;
   strikes near the money have the tightest spreads.
3. The dispersion is the median absolute deviation of those F_K, divided by F.
4. A strike whose |F_K - F| / F is above 0.5% is a PARITY_OUTLIER.
5. With fewer than 3 valid pairs there is no parity forward. The FALLBACK carries the spot:
   F = S exp(r tau) - sum D_i exp(r (tau - tau_i)), with the projected dividends (dividends.py).

De-Americanisation (ADR-0008 §3a) runs steps 1-2 on European-equivalent mids, mid - EEP, instead
of the raw mids; volbt.pricing.chain does that, because it needs the lattice for a whole date at
once. This module holds the parts that work on one expiry's arrays.

Day count (ADR-0008 §5): tau = calendar days / 365. Both of a quote's stamps are 16:00 ET, so the
day count is exact; the vendor's own DTE column carries a daylight-saving artefact (6.9583 days
across the March clock change) and is never used.
"""

from __future__ import annotations

from datetime import date

import numpy as np

DAYS_PER_YEAR = 365
MEDIAN_STRIKES = 5           # F is the median F_K over this many strikes nearest K*
DEAM_STRIKES = 10            # the strikes nearest K* whose call and put are de-Americanised (§3a)
MIN_PAIRS = 3                # fewer valid pairs than this: the dividend fallback
OUTLIER_REL = 0.005          # |F_K - F| / F above this: PARITY_OUTLIER


def tau_years(quote_date: date, expiry: date) -> float:
    """Calendar days from the quote date to the expiry, over 365. 0 on the expiry date itself."""
    return (expiry - quote_date).days / DAYS_PER_YEAR


def discount_factor(rate, tau):
    """DF = exp(-r tau), with r the continuous rate from DGS3MO (ADR-0007)."""
    return np.exp(-np.asarray(rate, dtype=float) * np.asarray(tau, dtype=float))


def carry_forward(spot: float, rate: float, tau: float, div_times, div_amounts) -> float:
    """The fallback F = S exp(r tau) - sum D_i exp(r (tau - tau_i)) over dividends with 0 < tau_i <= tau.

    ADR-0008 test 7: S = 450, r = 5%, tau = 30/365, one dividend of 1.80 at 10/365 gives 450.048.
    """
    times, amounts = np.asarray(div_times, dtype=float), np.asarray(div_amounts, dtype=float)
    paid = (times > 0) & (times <= tau)
    return float(spot * np.exp(rate * tau) - (amounts[paid] * np.exp(rate * (tau - times[paid]))).sum())


def strike_forwards(strikes, call_mid, put_mid, df):
    """F_K = K + (C - P) / DF at each strike."""
    return np.asarray(strikes, dtype=float) + (np.asarray(call_mid, dtype=float) - np.asarray(put_mid, dtype=float)) / df


def nearest(strikes, center: float, count: int) -> np.ndarray:
    """Indices of the `count` strikes nearest `center`. A tie goes to the lower strike (stable sort)."""
    distance = np.abs(np.asarray(strikes, dtype=float) - center)
    return np.argsort(distance, kind="stable")[:count]


def parity_forward(strikes, call_mid, put_mid, df: float) -> dict | None:
    """Steps 1-3 for one expiry, on strikes sorted ascending that all have a valid call and put.

    Returns {forward, k_star, used (indices of the median strikes), mad_rel}, or None when there
    are fewer than MIN_PAIRS pairs. ADR-0008 test 2: K = 443, C = 5.560, P = 6.315,
    tau = 29/365, r = 0.0521594 give DF = 0.995864 and F_K = 442.2419.
    """
    strikes = np.asarray(strikes, dtype=float)
    if strikes.size < MIN_PAIRS:
        return None
    gap = np.asarray(call_mid, dtype=float) - np.asarray(put_mid, dtype=float)
    forwards = strike_forwards(strikes, call_mid, put_mid, df)
    k_star = float(strikes[np.argmin(np.abs(gap))])   # argmin: the first (lowest) strike on a tie
    used = nearest(strikes, k_star, MEDIAN_STRIKES)
    forward = float(np.median(forwards[used]))
    mad_rel = float(np.median(np.abs(forwards[used] - forward)) / forward)
    return {"forward": forward, "k_star": k_star, "used": used, "mad_rel": mad_rel}


def slope_per_strike(strikes, forwards) -> float:
    """The least-squares slope of F_K against K: dF_K/dK. NaN with fewer than 3 points.

    The American put premium grows with the strike, so raw F_K falls with K at positive rates:
    about -0.036 per strike on 2023-06-15 (ADR-0008, Revised, point 3).
    """
    strikes, forwards = np.asarray(strikes, dtype=float), np.asarray(forwards, dtype=float)
    if strikes.size < 3:
        return float("nan")
    centred = strikes - strikes.mean()
    return float((centred * (forwards - forwards.mean())).sum() / (centred**2).sum())
