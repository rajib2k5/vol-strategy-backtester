"""VIX regimes, lagged one session (ADR-0010 §3; milestone 4, plan section 2).

    vix_bucket(level)          "<15", "15-20", "20-30" or ">=30"
    shock_days(closes)         True where VIX rose at least +25% or at least +5 points close to close
    regime_labels(closes)      per VIX session: "shock", "post_shock" (a shock in the 21 sessions before), "calm"
    lagged_regime(vix, t)      (bucket, regime) for a strategy at session t

ADR-0010 lets a strategy use a regime only lagged. So the labels a strategy sees at t describe the previous VIX
session, the last row dated before t: its bucket is that close's, and its regime is "shock" if that session was a
shock, "post_shock" if a shock fell in the 21 VIX sessions before it, else "calm" (default taken 2026-11-09, owner
can override). Both are None before there is such a session; the regime is also None for the first VIX session,
which has no previous close to compare with.

May import (volbt): pricing, view. numpy only.
"""

from __future__ import annotations

from datetime import date

import numpy as np

BOUNDS = (15.0, 20.0, 30.0)
BUCKETS = ("<15", "15-20", "20-30", ">=30")
SHOCK_RISE = 0.25            # +25% close to close
SHOCK_POINTS = 5.0           # or +5 points
POST_SHOCK = 21              # the sessions after a shock that form the post-shock regime


def vix_bucket(level: float) -> str:
    """The ADR-0010 bucket of one VIX close: 19.99 -> "15-20", 20.00 -> "20-30"."""
    return BUCKETS[int(np.searchsorted(BOUNDS, level, "right"))]


def shock_days(closes) -> np.ndarray:
    """Element i: VIX rose at least +25% or at least +5 points from close i-1 to close i (False at i = 0)."""
    closes = np.asarray(closes, dtype=float)
    out = np.zeros(closes.size, dtype=bool)
    if closes.size > 1:
        before, after = closes[:-1], closes[1:]
        out[1:] = (after >= before * (1 + SHOCK_RISE)) | (after - before >= SHOCK_POINTS)
    return out


def regime_labels(closes) -> list[str | None]:
    """Element i: "shock", "post_shock" (a shock among the POST_SHOCK sessions before i) or "calm"; None at i = 0."""
    shocks = shock_days(closes)
    labels: list[str | None] = []
    for i in range(shocks.size):
        if i == 0:
            labels.append(None)
        elif shocks[i]:
            labels.append("shock")
        elif shocks[max(i - POST_SHOCK, 0):i].any():
            labels.append("post_shock")
        else:
            labels.append("calm")
    return labels


def lagged_regime(vix, t: date) -> tuple[str | None, str | None]:
    """(bucket, regime) of the last VIX session dated before t, from view.vix() (`date`, `close`)."""
    days = np.asarray(vix["date"]).astype("datetime64[D]")
    end = int(np.searchsorted(days, np.datetime64(t, "D"), "left"))     # rows dated before t
    if end == 0:
        return None, None
    # The last row's label needs the shocks of the POST_SHOCK rows before it, and each shock the close before it.
    closes = np.asarray(vix["close"], dtype=float)[max(end - POST_SHOCK - 2, 0):end]
    return vix_bucket(float(closes[-1])), regime_labels(closes)[-1]
