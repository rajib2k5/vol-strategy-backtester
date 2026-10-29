"""The trading calendar, and what to do with chain rows dated on a day that is not a session.

A SESSION is a date with a SPY daily bar (ADR-0009 §1). We do not take the calendar from the
chain's own dates: OptionsDX has 12 snapshot dates on market closures and misses 26 sessions.

A vendor date that is not a session gets NON_SESSION_DATE and is DROPPED, in every source.
These are the only rows the cleaning step deletes; everything else is flagged, not dropped.

Why no relabel (changed in round 2 of the M1 review, default taken 2026-10-29, the owner can
override it). Until then a closure-dated snapshot moved to the previous session when that
session had no snapshot of its own and the snapshot's UNDERLYING_LAST equalled its SPY close
within $0.02. One date qualified: OptionsDX's 2022-06-20 file, moved to 2022-06-17. Its prices
do look like 06-17 closes, but its CONTRACT LIST is 06-20's: 9,742 rows whose first expiry is
06-21, none of the 516 contracts expiring 06-17 that 06-16 listed, and 1,142 symbols 06-16 did
not list (new expiries 07-25 and 07-27). Filed under 06-17, it would show a strategy on 06-17
contracts first listed on 06-20 (look-ahead) and hide that day's own expiries. A matching
underlying cannot tell a late snapshot from a mixed one, so 2022-06-17 is served as missing.

What stays, as a diagnostic: each dropped date keeps its previous session and that session's
close (prev_session, prev_close), and the quality report compares the vendor's underlying with
it (quality.non_session_check). Nothing is moved on the strength of it. The RELABELLED bit
keeps its number and is never set (flags.py).
"""

from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from volbt.data.flags import NON_SESSION_DATE


def sessions_from_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """date, close: one row per SPY session, ascending."""
    sessions = bars[["date", "close"]].sort_values("date").reset_index(drop=True)
    if sessions["date"].duplicated().any():
        raise ValueError("SPY bars have a duplicate date")
    return sessions


def build_date_map(snapshots: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Decide every (source, vendor_date): keep it as a session, or drop it.

    `snapshots` has one row per (source, vendor_date) with that date's `underlying_last`
    (null if the vendor has none) and, optionally, its row count `rows`.
    Returns the same rows plus: action ("session" / "drop"), quote_date (the vendor date for a
    session, null when dropped), flags (NON_SESSION_DATE on a dropped date), and, for a dropped
    date, the diagnostic prev_session and prev_close (the session before it and its SPY close).
    """
    sessions = sessions_from_bars(bars)
    session_days = list(sessions["date"])
    close_on = dict(zip(sessions["date"], sessions["close"]))
    session_set = set(session_days)
    out = snapshots.copy().sort_values(["source", "vendor_date"]).reset_index(drop=True)
    if "rows" not in out.columns:
        out["rows"] = pd.NA

    actions, quote_dates, flag_values, prev_sessions, prev_closes = [], [], [], [], []
    for vendor_date in out["vendor_date"]:
        if vendor_date in session_set:
            actions.append("session"), quote_dates.append(vendor_date), flag_values.append(0)
            prev_sessions.append(None), prev_closes.append(np.nan)
            continue
        # bisect_left gives the index of the first session >= vendor_date; one before it is p.
        index = bisect.bisect_left(session_days, vendor_date) - 1
        prev = session_days[index] if index >= 0 else None
        actions.append("drop"), quote_dates.append(None), flag_values.append(NON_SESSION_DATE)
        prev_sessions.append(prev), prev_closes.append(close_on[prev] if prev is not None else np.nan)

    out["action"], out["quote_date"], out["flags"] = actions, quote_dates, flag_values
    out["prev_session"], out["prev_close"] = prev_sessions, prev_closes
    out["flags"] = out["flags"].astype("int32")
    return out


def missing_sessions(snapshot_dates, bars: pd.DataFrame, start=None, end=None) -> list:
    """Sessions in [start, end] (default: the snapshot range) on which the source has no snapshot."""
    have = set(snapshot_dates)
    first = start or min(have)
    last = end or max(have)
    return [d for d in sessions_from_bars(bars)["date"] if first <= d <= last and d not in have]
