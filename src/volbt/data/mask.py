"""The DoltHub sampling mask: replay DoltHub's own SPY sampling on the dense OptionsDX chain.

Why (ADR-0009 §4). Out of sample we only have DoltHub, which lists about 3 expiries and 17 to
27 strikes a day, re-centred daily, mostly on Mon/Wed/Fri until Oct-2024 (677 of its 688 dates;
the rest are 6 Thursdays and 5 Tuesdays). To estimate what that thin sampling does to a backtest,
we run the in-sample period on OptionsDX twice: on the full chain, and cut to DoltHub's listings.

    chain_mask = none           the full OptionsDX chain
    chain_mask = dolthub        on each date, only the (expiry, strike) pairs DoltHub lists
                                for SPY that date. A session DoltHub lacks has no pairs: the
                                engine marks with STALE_SURFACE and option orders wait.
    chain_mask = dolthub_daily  as dolthub, but a Tue/Thu session DoltHub lacks keeps the
                                pairs of DoltHub's last listing before it (the holdout has
                                almost every weekday from Oct-2024).

A pair is (expiry, strike), so it keeps the call and the put at that strike. Strikes are
matched as integer thousandths of a dollar (strike_milli), never as floats.
DoltHub's dates are the clean ones: the calendar rule has already been applied to them.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

MASKS = ("none", "dolthub", "dolthub_daily")
# The validation window, where both vendors exist (ADR-0009 §4).
WINDOW = (date(2020, 1, 6), date(2023, 12, 29))
# Monday = 0, so Tuesday = 1 and Thursday = 3.
CARRY_WEEKDAYS = (1, 3)


def strike_milli(strike) -> np.ndarray:
    return np.rint(np.asarray(strike, dtype=float) * 1000).astype(np.int64)


def as_dates(column) -> pd.Series:
    """Any date-like column (datetime.date objects, arrow dates, timestamps) as datetime.date objects."""
    return pd.to_datetime(pd.Series(column)).dt.date


def listed_pairs(dolthub_quotes: pd.DataFrame) -> pd.DataFrame:
    """quote_date, expiry, strike_milli: every (expiry, strike) DoltHub lists on each of its dates."""
    pairs = pd.DataFrame({"quote_date": as_dates(dolthub_quotes["quote_date"]).to_numpy(),
                          "expiry": as_dates(dolthub_quotes["expiry"]).to_numpy(),
                          "strike_milli": strike_milli(dolthub_quotes["strike"])})
    return pairs.drop_duplicates().sort_values(["quote_date", "expiry", "strike_milli"]).reset_index(drop=True)


def build_mask(pairs: pd.DataFrame, sessions: list[date], mask: str, window=WINDOW) -> pd.DataFrame:
    """The kept (quote_date, expiry, strike_milli) for one mask over `window`, plus listed_on:
    the DoltHub date the pair comes from (the same date, or the carried-from date)."""
    if mask not in ("dolthub", "dolthub_daily"):
        raise ValueError(f"mask must be 'dolthub' or 'dolthub_daily', not {mask!r}")
    start, end = window
    inside = pairs[(pairs["quote_date"] >= start) & (pairs["quote_date"] <= end)]
    kept = inside.assign(listed_on=inside["quote_date"])
    if mask == "dolthub_daily":
        listing_dates = sorted(set(pairs["quote_date"]))
        by_date = {d: group for d, group in pairs.groupby("quote_date", sort=True)}
        carried = []
        for session in sessions:
            if not (start <= session <= end) or session in by_date or session.weekday() not in CARRY_WEEKDAYS:
                continue
            earlier = [d for d in listing_dates if d < session]
            if not earlier:
                continue
            source = by_date[earlier[-1]]
            # An expiry that has passed by the session cannot be quoted on it.
            live = source[source["expiry"] >= session]
            carried.append(live.assign(quote_date=session, listed_on=earlier[-1]))
        if carried:
            kept = pd.concat([kept, *carried], ignore_index=True)
    out = kept.assign(mask=mask)[["mask", "quote_date", "expiry", "strike_milli", "listed_on"]]
    return out.sort_values(["quote_date", "expiry", "strike_milli"]).reset_index(drop=True)


def apply_mask(chain: pd.DataFrame, mask_pairs: pd.DataFrame) -> pd.DataFrame:
    """The rows of an OptionsDX chain whose (quote_date, expiry, strike) the mask keeps."""
    # Merge on plain timestamps and integers, so the two sides' date types cannot disagree.
    key = ["key_quote_date", "key_expiry", "key_strike_milli"]
    left = chain.assign(key_quote_date=pd.to_datetime(chain["quote_date"]).to_numpy(),
                        key_expiry=pd.to_datetime(chain["expiry"]).to_numpy(),
                        key_strike_milli=strike_milli(chain["strike"]))
    right = pd.DataFrame({"key_quote_date": pd.to_datetime(mask_pairs["quote_date"]).to_numpy(),
                          "key_expiry": pd.to_datetime(mask_pairs["expiry"]).to_numpy(),
                          "key_strike_milli": np.asarray(mask_pairs["strike_milli"], dtype=np.int64)}).drop_duplicates()
    return left.merge(right, on=key, how="inner").drop(columns=key).reset_index(drop=True)
