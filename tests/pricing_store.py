"""A tiny built store for the pricing-build tests (not a test file: pytest does not collect it).

Made-up values only. Two sources, three snapshot dates, a handful of expiries and strikes:

    optionsdx  2023-06-14 and 2023-06-15 (year 2023), 2022-12-15 (year 2022)
    dolthub    2023-06-15 (year 2023)

Every quote is an AMERICAN price, from a CRR lattice of TRUTH_STEPS steps with the dividends
below at their real dates, at a smile sigma(k) = 0.18 - 0.25 k (a put skew, k = ln(K/F) on the
true forward), with a 2-cent spread around the mid, rounded to the cent. One put is crossed (its
quality_flags say so), so the build must leave it out of the forward and the smile.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from volbt.data import flags
from volbt.data.osi import osi_symbol
from volbt.data.store import Store
from volbt.pricing import lattice

SPOT = {date(2022, 12, 15): 395.00, date(2023, 6, 14): 437.18, date(2023, 6, 15): 442.60}
RATE_PCT = {date(2022, 12, 14): 4.20, date(2023, 6, 13): 5.20, date(2023, 6, 14): 5.25}
EXPIRIES = {date(2022, 12, 15): [date(2022, 12, 30), date(2023, 1, 20), date(2023, 3, 17)],
            date(2023, 6, 14): [date(2023, 6, 30), date(2023, 7, 14), date(2023, 8, 18)],
            date(2023, 6, 15): [date(2023, 6, 15), date(2023, 6, 30), date(2023, 7, 14), date(2023, 8, 18)]}
DIVIDENDS = [(date(2022, 9, 16), 1.596), (date(2022, 12, 16), 1.781), (date(2023, 3, 17), 1.506),
             (date(2023, 6, 16), 1.638)]
TRUTH_STEPS = 800
CROSSED_DATE, CROSSED_EXPIRY, CROSSED_STRIKE = date(2023, 6, 15), date(2023, 7, 14), 438.0


def smile_sigma(k):
    return 0.18 - 0.25 * k


def r_cc(pct):
    return (365 / 91) * math.log1p(pct / 100 * 91 / 365)


def true_forward(day: date, expiry: date, spot: float, rate: float) -> tuple[float, list, list]:
    """(F, dividend times, amounts): the carry forward with the dividends paid in (day, expiry]."""
    tau = (expiry - day).days / 365
    times = [(d - day).days / 365 for d, _ in DIVIDENDS if day < d <= expiry]
    amounts = [a for d, a in DIVIDENDS if day < d <= expiry]
    forward = spot * math.exp(rate * tau) - sum(a * math.exp(rate * (tau - t)) for t, a in zip(times, amounts))
    return forward, times, amounts


def quotes_for(day: date, source: str, expiries=None) -> list[dict]:
    rate = rate_on(day)
    spot = SPOT[day]
    rows = []
    for expiry in (EXPIRIES[day] if expiries is None else expiries):
        tau = (expiry - day).days / 365
        forward, times, amounts = true_forward(day, expiry, spot, rate)
        strikes = np.arange(round(spot) - 30, round(spot) + 31, 5.0)
        for call_put in ("C", "P"):
            if tau > 0:
                sigma = smile_sigma(np.log(strikes / forward))
                mids = lattice.crr(spot, strikes, tau, rate, sigma, call_put == "C", [times] if times else None,
                                   [amounts] if amounts else None, steps=TRUTH_STEPS)["price"]
            else:
                mids = np.maximum(spot - strikes, 0.0) if call_put == "C" else np.maximum(strikes - spot, 0.0)
            for strike, mid in zip(strikes, mids):
                bid = max(round(float(mid) - 0.02, 2), 0.0)
                ask = round(max(float(mid) + 0.02, 0.01), 2)
                bits = int(flags.mid_flags(flags.cents([bid]), flags.cents([ask]))[0])
                if tau == 0:
                    bits |= flags.EXPIRY_DAY
                rows.append({"source": source, "quote_date": day, "osi_symbol": osi_symbol("SPY", expiry, call_put, strike),
                             "expiry": expiry, "strike": float(strike), "call_put": call_put, "bid": bid, "ask": ask,
                             "spy_close": spot, "quality_flags": bits, "year": day.year})
    return rows


def rate_on(day: date) -> float:
    """The build's rule: the last DGS3MO value dated strictly before the quote date."""
    return r_cc([pct for d, pct in sorted(RATE_PCT.items()) if d < day][-1])


def make_store(root) -> Store:
    rows = [r for day in sorted(SPOT) for r in quotes_for(day, "optionsdx")] + quotes_for(date(2023, 6, 15), "dolthub")
    return _write(Store(root), rows)


# The summary's tenor buckets have edges at 60 and 180 days, and the expiry day is left out of
# them. One date whose expiries sit on each side of every edge.
TENOR_DATE = date(2023, 6, 14)
TENOR_DAYS = (0, 60, 61, 180, 181)


def make_tenor_store(root) -> Store:
    """One OptionsDX date, 2023-06-14, with expiries 0, 60, 61, 180 and 181 days out."""
    from datetime import timedelta

    expiries = [TENOR_DATE + timedelta(days=d) for d in TENOR_DAYS]
    return _write(Store(root), quotes_for(TENOR_DATE, "optionsdx", expiries))


def _write(store: Store, rows: list[dict]) -> Store:
    quotes = pd.DataFrame(rows)
    # One crossed OTM put on 2023-06-15 (OptionsDX): bid above ask.
    crossed = (quotes["source"] == "optionsdx") & (quotes["quote_date"] == CROSSED_DATE) & \
        (quotes["expiry"] == CROSSED_EXPIRY) & (quotes["strike"] == CROSSED_STRIKE) & (quotes["call_put"] == "P")
    quotes.loc[crossed, ["bid", "ask"]] = [5.50, 5.40]
    quotes.loc[crossed, "quality_flags"] = flags.CROSSED
    store.write_table("option_quotes", quotes, sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    store.write_table("rates", pd.DataFrame({"date": list(RATE_PCT), "dgs3mo_pct": list(RATE_PCT.values()),
                                             "r_cc": [r_cc(p) for p in RATE_PCT.values()]}), sort_by=("date",))
    store.write_table("dividends", pd.DataFrame({"ex_date": [d for d, _ in DIVIDENDS],
                                                 "amount": [a for _, a in DIVIDENDS]}), sort_by=("ex_date",))
    sessions = sorted(SPOT) + [date(2023, 6, 16), date(2023, 9, 15)]
    closes = [SPOT.get(d, 440.0) for d in sessions]
    store.write_table("spy_bars", pd.DataFrame({"date": sessions, "open": closes, "high": closes, "low": closes,
                                                "close": closes, "adj_close": closes, "volume": [1] * len(sessions)}),
                      sort_by=("date",))
    store.write_table("vix", pd.DataFrame({"date": sorted(SPOT), "open": [21.0, 14.0, 13.5], "high": [22.0, 14.5, 14.0],
                                           "low": [20.0, 13.5, 13.0], "close": [21.5, 13.9, 13.6]}), sort_by=("date",))
    return store
